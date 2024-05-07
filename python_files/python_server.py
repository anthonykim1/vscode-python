import debugpy
debugpy.connect(5678)
import sys
import json
import contextlib
import io
from threading import Thread
import traceback

is_interrupted = False
EXECUTE_QUEUE = []
STDIN = sys.stdin
STDOUT = sys.stdout
STDERR = sys.stderr

def send_message(msg: str):
    length_msg = len(msg)
    STDOUT.buffer.write(
        f"Content-Length: {length_msg}\r\n\r\n{msg}".encode(encoding="utf-8")
    )
    STDOUT.buffer.flush()


def print_log(msg: str):
    send_message(json.dumps({"jsonrpc": "2.0", "method": "log", "params": msg}))


def send_response(response: str, response_id: int):
    send_message(json.dumps({"jsonrpc": "2.0", "id": response_id, "result": response}))


def exec_function(user_input):

    try:
        compile(user_input, "<stdin>", "eval")
    except SyntaxError:
        return exec
    return eval

# have to run execute in different thread
# interrupt will kill the thread.

def execute():

    while EXECUTE_QUEUE:
        request = EXECUTE_QUEUE.pop(0)

        str_output = CustomIO("<stdout>", encoding="utf-8")
        str_error = CustomIO("<stderr>", encoding="utf-8")

        with redirect_io("stdout", str_output):
            with redirect_io("stderr", str_error):
                str_input = CustomIO("<stdin>", encoding="utf-8", newline="\n")
                with redirect_io("stdin", str_input):
                    user_output_globals = exec_user_input(
                        request["id"], request["params"], user_globals
                    )
        send_response(str_output.get_value(), request["id"])
        user_globals.update(user_output_globals)


def exec_user_input(request_id, user_input, user_globals):


    # have to do redirection
    user_input = user_input[0] if isinstance(user_input, list) else user_input
    user_globals = user_globals.copy()

    try:
        callable = exec_function(user_input)
        retval = callable(user_input, user_globals)
        if retval is not None:
            print(retval)
    except Exception:
        print(traceback.format_exc())
    return user_globals


class CustomIO(io.TextIOWrapper):
    """Custom stream object to replace stdio."""

    name = None

    def __init__(self, name, encoding="utf-8", newline=None):
        self._buffer = io.BytesIO()
        self._buffer.name = name
        super().__init__(self._buffer, encoding=encoding, newline=newline)

    def close(self):
        """Provide this close method which is used by some tools."""
        # This is intentionally empty.

    def get_value(self) -> str:
        """Returns value from the buffer as string."""
        self.seek(0)
        return self.read()


@contextlib.contextmanager
def redirect_io(stream: str, new_stream):
    """Redirect stdio streams to a custom stream."""
    old_stream = getattr(sys, stream)
    setattr(sys, stream, new_stream)
    yield
    setattr(sys, stream, old_stream)


def get_headers():
    headers = {}
    while line := STDIN.readline().strip():
        name, value = line.split(":", 1)
        headers[name] = value.strip()
    return headers


# execute_queue.append({"id": 1, "params": "print('hello')"})

if __name__ == "__main__":
    user_globals = {}
    thread = None

    while not STDIN.closed:
        try:
            headers = get_headers()
            content_length = int(headers.get("Content-Length", 0))
# just one execute thread
# queue execute items on that thread
            if content_length:
                request_text = STDIN.read(content_length) # make sure Im getting right content
                request_json = json.loads(request_text)
                if request_json["method"] == "execute":
                    EXECUTE_QUEUE.append(request_json)
                    if thread is None or not thread.is_alive():
                        thread = Thread(target=execute)
                        thread.start()
                    # execute_queue.append(request_json) # instead of directly calling execute, create another thread and run execute inside that thread
                elif request_json["method"] == "interrupt":

                    # kill 'thread'
                    # thread._stop() # THIS IS NOT WORKING


                    # set thread as empty
                    thread = None
                    # clear execute queue
                    EXECUTE_QUEUE.clear()

                elif request_json["method"] == "exit":
                    sys.exit(0)

        except Exception as e:
            print_log(str(e))


# problem is not able to send interrupt to right thread or kill the thread directly.