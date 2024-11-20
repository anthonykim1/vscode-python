// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

import {
    CancellationToken,
    CodeAction,
    CodeActionContext,
    CodeActionKind,
    CodeActionProvider,
    Command,
    ProviderResult,
    Range,
    Selection,
    TextDocument,
} from 'vscode';
// Look at status bar option too.
export class PythonNativeReplSuggestionProvider implements CodeActionProvider {
    public provideCodeActions(
        document: TextDocument,
        range: Range | Selection,
        context: CodeActionContext,
        token: CancellationToken,
    ): ProviderResult<(CodeAction | Command)[]> {
        const nativeReplCodeAction = new CodeAction('Run in Native REPL', this.getFixAsNativeReplSuggestion());
        return [nativeReplCodeAction];
    }

    private getFixAsNativeReplSuggestion(): CodeAction {
        const nativeReplSuggestion = new CodeAction('Run in Native REPL', CodeActionKind.QuickFix);
        return nativeReplSuggestion;
    }

    public resolveCodeAction?(codeAction: CodeAction, token: CancellationToken): ProviderResult<CodeAction> {
        throw new Error('Method not implemented.');
    }
}
