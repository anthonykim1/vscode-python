import {
    NotebookCellData,
    NotebookCellKind,
    NotebookDocument,
    NotebookEdit,
    TextEditor,
    workspace,
    WorkspaceEdit,
} from 'vscode';
import { getActiveResource } from '../common/vscodeApis/windowApis';
import { getConfiguration } from '../common/vscodeApis/workspaceApis';
import { getMultiLineSelectionText, getSingleLineSelectionText } from '../terminals/codeExecution/helper';

export function getSendToNativeREPLSetting(): boolean {
    const uri = getActiveResource();
    const configuration = getConfiguration('python', uri);
    return configuration.get<boolean>('REPL.sendToNativeREPL', false);
}

export async function getSelectedTextToExecute(textEditor: TextEditor): Promise<string | undefined> {
    if (!textEditor) {
        return undefined;
    }

    const { selection } = textEditor;
    let code: string;

    if (selection.isEmpty) {
        code = textEditor.document.lineAt(selection.start.line).text;
    } else if (selection.isSingleLine) {
        code = getSingleLineSelectionText(textEditor);
    } else {
        code = getMultiLineSelectionText(textEditor);
    }

    return code;
}

/**
 * Function that adds cell to notebook.
 * This function will only get called when notebook document is defined.
 * @param code
 *
 */
export async function addCellToNotebook(notebookDocument: NotebookDocument, code: string): Promise<void> {
    const notebookCellData = new NotebookCellData(NotebookCellKind.Code, code as string, 'python');
    const { cellCount } = notebookDocument!;
    // Add new cell to interactive window document
    const notebookEdit = NotebookEdit.insertCells(cellCount, [notebookCellData]);
    const workspaceEdit = new WorkspaceEdit();
    workspaceEdit.set(notebookDocument!.uri, [notebookEdit]);
    await workspace.applyEdit(workspaceEdit);
}

export function isMultiLineText(textEditor: TextEditor | undefined): boolean {
    return (textEditor?.document?.lineCount ?? 0) > 1;
}
