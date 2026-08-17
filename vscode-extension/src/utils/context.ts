import * as vscode from 'vscode';
import * as path from 'path';

export interface ContextRequest {
  filePath?: string;
  language?: string;
  selection?: {
    text: string;
    startLine: number;
    endLine: number;
  };
  visibleRange?: {
    startLine: number;
    endLine: number;
  };
  imports?: string[];
  workspaceRoot?: string;
  workspaceFolders?: string[];
  openFiles?: string[];
  gitBranch?: string;
  gitStatus?: string;
  maxTokens?: number;
  symbolContext?: SymbolInfo[];
}

export interface SymbolInfo {
  name: string;
  kind: string;
  startLine: number;
  endLine: number;
  signature?: string;
}

export interface EditorContext {
  filePath: string;
  language: string;
  fileName: string;
  directory: string;
  selection: {
    text: string;
    startLine: number;
    endLine: number;
    startCharacter: number;
    endCharacter: number;
  };
  visibleRange: {
    startLine: number;
    endLine: number;
  };
  imports: string[];
  symbols: SymbolInfo[];
}

export class ContextCollector {

  collectEditorContext(editor: vscode.TextEditor): EditorContext {
    const document = editor.document;
    const selection = editor.selection;
    const selectionText = document.getText(selection);
    const visibleRange = editor.visibleRanges[0] || new vscode.Range(0, 0, 100, 0);

    const fullPath = document.uri.fsPath;
    const fileName = path.basename(fullPath);
    const directory = path.dirname(fullPath);

    const imports = this.extractImports(document);
    const symbols = this.extractSymbols(document, visibleRange);

    return {
      filePath: fullPath,
      language: document.languageId,
      fileName,
      directory,
      selection: {
        text: selectionText,
        startLine: selection.start.line + 1,
        endLine: selection.end.line + 1,
        startCharacter: selection.start.character,
        endCharacter: selection.end.character
      },
      visibleRange: {
        startLine: visibleRange.start.line + 1,
        endLine: visibleRange.end.line + 1
      },
      imports,
      symbols
    };
  }

  collectWorkspaceContext(): {
    workspaceFolders: string[];
    openFiles: string[];
    activeFile?: string;
  } {
    const workspaceFolders = (vscode.workspace.workspaceFolders || [])
      .map(folder => folder.uri.fsPath);

    const openFiles = vscode.workspace.textDocuments
      .filter(doc => !doc.isUntitled && doc.uri.scheme === 'file')
      .map(doc => doc.uri.fsPath);

    const activeFile = vscode.window.activeTextEditor?.document.uri.fsPath;

    return {
      workspaceFolders,
      openFiles,
      activeFile
    };
  }

