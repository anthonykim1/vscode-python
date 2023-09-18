# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import ast
import json
import re
import sys
import textwrap
from typing import Iterable


def split_lines(source):
    """
    Split selection lines in a version-agnostic way.

    Python grammar only treats \r, \n, and \r\n as newlines.
    But splitlines() in Python 3 has a much larger list: for example, it also includes \v, \f.
    As such, this function will split lines across all Python versions.
    """
    return re.split(r"[\n\r]+", source)


def _get_statements(selection):
    """
    Process a multiline selection into a list of its top-level statements.
    This will remove empty newlines around and within the selection, dedent it,
    and split it using the result of `ast.parse()`.
    """

    # Remove blank lines within the selection to prevent the REPL from thinking the block is finished.
    lines = (line for line in split_lines(selection) if line.strip() != "")

    # Dedent the selection and parse it using the ast module.
    # Note that leading comments in the selection will be discarded during parsing.
    source = textwrap.dedent("\n".join(lines))
    tree = ast.parse(source)

    # We'll need the dedented lines to rebuild the selection.
    lines = split_lines(source)

    # Get the line ranges for top-level blocks returned from parsing the dedented text
    # and split the selection accordingly.
    # tree.body is a list of AST objects, which we rely on to extract top-level statements.
    # If we supported Python 3.8+ only we could use the lineno and end_lineno attributes of each object
    # to get the boundaries of each block.
    # However, earlier Python versions only have the lineno attribute, which is the range start position (1-indexed).
    # Therefore, to retrieve the end line of each block in a version-agnostic way we need to do
    # `end = next_block.lineno - 1`
    # for all blocks except the last one, which will will just run until the last line.
    ends = []
    for node in tree.body[1:]:
        line_end = node.lineno - 1
        # Special handling of decorators:
        # In Python 3.8 and higher, decorators are not taken into account in the value returned by lineno,
        # and we have to use the length of the decorator_list array to compute the actual start line.
        # Before that, lineno takes into account decorators, so this offset check is unnecessary.
        # Also, not all AST objects can have decorators.
        if hasattr(node, "decorator_list") and sys.version_info >= (3, 8):
            # Using getattr instead of node.decorator_list or pyright will complain about an unknown member.
            line_end -= len(getattr(node, "decorator_list"))
        ends.append(line_end)
    ends.append(len(lines))

    for node, end in zip(tree.body, ends):
        # Given this selection:
        # 1: if (m > 0 and
        # 2:        n < 3):
        # 3:     print('foo')
        # 4: value = 'bar'
        #
        # The first block would have lineno = 1,and the second block lineno = 4
        start = node.lineno - 1

        # Special handling of decorators similar to what's above.
        if hasattr(node, "decorator_list") and sys.version_info >= (3, 8):
            # Using getattr instead of node.decorator_list or pyright will complain about an unknown member.
            start -= len(getattr(node, "decorator_list"))
        block = "\n".join(lines[start:end])

        # If the block is multiline, add an extra newline character at its end.
        # This way, when joining blocks back together, there will be a blank line between each multiline statement
        # and no blank lines between single-line statements, or it would look like this:
        # >>> x = 22
        # >>>
        # >>> total = x + 30
        # >>>
        # Note that for the multiline parentheses case this newline is redundant,
        # since the closing parenthesis terminates the statement already.
        # This means that for this pattern we'll end up with:
        # >>> x = [
        # ...   1
        # ... ]
        # >>>
        # >>> y = [
        # ...   2
        # ...]
        if end - start > 1:
            block += "\n"

        yield block


def normalize_lines(selection):
    """
    Normalize the text selection received from the extension.

    If it is a single line selection, dedent it and append a newline and
    send it back to the extension.
    Otherwise, sanitize the multiline selection before returning it:
    split it in a list of top-level statements
    and add newlines between each of them so the REPL knows where each block ends.
    """
    try:
        # Parse the selection into a list of top-level blocks.
        # We don't differentiate between single and multiline statements
        # because it's not a perf bottleneck,
        # and the overhead from splitting and rejoining strings in the multiline case is one-off.
        statements = _get_statements(selection)

        # Insert a newline between each top-level statement, and append a newline to the selection.
        source = "\n".join(statements) + "\n"
        if selection[-2] == "}":
            source = source[:-1]
    except Exception:
        # If there's a problem when parsing statements,
        # append a blank line to end the block and send it as-is.
        source = selection + "\n\n"

    return source


top_level_nodes = []  # collection of top level nodes
top_level_to_min_difference = (
    {}
)  # dictionary of top level nodes to difference in relative to given code block to run
min_key = None
global_next_lineno = None
should_run_top_blocks = []


def check_exact_exist(top_level_nodes, start_line, end_line):
    exact_nodes = []
    for node in top_level_nodes:
        if node.lineno == start_line and node.end_lineno == end_line:
            exact_nodes.append(node)

    return exact_nodes


