import * as vscode from 'vscode';

export interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  content: string;
  changes: DiffLine[];
}

export interface DiffLine {
  type: 'add' | 'remove' | 'context';
  content: string;
  oldLineNum: number | null;
  newLineNum: number | null;
}

export interface ParsedDiff {
  hunks: DiffHunk[];
  addedLines: number;
  removedLines: number;
  filePath?: string;
}

export class DiffManager {

  parseDiff(diffText: string, filePath?: string): ParsedDiff {
    const lines = diffText.split('\n');
    const hunks: DiffHunk[] = [];
    let currentHunk: DiffHunk | null = null;
    let addedLines = 0;
    let removedLines = 0;

    for (const line of lines) {
      const hunkMatch = line.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/);

      if (hunkMatch) {
        if (currentHunk) {
          hunks.push(currentHunk);
        }

        currentHunk = {
          oldStart: parseInt(hunkMatch[1], 10),
          oldLines: hunkMatch[2] ? parseInt(hunkMatch[2], 10) : 1,
          newStart: parseInt(hunkMatch[3], 10),
          newLines: hunkMatch[4] ? parseInt(hunkMatch[4], 10) : 1,
          content: line,
          changes: []
        };
        continue;
      }

      if (!currentHunk) {
        continue;
      }

      if (line.startsWith('+')) {
        addedLines++;
        currentHunk.changes.push({
          type: 'add',
          content: line.substring(1),
          oldLineNum: null,
          newLineNum: currentHunk.newStart + currentHunk.changes.filter(c => c.type !== 'remove').length
        });
      } else if (line.startsWith('-')) {
        removedLines++;
        currentHunk.changes.push({
          type: 'remove',
          content: line.substring(1),
          oldLineNum: currentHunk.oldStart + currentHunk.changes.filter(c => c.type !== 'add').length,
          newLineNum: null
        });
      } else if (line.startsWith(' ')) {
        currentHunk.changes.push({
          type: 'context',
          content: line.substring(1),
          oldLineNum: currentHunk.oldStart + currentHunk.changes.filter(c => c.type !== 'add').length,
          newLineNum: currentHunk.newStart + currentHunk.changes.filter(c => c.type !== 'remove').length
        });
      }
    }

    if (currentHunk) {
      hunks.push(currentHunk);
    }