  async collectGitContext(): Promise<{
    branch?: string;
    status?: string;
    lastCommit?: string;
  }> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      return {};
    }

    try {
      const gitExtension = vscode.extensions.getExtension('vscode.git')?.exports;
      if (!gitExtension) {
        return {};
      }

      const api = gitExtension.getAPI();
      if (!api || !api.repositories || api.repositories.length === 0) {
        return {};
      }

      const repo = api.repositories[0];
      const branch = repo.state.HEAD?.name;
      const status = repo.state.indexChanges.length > 0 ? 'dirty' : 'clean';
      const lastCommit = repo.state.HEAD?.commit;

      return {
        branch,
        status,
        lastCommit: lastCommit?.substring(0, 8)
      };
    } catch {
      return {};
    }
  }

  async buildContextRequest(
    editor: vscode.TextEditor | undefined,
    maxTokens?: number
  ): Promise<ContextRequest> {
    const context: ContextRequest = {};

    if (editor) {
      const editorContext = this.collectEditorContext(editor);
      context.filePath = editorContext.filePath;
      context.language = editorContext.language;
      context.visibleRange = editorContext.visibleRange;
      context.imports = editorContext.imports;
      context.symbolContext = editorContext.symbols;

      if (editorContext.selection.text.trim().length > 0) {
        context.selection = {
          text: this.truncateToTokenBudget(editorContext.selection.text, maxTokens || 2000),
          startLine: editorContext.selection.startLine,
          endLine: editorContext.selection.endLine
        };
      }
    }

    const workspaceCtx = this.collectWorkspaceContext();
    context.workspaceRoot = workspaceCtx.workspaceFolders[0];
    context.workspaceFolders = workspaceCtx.workspaceFolders;
    context.openFiles = workspaceCtx.openFiles.slice(0, 20);

    const gitCtx = await this.collectGitContext();
    context.gitBranch = gitCtx.branch;
    context.gitStatus = gitCtx.status;

    if (maxTokens) {
      context.maxTokens = maxTokens;
    }

    return context;
  }

  buildMinimalContext(editor: vscode.TextEditor): ContextRequest {
    const document = editor.document;
    const selection = editor.selection;
    const selectionText = document.getText(selection);

    const context: ContextRequest = {
      filePath: document.uri.fsPath,
      language: document.languageId,
    };

    if (selectionText.trim().length > 0) {
      context.selection = {
        text: selectionText,
        startLine: selection.start.line + 1,
        endLine: selection.end.line + 1
      };
    }

    return context;
  }

  private extractImports(document: vscode.TextDocument): string[] {
    const imports: string[] = [];
    const maxLines = Math.min(50, document.lineCount);

    for (let i = 0; i < maxLines; i++) {
      const line = document.lineAt(i).text;

      const importMatch = line.match(
        /^(?:import\s+.*?from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))/
      );

      if (importMatch) {
        const importPath = importMatch[1] || importMatch[2] || importMatch[3];
        if (importPath && !importPath.startsWith('.')) {
          imports.push(importPath);
        }
      }
    }

    return imports;
  }

  private extractSymbols(
    document: vscode.TextDocument,
    visibleRange: vscode.Range
  ): SymbolInfo[] {
    const symbols: SymbolInfo[] = [];
    const startLine = visibleRange.start.line;
    const endLine = Math.min(visibleRange.end.line + 20, document.lineCount - 1);

    for (let i = startLine; i <= endLine; i++) {
      const line = document.lineAt(i).text;

      const funcMatch = line.match(
        /^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)/
      );
      if (funcMatch) {
        symbols.push({
          name: funcMatch[1],
          kind: 'function',
          startLine: i + 1,
          endLine: this.findBlockEnd(document, i),
          signature: funcMatch[0]
        });
        continue;
      }

      const classMatch = line.match(/^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/);
      if (classMatch) {
        symbols.push({
          name: classMatch[1],
          kind: 'class',
          startLine: i + 1,
          endLine: this.findBlockEnd(document, i),
          signature: classMatch[0]
        });
        continue;
      }

      const methodMatch = line.match(
        /^\s+(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*(?:get\s+|set\s+)?(\w+)\s*\(([^)]*)\)/
      );
      if (methodMatch) {
        symbols.push({
          name: methodMatch[1],
          kind: 'method',
          startLine: i + 1,
          endLine: this.findBlockEnd(document, i),
          signature: methodMatch[0].trim()
        });
      }
    }

    return symbols;
  }

  private findBlockEnd(document: vscode.TextDocument, startLine: number): number {
    let braceCount = 0;
    let foundOpen = false;

    for (let i = startLine; i < document.lineCount && i < startLine + 200; i++) {
      const line = document.lineAt(i).text;

      for (const char of line) {
        if (char === '{') {
          braceCount++;
          foundOpen = true;
        } else if (char === '}') {
          braceCount--;
        }
      }

      if (foundOpen && braceCount <= 0) {
        return i + 1;
      }
    }

    return Math.min(startLine + 50, document.lineCount);
  }

  private truncateToTokenBudget(text: string, maxTokens: number): string {
    const approxCharsPerToken = 4;
    const maxChars = maxTokens * approxCharsPerToken;

    if (text.length <= maxChars) {
      return text;
    }

    return text.substring(0, maxChars) + '\n... [truncated]';
  }
}
