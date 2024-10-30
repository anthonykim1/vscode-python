// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

import { inject, injectable } from 'inversify';
import { CancellationToken, Disposable, Event, EventEmitter, Terminal, TerminalShellExecution } from 'vscode';
import '../../common/extensions';
import { IInterpreterService } from '../../interpreter/contracts';
import { IServiceContainer } from '../../ioc/types';
import { captureTelemetry } from '../../telemetry';
import { EventName } from '../../telemetry/constants';
import { ITerminalAutoActivation } from '../../terminals/types';
import { ITerminalManager } from '../application/types';
import { _SCRIPTS_DIR } from '../process/internal/scripts/constants';
import { IConfigurationService, IDisposableRegistry } from '../types';
import {
    ITerminalActivator,
    ITerminalHelper,
    ITerminalService,
    TerminalCreationOptions,
    TerminalShellType,
} from './types';
import { traceVerbose } from '../../logging';

@injectable()
export class TerminalService implements ITerminalService, Disposable {
    private terminal?: Terminal;
    private terminalShellType!: TerminalShellType;
    private terminalClosed = new EventEmitter<void>();
    private terminalManager: ITerminalManager;
    private terminalHelper: ITerminalHelper;
    private terminalActivator: ITerminalActivator;
    private terminalAutoActivator: ITerminalAutoActivation;
    private readonly executeCommandListeners: Set<Disposable> = new Set();
    private _shellIntegrationEnabled: boolean = false;
    public get onDidCloseTerminal(): Event<void> {
        return this.terminalClosed.event.bind(this.terminalClosed);
    }

    constructor(
        @inject(IServiceContainer) private serviceContainer: IServiceContainer,
        private readonly options?: TerminalCreationOptions,
    ) {
        const disposableRegistry = this.serviceContainer.get<Disposable[]>(IDisposableRegistry);
        disposableRegistry.push(this);
        this.terminalHelper = this.serviceContainer.get<ITerminalHelper>(ITerminalHelper);
        this.terminalManager = this.serviceContainer.get<ITerminalManager>(ITerminalManager);
        this.terminalAutoActivator = this.serviceContainer.get<ITerminalAutoActivation>(ITerminalAutoActivation);
        this.terminalManager.onDidCloseTerminal(this.terminalCloseHandler, this, disposableRegistry);
        this.terminalActivator = this.serviceContainer.get<ITerminalActivator>(ITerminalActivator);
    }
    public dispose() {
        this.terminal?.dispose();

        if (this.executeCommandListeners && this.executeCommandListeners.size > 0) {
            this.executeCommandListeners.forEach((d) => {
                d?.dispose();
            });
        }
    }
    public async sendCommand(command: string, args: string[], _?: CancellationToken): Promise<void> {
        await this.ensureTerminal();
        const text = this.terminalHelper.buildCommandForTerminal(this.terminalShellType, command, args);
        if (!this.options?.hideFromUser) {
            this.terminal!.show(true);
        }

        await this.executeCommand(text);
    }
    /** @deprecated */
    public async sendText(text: string): Promise<void> {
        await this.ensureTerminal();
        if (!this.options?.hideFromUser) {
            this.terminal!.show(true);
        }
        this.terminal!.sendText(text);
    }
    public async executeCommand(commandLine: string): Promise<TerminalShellExecution | undefined> {
        const terminal = this.terminal!;
        if (!this.options?.hideFromUser) {
            terminal.show(true);
        }

        // If terminal was just launched, wait some time for shell integration to onDidChangeShellIntegration.
        if (!terminal.shellIntegration && !this._shellIntegrationEnabled) {
            const promise = new Promise<boolean>((resolve) => {
                const disposable = this.terminalManager.onDidChangeTerminalShellIntegration(() => {
                    this._shellIntegrationEnabled = true;
                    clearTimeout(timer); //racetimeout
                    disposable.dispose();
                    resolve(true);
                });
                const TIMEOUT_DURATION = 500;
                const timer = setTimeout(() => {
                    this._shellIntegrationEnabled = false;
                    disposable.dispose();
                    resolve(true);
                }, TIMEOUT_DURATION);
            });
            await promise;
        }

        if (terminal.shellIntegration) {
            // TODO: executeCommand would not execute command manually typed inside Python Terminal REPL.
            // We only run executeCommand when user shift+enter in .py file, and hence run command in terminal on user's behalf.
            const execution = terminal.shellIntegration.executeCommand(commandLine);
            this._shellIntegrationEnabled = true;
            return execution;
        } else {
            this._shellIntegrationEnabled = false;
            terminal.sendText(commandLine);
            traceVerbose(`Shell Integration is disabled, sendText: ${commandLine}`);
        }

        return undefined;
    }

    public async show(preserveFocus: boolean = true): Promise<void> {
        await this.ensureTerminal(preserveFocus);
        if (!this.options?.hideFromUser) {
            this.terminal!.show(preserveFocus);
        }
    }
    // TODO: Debt switch to Promise<Terminal> ---> breaks 20 tests
    public async ensureTerminal(preserveFocus: boolean = true): Promise<void> {
        if (this.terminal) {
            return;
        }
        this.terminalShellType = this.terminalHelper.identifyTerminalShell(this.terminal);
        this.terminal = this.terminalManager.createTerminal({
            name: this.options?.title || 'Python',
            hideFromUser: this.options?.hideFromUser,
        });
        this.terminalAutoActivator.disableAutoActivation(this.terminal);

        // Sometimes the terminal takes some time to start up before it can start accepting input.
        await new Promise((resolve) => setTimeout(resolve, 100));

        await this.terminalActivator.activateEnvironmentInTerminal(this.terminal, {
            resource: this.options?.resource,
            preserveFocus,
            interpreter: this.options?.interpreter,
            hideFromUser: this.options?.hideFromUser,
        });

        if (!this.options?.hideFromUser) {
            this.terminal.show(preserveFocus);
        }

        this.sendTelemetry().ignoreErrors();
        return;
    }
    private terminalCloseHandler(terminal: Terminal) {
        if (terminal === this.terminal) {
            this.terminalClosed.fire();
            this.terminal = undefined;
        }
    }

    private async sendTelemetry() {
        const pythonPath = this.serviceContainer
            .get<IConfigurationService>(IConfigurationService)
            .getSettings(this.options?.resource).pythonPath;
        const interpreterInfo =
            this.options?.interpreter ||
            (await this.serviceContainer
                .get<IInterpreterService>(IInterpreterService)
                .getInterpreterDetails(pythonPath));
        const pythonVersion = interpreterInfo && interpreterInfo.version ? interpreterInfo.version.raw : undefined;
        const interpreterType = interpreterInfo ? interpreterInfo.envType : undefined;
        captureTelemetry(EventName.TERMINAL_CREATE, {
            terminal: this.terminalShellType,
            pythonVersion,
            interpreterType,
        });
    }
}
