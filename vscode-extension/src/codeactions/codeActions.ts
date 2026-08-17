import * as vscode from 'vscode';
import { NovaForgeAPI } from '../client/api';

export interface CodeActionItem extends vscode.CodeAction {
  novaforgeAction?: string;
  apiResult?: unknown;
}

export class NovaForgeCodeActionProvider implements vscode.CodeActionProvider {
  static readonly providedCodeActionKinds: vscode.CodeActionKind[] = [
    vscode.CodeActionKind.QuickFix,
    vscode.CodeActionKind.Refactor
  ];

  private api: NovaForgeAPI;

  constructor(api: NovaForgeAPI) {
    this.api = api;
  }

  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    const selectionText = document.getText(range);
    if (!selectionText || selectionText.trim().length === 0) {
      return actions;
    }

    const language = document.languageId;
    const filePath = document.uri.fsPath;

    actions.push(
      this.createAction(
        'Explain Code',
        'novaforge.explain',
        vscode.CodeActionKind.QuickFix,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Fix Code',
        'novaforge.fix',
        vscode.CodeActionKind.QuickFix,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Refactor Code',
        'novaforge.refactor',
        vscode.CodeActionKind.Refactor,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Optimize Code',
        'novaforge.optimize',
        vscode.CodeActionKind.Refactor,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Generate Tests',
        'novaforge.generateTests',
        vscode.CodeActionKind.Refactor,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Generate Documentation',
        'novaforge.generateDocs',
        vscode.CodeActionKind.Refactor,
        filePath,
        language,
        selectionText,
        range
      )
    );

    actions.push(
      this.createAction(
        'Security Review',
        'novaforge.securityReview',
        vscode.CodeActionKind.QuickFix,
        filePath,
        language,
        selectionText,
        range
      )
    );

    if (context.diagnostics.length > 0) {
      for (const diagnostic of context.diagnostics) {
        actions.push(
          this.createDiagnosticAction(
            'Fix with NovaForge',
            'novaforge.fix',
            filePath,
            language,
            selectionText,
            range,
            diagnostic
          )
        );
      }
    }

