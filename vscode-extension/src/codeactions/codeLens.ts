import * as vscode from 'vscode';

interface NovaForgeCodeLens extends vscode.CodeLens {
  command: string;
  filePath: string;
  line: number;
  code: string;
}

export class NovaForgeCodeLensProvider implements vscode.CodeLensProvider {
  private onDidChangeCodeLensesEmitter = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this.onDidChangeCodeLensesEmitter.event;

  private enabled: boolean = true;

  provideCodeLenses(
    document: vscode.TextDocument,
    token: vscode.CancellationToken
  ): vscode.CodeLens[] {
    if (!this.enabled) {
      return [];
    }

    const lenses: vscode.CodeLens[] = [];
    const filePath = document.uri.fsPath;

    const symbols = this.getDocumentSymbols(document);

    for (const symbol of symbols) {
      if (token.isCancellationRequested) {
        break;
      }

      const range = symbol.range;
      const name = symbol.name;
      const code = document.getText(range);

      const codeLensRange = new vscode.Range(
        range.start,
        range.start
      );

      const contextArg = {
        filePath,
        language: document.languageId,
        code,
        startLine: range.start.line + 1,
        endLine: range.end.line + 1,
        symbolName: name
      };

      const explainLens = this.createLens(
        '💡 Explain',
        'novaforge.explain',
        codeLensRange,
        contextArg
      );
      lenses.push(explainLens);

      const fixLens = this.createLens(
        '🔧 Fix',
        'novaforge.fix',
        new vscode.Range(
          new vscode.Position(range.start.line, range.start.character + (range.start.character > 0 ? 0 : 0)),
          new vscode.Position(range.start.line, range.start.character)
        ),
        contextArg
      );
      lenses.push(fixLens);

      const testLens = this.createLens(
        '🧪 Generate Tests',
        'novaforge.generateTests',
        new vscode.Range(
          new vscode.Position(range.start.line, range.start.character),
          new vscode.Position(range.start.line, range.start.character + 1)
        ),
        contextArg
      );
      lenses.push(testLens);
    }

    return lenses;
  }

  private createLens(
    title: string,
    command: string,
    range: vscode.Range,
    args: unknown
  ): NovaForgeCodeLens {
    const lens = new vscode.CodeLens(range) as NovaForgeCodeLens;
    lens.command = command;
    lens.filePath = args.filePath;
    lens.line = args.startLine;
    lens.code = args.code;

    lens.command = {
      command,
      title,
      arguments: [args]
    };

    return lens;
  }

  private getDocumentSymbols(document: vscode.TextDocument): Array<{
    name: string;
    range: vscode.Range;
    kind: vscode.SymbolKind;
  }> {
    const symbols: Array<{
      name: string;
      range: vscode.Range;
      kind: vscode.SymbolKind;
    }> = [];

    const text = document.getText();
    const lines = text.split('\n');

    const functionPatterns = [
      /^(?:export\s+)?(?:async\s+)?function\s+(\w+)/,
      /^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)\s*(?::\s*\S+\s*)?=>|function)/,
      /^(?:export\s+)?(?:static\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]/
    ];

    const classPattern = /^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/;

    const methodPattern = /^\s+(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*(?:get\s+|set\s+)?(\w+)\s*\([^)]*\)\s*[:{]/;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      const classMatch = line.match(classPattern);
      if (classMatch) {
        const endLine = this.findBlockEnd(lines, i);
        symbols.push({
          name: classMatch[1],
          range: new vscode.Range(
            new vscode.Position(i, 0),
            new vscode.Position(endLine, lines[endLine]?.length || 0)
          ),
          kind: vscode.SymbolKind.Class
        });
        continue;
      }

      for (const pattern of functionPatterns) {
        const match = line.match(pattern);
        if (match) {
          const endLine = this.findBlockEnd(lines, i);
          symbols.push({
            name: match[1],
            range: new vscode.Range(
              new vscode.Position(i, 0),
              new vscode.Position(endLine, lines[endLine]?.length || 0)
            ),
            kind: vscode.SymbolKind.Function
          });
          break;
        }
      }
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const methodMatch = line.match(methodPattern);

      if (methodMatch) {
        const endLine = this.findBlockEnd(lines, i);
        const isInClass = symbols.some(
          s => s.kind === vscode.SymbolKind.Class &&
            i > s.range.start.line && i < s.range.end.line
        );

        if (isInClass) {
          const alreadyAdded = symbols.some(
            s => s.name === methodMatch[1] && s.range.start.line === i
          );

          if (!alreadyAdded) {
            symbols.push({
              name: methodMatch[1],
              range: new vscode.Range(
                new vscode.Position(i, 0),
                new vscode.Position(endLine, lines[endLine]?.length || 0)
              ),
              kind: vscode.SymbolKind.Method
            });
          }
        }
      }
    }

    return symbols;
  }

  private findBlockEnd(lines: string[], startLine: number): number {
    let braceCount = 0;
    let foundOpen = false;

    for (let i = startLine; i < lines.length; i++) {
      const line = lines[i];

      for (const char of line) {
        if (char === '{') {
          braceCount++;
          foundOpen = true;
        } else if (char === '}') {
          braceCount--;
        }
      }

      if (foundOpen && braceCount <= 0) {
        return i;
      }

      if (!foundOpen && i > startLine + 20) {
        return i;
      }
    }

    return Math.min(startLine + 50, lines.length - 1);
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    this.onDidChangeCodeLensesEmitter.fire();
  }

  refresh(): void {
    this.onDidChangeCodeLensesEmitter.fire();
  }

  dispose(): void {
    this.onDidChangeCodeLensesEmitter.dispose();
  }
}