    return { hunks, addedLines, removedLines, filePath };
  }

  async createDiffUriDocument(
    original: string,
    proposed: string,
    filePath: string
  ): Promise<{ originalUri: vscode.Uri; proposedUri: vscode.Uri }> {
    const originalUri = vscode.Uri.parse(`novaforge-diff:original/${filePath}`);
    const proposedUri = vscode.Uri.parse(`novaforge-diff:proposed/${filePath}`);

    return { originalUri, proposedUri };
  }

  async showDiffPreview(
    original: string,
    proposed: string,
    filePath: string
  ): Promise<boolean> {
    const originalUri = vscode.Uri.parse(
      `novaforge-diff:original/${encodeURIComponent(filePath)}`
    ).with({ scheme: 'untitled' });

    const proposedUri = vscode.Uri.parse(
      `novaforge-diff:proposed/${encodeURIComponent(filePath)}`
    ).with({ scheme: 'untitled' });

    const tempDir = require('os').tmpdir();
    const path = require('path');
    const originalPath = path.join(tempDir, `novaforge-original-${Date.now()}.tmp`);
    const proposedPath = path.join(tempDir, `novaforge-proposed-${Date.now()}.tmp`);

    const fs = vscode.workspace.fs;
    const origUri = vscode.Uri.file(originalPath);
    const propUri = vscode.Uri.file(proposedPath);

    await fs.writeFile(origUri, Buffer.from(original, 'utf8'));
    await fs.writeFile(propUri, Buffer.from(proposed, 'utf8'));

    try {
      const title = `NovaForge Diff: ${filePath}`;
      await vscode.commands.executeCommand(
        'vscode.diff',
        origUri,
        propUri,
        title,
        { preserveFocus: false, preview: true }
      );

      const choice = await vscode.window.showInformationMessage(
        `Apply changes to ${filePath}?`,
        'Apply',
        'Discard'
      );

      return choice === 'Apply';
    } finally {
      try { await fs.delete(origUri); } catch { /* cleanup */ }
      try { await fs.delete(propUri); } catch { /* cleanup */ }
    }
  }

  applyDiff(diff: ParsedDiff, editor: vscode.TextEditor): vscode.WorkspaceEdit {
    const workspaceEdit = new vscode.WorkspaceEdit();
    const document = editor.document;
    const fullText = document.getText();
    const lines = fullText.split('\n');

    for (const hunk of diff.hunks) {
      let oldLineIndex = hunk.oldStart - 1;
      const removeCount = hunk.changes.filter(c => c.type === 'remove').length;
      const addCount = hunk.changes.filter(c => c.type === 'add').length;

      const rangeStart = new vscode.Position(
        Math.min(oldLineIndex, lines.length),
        0
      );

      let rangeEndLine: number;
      if (removeCount > 0) {
        rangeEndLine = oldLineIndex + removeCount;
      } else {
        rangeEndLine = oldLineIndex;
      }

      if (addCount === 0 && removeCount === 0) {
        continue;
      }

      rangeEndLine = Math.min(rangeEndLine, lines.length);
      const rangeEnd = new vscode.Position(rangeEndLine, 0);

      const range = new vscode.Range(rangeStart, rangeEnd);

      const newLines: string[] = [];
      for (const change of hunk.changes) {
        if (change.type === 'add' || change.type === 'context') {
          newLines.push(change.content);
        }
      }

      const newText = newLines.join('\n') + '\n';
      workspaceEdit.replace(document.uri, range, newText);
    }

    return workspaceEdit;
  }

  async confirmAndApply(
    workspaceEdit: vscode.WorkspaceEdit,
    dryRun: boolean = true
  ): Promise<boolean> {
    const entries = Array.from(workspaceEdit.entries());
    if (entries.length === 0) {
      return false;
    }

    let description = '';
    if (entries.length === 1) {
      const [uri, edits] = entries[0];
      const fileName = vscode.workspace.asRelativePath(uri);
      description = `Apply ${edits.length} change(s) to ${fileName}?`;
    } else {
      const fileNames = entries.map(([uri]) => vscode.workspace.asRelativePath(uri));
      description = `Apply changes to ${fileNames.length} file(s): ${fileNames.slice(0, 3).join(', ')}${fileNames.length > 3 ? '...' : ''}?`;
    }

    const choice = await vscode.window.showWarningMessage(
      description,
      { modal: true },
      'Apply',
      'Preview',
      'Cancel'
    );

    if (choice === 'Cancel' || !choice) {
      return false;
    }

    if (choice === 'Preview') {
      return await this.previewAndConfirm(workspaceEdit);
    }

    const success = await vscode.workspace.applyEdit(workspaceEdit, true);
    if (success) {
      vscode.window.showInformationMessage('Changes applied successfully.');
    } else {
      vscode.window.showErrorMessage('Failed to apply some changes.');
    }
    return success;
  }

  private async previewAndConfirm(workspaceEdit: vscode.WorkspaceEdit): Promise<boolean> {
    const entries = Array.from(workspaceEdit.entries());

    for (const [uri, edits] of entries) {
      const document = await vscode.workspace.openTextDocument(uri);
      const tempEdit = new vscode.WorkspaceEdit();
      tempEdit.set(uri, edits);

      const choice = await vscode.window.showInformationMessage(
        `Preview changes to ${vscode.workspace.asRelativePath(uri)} (${edits.length} edit(s))`,
        { modal: true },
        'Apply All Remaining',
        'Skip',
        'Cancel'
      );

      if (choice === 'Cancel') {
        return false;
      }

      if (choice === 'Apply All Remaining') {
        const success = await vscode.workspace.applyEdit(workspaceEdit, true);
        if (success) {
          vscode.window.showInformationMessage('All changes applied successfully.');
        }
        return success;
      }
    }

    return false;
  }
}
