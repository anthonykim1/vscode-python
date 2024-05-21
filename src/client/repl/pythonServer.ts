// eslint-disable-next-line max-classes-per-file
import * as path from 'path';
import * as ch from 'child_process';
import * as rpc from 'vscode-jsonrpc/node';
import { Disposable, window } from 'vscode';
import { EXTENSION_ROOT_DIR } from '../constants';
import { traceError, traceLog } from '../logging';

const SERVER_PATH = path.join(EXTENSION_ROOT_DIR, 'python_files', 'python_server.py');
let serverInstance: PythonServer | undefined;

export interface PythonServer extends Disposable {
    execute(code: string): Promise<string>;
    interrupt(): void;
    input(): void;
    checkValidCommand(code: string): Promise<string>;
}

class PythonServerImpl implements Disposable {
    private readonly disposables: Disposable[] = [];

    constructor(
        private connection: rpc.MessageConnection,
        private pythonServer: ch.ChildProcess,
        private interpreter: string,
    ) {
        this.initialize();
        this.input();
    }

    private initialize(): void {
        this.disposables.push(
            this.connection.onNotification('log', (message: string) => {
                console.log('Log:', message);
            }),
        );
        this.connection.listen();
    }

    // Register input handler
    public input(): void {
        // Register input request handler
        this.connection.onRequest('input', async (request) => {
            // Ask for user input via popup quick input, send it back to Python
            let userPrompt = 'Enter your input here: ';
            if (request && request.prompt) {
                userPrompt = request.prompt;
            }
            const input = await window.showInputBox({
                title: 'Input Request',
                prompt: userPrompt,
                ignoreFocusOut: true,
            });
            return { userInput: input };
        });
    }

    public execute(code: string): Promise<string> {
        return this.connection.sendRequest('execute', code);
    }

    public interrupt(): void {
        // Passing SIGINT to interrupt only would work for Mac and Linux
        if (this.pythonServer.kill('SIGINT')) {
            traceLog('Python REPL server interrupted');
        } else {
            // TODO: Handle interrupt for windows
            // Run python_files/ctrlc.py with 12345 as argument
            // TODO: properly get PID from Python Server
            const ctrlc = ch.spawn(this.interpreter, [
                path.join(EXTENSION_ROOT_DIR, 'python_files', 'ctrlc.py'),
                '12345',
            ]);
            ctrlc.on('exit', (code) => {
                if (code === 0) {
                    traceLog('Windows Python REPL server interrupted successfully with exit code 0');
                } else {
                    traceLog('Windows Python REPL interrupt may have failed');
                }
            });
        }
    }

    public async checkValidCommand(code: string): Promise<string> {
        return this.connection.sendRequest('check_valid_command', code);
    }

    public dispose(): void {
        this.connection.sendNotification('exit');
        this.disposables.forEach((d) => d.dispose());
        this.connection.dispose();
    }
}

export function createPythonServer(interpreter: string[]): PythonServer {
    if (serverInstance) {
        return serverInstance;
    }

    const pythonServer = ch.spawn(interpreter[0], [...interpreter.slice(1), SERVER_PATH]);

    pythonServer.stderr.on('data', (data) => {
        traceError(data.toString());
    });
    pythonServer.on('exit', (code) => {
        traceError(`Python server exited with code ${code}`);
    });
    pythonServer.on('error', (err) => {
        traceError(err);
    });
    const connection = rpc.createMessageConnection(
        new rpc.StreamMessageReader(pythonServer.stdout),
        new rpc.StreamMessageWriter(pythonServer.stdin),
    );
    const ourPythonServerImpl = new PythonServerImpl(connection, pythonServer, interpreter[0]);
    serverInstance = ourPythonServerImpl;
    return ourPythonServerImpl;
}