    return actions.filter(action => {
      if (token.isCancellationRequested) {
        return false;
      }
      return true;
    });
  }

  private createAction(
    title: string,
    command: string,
    kind: vscode.CodeActionKind,
    filePath: string,
    language: string,
    code: string,
    range: vscode.Range
  ): CodeActionItem {
    const action = new vscode.CodeAction(title, kind) as CodeActionItem;
    action.novaforgeAction = command;

    action.command = {
      command,
      title,
      arguments: [
        {
          filePath,
          language,
          code,
          startLine: range.start.line + 1,
          endLine: range.end.line + 1
        }
      ]
    };

    action.isPreferred = kind === vscode.CodeActionKind.QuickFix;

    return action;
  }

  private createDiagnosticAction(
    title: string,
    command: string,
    filePath: string,
    language: string,
    code: string,
    range: vscode.Range,
    diagnostic: vscode.Diagnostic
  ): CodeActionItem {
    const action = new vscode.CodeAction(title, vscode.CodeActionKind.QuickFix) as CodeActionItem;
    action.novaforgeAction = command;
    action.diagnostics = [diagnostic];

    action.command = {
      command,
      title,
      arguments: [
        {
          filePath,
          language,
          code,
          startLine: range.start.line + 1,
          endLine: range.end.line + 1,
          diagnosticMessage: diagnostic.message,
          diagnosticSource: diagnostic.source
        }
      ]
    };

    action.diagnostics = [diagnostic];
    action.isPreferred = true;

    return action;
  }

  async executeAction(
    action: string,
    args: {
      filePath: string;
      language: string;
      code: string;
      startLine?: number;
      endLine?: number;
      diagnosticMessage?: string;
    }
  ): Promise<void> {
    const progressOptions: vscode.ProgressOptions = {
      location: vscode.ProgressLocation.Notification,
      title: `NovaForge: ${action}`,
      cancellable: true
    };

    await vscode.window.withProgress(progressOptions, async (progress, token) => {
      progress.report({ message: `Processing ${action}...` });

      try {
        const result = await this.api.codeAction(
          action,
          args.filePath,
          args.language,
          args.code,
          args.startLine,
          args.endLine
        );

        if (token.isCancellationRequested) {
          return;
        }

        await this.handleActionResult(action, result, args.filePath);
      } catch (error) {
        if (token.isCancellationRequested) {
          return;
        }
        vscode.window.showErrorMessage(
          `${action} failed: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    });
  }

  private async handleActionResult(
    action: string,
    result: unknown,
    filePath: string
  ): Promise<void> {
    if (!result || typeof result !== 'object') {
      vscode.window.showInformationMessage(`${action} completed.`);
      return;
    }

    const response = result as {
      result?: string;
      explanation?: string;
      suggestedCode?: string;
      diff?: string;
      diagnostics?: Array<{ message: string; severity: string }>;
    };

    if (response.suggestedCode) {
      const apply = await vscode.window.showInformationMessage(
        `${action}: Apply suggested changes?`,
        'Apply',
        'Preview',
        'Dismiss'
      );

      if (apply === 'Apply') {
        await this.applySuggestedCode(response.suggestedCode, filePath);
      } else if (apply === 'Preview') {
        const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
        const currentCode = document.getText();
        await this.previewDiff(currentCode, response.suggestedCode, filePath);
      }
    } else if (response.result || response.explanation) {
      const message = response.result || response.explanation;
      const choice = await vscode.window.showInformationMessage(
        message as string,
        'Copy',
        'Dismiss'
      );
      if (choice === 'Copy') {
        await vscode.env.clipboard.writeText(message as string);
        vscode.window.showInformationMessage('Copied to clipboard.');
      }
    }
  }

  private async applySuggestedCode(code: string, filePath: string): Promise<void> {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
    const fullRange = new vscode.Range(
      document.positionAt(0),
      document.positionAt(document.getText().length)
    );

    const edit = new vscode.WorkspaceEdit();
    edit.replace(document.uri, fullRange, code);

    const confirmed = await vscode.window.showWarningMessage(
      'Apply NovaForge suggested changes?',
      { modal: true },
      'Apply',
      'Cancel'
    );

    if (confirmed === 'Apply') {
      const success = await vscode.workspace.applyEdit(edit, true);
      if (success) {
        vscode.window.showInformationMessage('Changes applied successfully.');
      } else {
        vscode.window.showErrorMessage('Failed to apply changes.');
      }
    }
  }

  private async previewDiff(
    original: string,
    proposed: string,
    filePath: string
  ): Promise<void> {
    const fs = require('fs');
    const os = require('os');
    const path = require('path');

    const tempDir = os.tmpdir();
    const originalPath = path.join(tempDir, `novaforge-orig-${Date.now()}.tmp`);
    const proposedPath = path.join(tempDir, `novaforge-new-${Date.now()}.tmp`);

    const origUri = vscode.Uri.file(originalPath);
    const propUri = vscode.Uri.file(proposedPath);

    try {
      await vscode.workspace.fs.writeFile(origUri, Buffer.from(original, 'utf8'));
      await vscode.workspace.fs.writeFile(propUri, Buffer.from(proposed, 'utf8'));

      await vscode.commands.executeCommand(
        'vscode.diff',
        origUri,
        propUri,
        `NovaForge: ${filePath}`,
        { preserveFocus: false }
      );

      const choice = await vscode.window.showInformationMessage(
        'Apply these changes?',
        'Apply',
        'Cancel'
      );

      if (choice === 'Apply') {
        await this.applySuggestedCode(proposed, filePath);
      }
    } finally {
      try { await vscode.workspace.fs.delete(origUri); } catch { /* cleanup */ }
      try { await vscode.workspace.fs.delete(propUri); } catch { /* cleanup */ }
    }
  }
}