# Function that traverses the file and calculate the minimum viable top level block.
def traverse_file(wholeFileContent, start_line, end_line, was_highlighted):
    # Use ast module to parse content of the file.
    parsed_file_content = ast.parse(wholeFileContent)
    smart_code = ""

    for node in ast.iter_child_nodes(parsed_file_content):
        top_level_nodes.append(node)
        if hasattr(node, "body"):
            # Check if node has attribute body, then we have to go add child blocks.
            if (
                isinstance(node, ast.Module)
                or isinstance(node, ast.Interactive)
                or isinstance(node, ast.Expression)
                or isinstance(node, ast.FunctionDef)
                or isinstance(node, ast.AsyncFunctionDef)
                or isinstance(node, ast.ClassDef)
                or isinstance(node, ast.For)
                or isinstance(node, ast.AsyncFor)
                or isinstance(node, ast.While)
                or isinstance(node, ast.If)
                or isinstance(node, ast.With)
                or isinstance(node, ast.AsyncWith)
                or isinstance(node, ast.Try)
                or isinstance(node, ast.Lambda)
                or isinstance(node, ast.IfExp)
                or isinstance(node, ast.ExceptHandler)
            ):
                if isinstance(node.body, Iterable):
                    for child_nodes in node.body:
                        top_level_nodes.append(child_nodes)

    exact_nodes = check_exact_exist(top_level_nodes, start_line, end_line)

    # Just return the exact top level line, if present.
    if len(exact_nodes) > 0:
        for same_line_node in exact_nodes:
            should_run_top_blocks.append(same_line_node)
            smart_code += str(ast.get_source_segment(wholeFileContent, same_line_node))
            smart_code += "\n"
        return smart_code

    # With the given start_line and end_line number from VSCode,
    # Calculate the absolute difference between each of the top level block and given code (via line number)
    for top_node in ast.iter_child_nodes(parsed_file_content):
        top_level_block_start_line = top_node.lineno
        top_level_block_end_line = top_node.end_lineno
        abs_difference = abs(start_line - top_level_block_start_line) + abs(
            end_line - top_level_block_end_line
        )
        top_level_to_min_difference[top_node] = abs_difference
        # Handle case for same line run.
        if (
            start_line == top_level_block_start_line
            and end_line == top_level_block_end_line
        ):
            should_run_top_blocks.append(top_node)

            smart_code += str(ast.get_source_segment(wholeFileContent, top_node))
            smart_code += "\n"
            break  # Break out of the loop since we found the exact match.
        else:  # Case to apply smart selection for multiple line.
            if (
                start_line >= top_level_block_start_line
                and end_line <= top_level_block_end_line
            ):
                should_run_top_blocks.append(top_node)

                smart_code += str(ast.get_source_segment(wholeFileContent, top_node))
                smart_code += "\n"

    normalized_smart_result = normalize_lines(smart_code)

    return normalized_smart_result


# Look at the last top block added, find lineno for the next upcoming block,
# This will allow us to move cursor in VS Code.
def get_next_block_lineno():
    last_ran_lineno = int(should_run_top_blocks[-1].end_lineno)
    temp_next_lineno = int(should_run_top_blocks[-1].end_lineno)

    for reverse_node in top_level_nodes:
        if reverse_node.lineno > last_ran_lineno:
            temp_next_lineno = reverse_node.lineno
            break
    return temp_next_lineno - 1


if __name__ == "__main__":
    # Content is being sent from the extension as a JSON object.
    # Decode the data from the raw bytes.
    stdin = sys.stdin if sys.version_info < (3,) else sys.stdin.buffer
    raw = stdin.read()
    contents = json.loads(raw.decode("utf-8"))
    # Need to get information on whether there was a selection via Highlight.
    empty_Highlight = False
    if contents["emptyHighlight"] is True:
        empty_Highlight = True
    # We also get the activeEditor selection start line and end line from the typescript VS Code side.
    # Remember to add 1 to each of the received since vscode starts line counting from 0 .
    vscode_start_line = contents["startLine"] + 1
    vscode_end_line = contents["endLine"] + 1

    # Send the normalized code back to the extension in a JSON object.
    data = None
    which_line_next = 0
    # Depending on whether there was a explicit highlight, send smart selection or regular normalization.
    # Experiment also has to be enable to use smart selection.
    if empty_Highlight is True and contents["smartSendExperimentEnabled"] is True:
        normalized = traverse_file(
            contents["wholeFileContent"],
            vscode_start_line,
            vscode_end_line,
            not empty_Highlight,
        )
        which_line_next = (
            get_next_block_lineno()
        )  # Only figure out next block line number for smart shift+enter.
    else:
        normalized = normalize_lines(contents["code"])

    data = json.dumps({"normalized": normalized, "nextBlockLineno": which_line_next})
    stdout = sys.stdout if sys.version_info < (3,) else sys.stdout.buffer
    stdout.write(data.encode("utf-8"))
    stdout.close()
