import * as vscode from 'vscode';
import { NovaForgeAPI, ReviewResult, ReviewFinding, ReviewSeverity } from '../client/api';

export interface ReviewOptions {
  reviewType?: string;
  filePath?: string;
  code?: string;
  selection?: vscode.Range;
}

export class ReviewProvider {
  private api: NovaForgeAPI;
  private diagnosticCollection: vscode.DiagnosticCollection;
  private reviewPanel: vscode.WebviewPanel | undefined;
  private static readonly SEVERITY_MAP: Record<ReviewSeverity, vscode.DiagnosticSeverity> = {
    critical: vscode.DiagnosticSeverity.Error,
    error: vscode.DiagnosticSeverity.Error,
    warning: vscode.DiagnosticSeverity.Warning,
    info: vscode.DiagnosticSeverity.Information,
    hint: vscode.DiagnosticSeverity.Hint
  };

  constructor(api: NovaForgeAPI) {
    this.api = api;
    this.diagnosticCollection = vscode.languages.createDiagnosticCollection('novaforge-review');
  }

  async reviewFile(filePath?: string): Promise<void> {
    const targetPath = filePath || this.getActiveFilePath();
    if (!targetPath) {
      vscode.window.showWarningMessage('No file to review. Open a file first.');
      return;
    }

    const progressOptions: vscode.ProgressOptions = {
      location: vscode.ProgressLocation.Notification,
      title: 'NovaForge Code Review',
      cancellable: true
    };

    await vscode.window.withProgress(progressOptions, async (progress, token) => {
      progress.report({ message: 'Analyzing code...' });

      try {
        const result = await this.api.review(targetPath);
        this.showReviewResults(result, targetPath);
      } catch (error) {
        if (token.isCancellationRequested) {
          return;
        }
        vscode.window.showErrorMessage(
          `Review failed: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    });
  }

  async reviewSelection(code: string, filePath?: string): Promise<void> {
    const targetPath = filePath || this.getActiveFilePath();
    if (!targetPath) {
      return;
    }

    const progressOptions: vscode.ProgressOptions = {
      location: vscode.ProgressLocation.Notification,
      title: 'NovaForge Review Selection',
      cancellable: true
    };

    await vscode.window.withProgress(progressOptions, async (progress, token) => {
      progress.report({ message: 'Reviewing selection...' });

      try {
        const result = await this.api.review(targetPath, code);
        this.showReviewResults(result, targetPath);
      } catch (error) {
        if (token.isCancellationRequested) {
          return;
        }
        vscode.window.showErrorMessage(
          `Review failed: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    });
  }

  async reviewPR(prNumber: number | string): Promise<void> {
    const prStr = typeof prNumber === 'number' ? prNumber.toString() : prNumber;

    const progressOptions: vscode.ProgressOptions = {
      location: vscode.ProgressLocation.Notification,
      title: `NovaForge PR Review #${prStr}`,
      cancellable: true
    };

    await vscode.window.withProgress(progressOptions, async (progress, token) => {
      progress.report({ message: `Reviewing pull request #${prStr}...` });

      try {
        const result = await this.api.review(undefined, undefined, `pr:${prStr}`);
        this.showReviewResults(result, `PR #${prStr}`);
      } catch (error) {
        if (token.isCancellationRequested) {
          return;
        }
        vscode.window.showErrorMessage(
          `PR review failed: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    });
  }

  showReviewResults(result: ReviewResult, context: string): void {
    this.updateDiagnostics(result, context);
    this.showReviewPanel(result, context);
  }

  private updateDiagnostics(result: ReviewResult, filePath: string): void {
    const diagnostics: vscode.Diagnostic[] = [];

    for (const finding of result.findings) {
      const line = Math.max(0, (finding.line || 1) - 1);
      const column = Math.max(0, (finding.column || 0));
      const endLine = finding.endLine ? Math.max(0, finding.endLine - 1) : line;
      const endColumn = finding.endColumn || column + 1;

      const range = new vscode.Range(
        new vscode.Position(line, column),
        new vscode.Position(endLine, endColumn)
      );

      const severity = ReviewProvider.SEVERITY_MAP[finding.severity] || vscode.DiagnosticSeverity.Warning;

      const diagnostic = new vscode.Diagnostic(
        range,
        finding.message,
        severity
      );

      diagnostic.source = 'NovaForge';
      diagnostic.code = finding.rule || finding.code;

      if (finding.suggestedFix) {
        diagnostic.relatedInformation = [
          new vscode.DiagnosticRelatedInformation(
            new vscode.Location(vscode.Uri.file(filePath), range),
            `Suggested fix: ${finding.suggestedFix}`
          )
        ];
      }

      diagnostics.push(diagnostic);
    }

    const fileUri = vscode.Uri.file(filePath);
    this.diagnosticCollection.set(fileUri, diagnostics);
  }

  private showReviewPanel(result: ReviewResult, context: string): void {
    if (this.reviewPanel) {
      this.reviewPanel.webview.html = this.getReviewHtml(result, context);
      this.reviewPanel.reveal(vscode.ViewColumn.Two);
      return;
    }

    this.reviewPanel = vscode.window.createWebviewPanel(
      'novaforge-review',
      `NovaForge Review: ${context}`,
      vscode.ViewColumn.Two,
      {
        enableScripts: true,
        retainContextWhenHidden: true
      }
    );

    this.reviewPanel.webview.html = this.getReviewHtml(result, context);

    this.reviewPanel.webview.onDidReceiveMessage(
      async (message) => {
        switch (message.type) {
          case 'applyFix':
            await this.applyFix(message.finding);
            break;
          case 'goToLine':
            await this.goToLine(message.filePath, message.line, message.column);
            break;
          case 'dismissFinding':
            this.dismissFinding(message.filePath, message.line);
            break;
        }
      },
      undefined,
      []
    );

    this.reviewPanel.onDidDispose(() => {
      this.reviewPanel = undefined;
    });
  }

  private getReviewHtml(result: ReviewResult, context: string): string {
    const summary = result.summary || 'Review complete';
    const findings = result.findings || [];

    const criticalCount = findings.filter(f => f.severity === 'critical' || f.severity === 'error').length;
    const warningCount = findings.filter(f => f.severity === 'warning').length;
    const infoCount = findings.filter(f => f.severity === 'info' || f.severity === 'hint').length;

    const findingsHtml = findings.map((finding, index) => {
      const severityClass = this.getSeverityClass(finding.severity);
      const location = finding.line ? `Line ${finding.line}` : '';
      const fixButton = finding.suggestedFix
        ? `<button class="fix-btn" onclick="applyFix(${index})">Apply Fix</button>`
        : '';
      const goToButton = finding.line
        ? `<button class="go-btn" onclick="goToLine('${finding.file || context}', ${finding.line}, ${finding.column || 0})">Go to Line</button>`
        : '';

      return `
        <div class="finding ${severityClass}">
          <div class="finding-header">
            <span class="severity-badge ${severityClass}">${finding.severity.toUpperCase()}</span>
            <span class="finding-rule">${finding.rule || 'General'}</span>
            <span class="finding-location">${location}</span>
          </div>
          <div class="finding-message">${this.escapeHtml(finding.message)}</div>
          ${finding.suggestedFix ? `<div class="finding-fix"><pre>${this.escapeHtml(finding.suggestedFix)}</pre></div>` : ''}
          <div class="finding-actions">
            ${fixButton}
            ${goToButton}
            <button class="dismiss-btn" onclick="dismissFinding(${index})">Dismiss</button>
          </div>
        </div>
      `;
    }).join('\n');

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NovaForge Review</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      padding: 16px;
      line-height: 1.5;
    }
    .summary {
      padding: 12px 16px;
      background: var(--vscode-editor-inactiveSelectionBackground);
      border-radius: 6px;
      margin-bottom: 16px;
    }
    .summary h2 { margin-bottom: 8px; font-size: 16px; }
    .stats { display: flex; gap: 16px; margin-top: 8px; }
    .stat { display: flex; align-items: center; gap: 4px; font-size: 13px; }
    .stat-dot {
      width: 8px; height: 8px; border-radius: 50%;
    }
    .stat-dot.critical { background: var(--vscode-errorForeground); }
    .stat-dot.warning { background: var(--vscode-editorWarning-foreground); }
    .stat-dot.info { background: var(--vscode-editorInfo-foreground); }
    .findings { display: flex; flex-direction: column; gap: 8px; }
    .finding {
      border: 1px solid var(--vscode-widget-border);
      border-radius: 6px;
      padding: 12px;
    }
    .finding.critical { border-left: 3px solid var(--vscode-errorForeground); }
    .finding.warning { border-left: 3px solid var(--vscode-editorWarning-foreground); }
    .finding.info { border-left: 3px solid var(--vscode-editorInfo-foreground); }
    .finding-header {
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 6px; font-size: 12px;
    }
    .severity-badge {
      padding: 2px 6px; border-radius: 3px;
      font-weight: bold; font-size: 11px;
    }
    .severity-badge.critical { background: var(--vscode-errorForeground); color: white; }
    .severity-badge.error { background: var(--vscode-errorForeground); color: white; }
    .severity-badge.warning { background: var(--vscode-editorWarning-foreground); color: black; }
    .severity-badge.info { background: var(--vscode-editorInfo-foreground); color: black; }
    .finding-rule { color: var(--vscode-descriptionForeground); }
    .finding-location { color: var(--vscode-descriptionForeground); margin-left: auto; }
    .finding-message { font-size: 14px; }
    .finding-fix {
      margin-top: 8px; padding: 8px;
      background: var(--vscode-editor-background);
      border-radius: 4px; font-size: 13px;
    }
    .finding-fix pre {
      white-space: pre-wrap;
      font-family: var(--vscode-editor-font-family);
    }
    .finding-actions { margin-top: 8px; display: flex; gap: 8px; }
    .finding-actions button {
      padding: 4px 10px; border-radius: 4px; border: 1px solid var(--vscode-widget-border);
      background: var(--vscode-button-background); color: var(--vscode-button-foreground);
      cursor: pointer; font-size: 12px;
    }
    .finding-actions button:hover { background: var(--vscode-button-hoverBackground); }
    .fix-btn { background: var(--vscode-quickInputBackground) !important; }
    .dismiss-btn { background: transparent !important; color: var(--vscode-descriptionForeground) !important; }
    .no-findings {
      text-align: center; padding: 40px; color: var(--vscode-descriptionForeground);
    }
  </style>
</head>
<body>
  <div class="summary">
    <h2>Review: ${this.escapeHtml(context)}</h2>
    <p>${this.escapeHtml(summary)}</p>
    <div class="stats">
      <div class="stat"><span class="stat-dot critical"></span> ${criticalCount} Critical</div>
      <div class="stat"><span class="stat-dot warning"></span> ${warningCount} Warnings</div>
      <div class="stat"><span class="stat-dot info"></span> ${infoCount} Info</div>
    </div>
  </div>
  <div class="findings">
    ${findingsHtml || '<div class="no-findings">No findings. Code looks good!</div>'}
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const findings = ${JSON.stringify(findings)};

    function applyFix(index) {
      vscode.postMessage({ type: 'applyFix', finding: findings[index] });
    }

    function goToLine(filePath, line, column) {
      vscode.postMessage({ type: 'goToLine', filePath, line, column });
    }

    function dismissFinding(index) {
      vscode.postMessage({ type: 'dismissFinding', filePath: findings[index]?.file, line: findings[index]?.line });
    }
  </script>
</body>
</html>`;
  }

  async applyFix(finding: ReviewFinding): Promise<void> {
    if (!finding.suggestedFix) {
      vscode.window.showWarningMessage('No suggested fix available for this finding.');
      return;
    }

    const filePath = finding.file || this.getActiveFilePath();
    if (!filePath) {
      return;
    }

    try {
      const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
      const edit = new vscode.WorkspaceEdit();

      const line = Math.max(0, (finding.line || 1) - 1);
      const endLine = finding.endLine ? Math.max(0, finding.endLine - 1) : line;

      const range = new vscode.Range(
        new vscode.Position(line, finding.column || 0),
        new vscode.Position(endLine, finding.endColumn || document.lineAt(line).text.length)
      );

      edit.replace(vscode.Uri.file(filePath), range, finding.suggestedFix);

      const confirmed = await vscode.window.showWarningMessage(
        `Apply suggested fix for: ${finding.rule || 'this finding'}?`,
        { modal: true },
        'Apply',
        'Cancel'
      );

      if (confirmed === 'Apply') {
        const success = await vscode.workspace.applyEdit(edit, true);
        if (success) {
          vscode.window.showInformationMessage('Fix applied successfully.');
        } else {
          vscode.window.showErrorMessage('Failed to apply fix.');
        }
      }
    } catch (error) {
      vscode.window.showErrorMessage(
        `Failed to apply fix: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async goToLine(filePath: string, line: number, column?: number): Promise<void> {
    try {
      const uri = vscode.Uri.file(filePath);
      const document = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(document);

      const position = new vscode.Position(
        Math.max(0, line - 1),
        Math.max(0, (column || 0))
      );

      editor.selection = new vscode.Selection(position, position);
      editor.revealRange(
        new vscode.Range(position, position),
        vscode.TextEditorRevealType.InCenter
      );
    } catch (error) {
      vscode.window.showErrorMessage(
        `Failed to navigate: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private dismissFinding(filePath: string | undefined, line: number | undefined): void {
    if (filePath && line !== undefined) {
      const uri = vscode.Uri.file(filePath);
      const currentDiagnostics = this.diagnosticCollection.get(uri) || [];
      const filtered = currentDiagnostics.filter(d => d.range.start.line !== Math.max(0, line - 1));
      this.diagnosticCollection.set(uri, filtered);
    }
  }

  private getSeverityClass(severity: ReviewSeverity): string {
    switch (severity) {
      case 'critical':
      case 'error':
        return 'critical';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  private getActiveFilePath(): string | undefined {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return undefined;
    }
    return editor.document.uri.fsPath;
  }

  dispose(): void {
    this.diagnosticCollection.dispose();
    if (this.reviewPanel) {
      this.reviewPanel.dispose();
      this.reviewPanel = undefined;
    }
  }
}
