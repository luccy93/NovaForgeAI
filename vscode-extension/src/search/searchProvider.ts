import * as vscode from 'vscode';
import { NovaForgeAPI, SearchResult, SearchType } from '../client/api';

interface SearchResultItem extends vscode.QuickPickItem {
  result: SearchResult;
}

interface FileSearchResult extends vscode.QuickPickItem {
  uri: vscode.Uri;
}

export class SearchProvider {
  private api: NovaForgeAPI;
  private lastQuery: string = '';

  constructor(api: NovaForgeAPI) {
    this.api = api;
  }

  async searchRepository(query?: string): Promise<void> {
    const searchTerm = query || await this.getSearchQuery();
    if (!searchTerm) {
      return;
    }

    this.lastQuery = searchTerm;

    const searchType = await this.pickSearchType();
    if (!searchType) {
      return;
    }

    try {
      const results = await this.api.search(searchTerm, searchType);
      await this.showResults(results, searchTerm);
    } catch (error) {
      vscode.window.showErrorMessage(
        `Search failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async searchSymbol(query?: string): Promise<void> {
    const searchTerm = query || await this.getSearchQuery('Search symbols...');
    if (!searchTerm) {
      return;
    }

    try {
      const results = await this.api.search(searchTerm, 'symbol');
      await this.showResults(results, searchTerm);
    } catch (error) {
      vscode.window.showErrorMessage(
        `Symbol search failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async searchFile(query?: string): Promise<void> {
    const searchTerm = query || await this.getSearchQuery('Search files...');
    if (!searchTerm) {
      return;
    }

    try {
      const results = await this.api.search(searchTerm, 'file');
      await this.showResults(results, searchTerm);
    } catch (error) {
      vscode.window.showErrorMessage(
        `File search failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async searchWithLocalFallback(query?: string): Promise<void> {
    const searchTerm = query || await this.getSearchQuery();
    if (!searchTerm) {
      return;
    }

    try {
      const results = await this.api.search(searchTerm, 'file');
      if (results.results && results.results.length > 0) {
        await this.showResults(results, searchTerm);
        return;
      }
    } catch {
      // Fall through to local search
    }

    await this.localFileSearch(searchTerm);
  }

  private async localFileSearch(query: string): Promise<void> {
    const pattern = `**/*${query}*`;
    const excludePattern = '{**/node_modules/**,**/.git/**,**/dist/**,**/build/**}';

    try {
      const files = await vscode.workspace.findFiles(pattern, excludePattern, 100);

      if (files.length === 0) {
        vscode.window.showInformationMessage(`No files found matching "${query}"`);
        return;
      }

      const items: FileSearchResult[] = files.map(file => ({
        label: vscode.workspace.asRelativePath(file),
        description: file.fsPath,
        uri: file
      }));

      const selected = await vscode.window.showQuickPick(items, {
        placeHolder: `Local search results for "${query}" (${items.length} files)`,
        matchOnDescription: true,
        matchOnLabel: true
      });

      if (selected) {
        const document = await vscode.workspace.openTextDocument(selected.uri);
        await vscode.window.showTextDocument(document);
      }
    } catch (error) {
      vscode.window.showErrorMessage(
        `Local search failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async getSearchQuery(placeholder?: string): Promise<string | undefined> {
    return vscode.window.showInputBox({
      prompt: placeholder || 'Search repository',
      placeHolder: placeholder || 'Enter search query...',
      value: this.lastQuery
    });
  }

  private async pickSearchType(): Promise<SearchType | undefined> {
    const items: Array<{ label: string; description: string; type: SearchType }> = [
      { label: '$(search) All', description: 'Search across all content types', type: 'all' },
      { label: '$(file) File', description: 'Search file names and paths', type: 'file' },
      { label: '$(symbol-method) Symbol', description: 'Search code symbols (functions, classes)', type: 'symbol' },
      { label: '$(comment) Documentation', description: 'Search documentation and comments', type: 'documentation' },
      { label: '$(terminal) Code', description: 'Search code content', type: 'code' }
    ];

    const selected = await vscode.window.showQuickPick(items, {
      placeHolder: 'Select search type',
      matchOnDescription: true
    });

    return selected?.type;
  }

  private async showResults(results: SearchResult, query: string): Promise<void> {
    const resultItems = results.results.map((item, index): SearchResultItem => {
      const icon = this.getResultIcon(item.type);
      const lineInfo = item.line ? `:${item.line}` : '';
      const colInfo = item.column ? `:${item.column}` : '';

      return {
        label: `${icon} ${item.title || vscode.workspace.asRelativePath(item.path || '')}`,
        description: item.path ? `${item.path}${lineInfo}${colInfo}` : '',
        detail: item.snippet || item.description || '',
        result: item
      };
    });

    if (resultItems.length === 0) {
      vscode.window.showInformationMessage(`No results found for "${query}"`);
      return;
    }

    const selected = await vscode.window.showQuickPick(resultItems, {
      placeHolder: `${resultItems.length} results for "${query}"`,
      matchOnDescription: true,
      matchOnLabel: true,
      matchOnDetail: true,
      placeHolder: `Showing ${resultItems.length} results for "${query}"`
    } as vscode.QuickPickOptions);

    if (selected) {
      await this.navigateToResult(selected.result);
    }
  }

  private getResultIcon(type?: string): string {
    switch (type) {
      case 'file': return '$(file)';
      case 'symbol': return '$(symbol-method)';
      case 'documentation': return '$(book)';
      case 'code': return '$(code)';
      default: return '$(search)';
    }
  }

  private async navigateToResult(result: SearchResult): Promise<void> {
    if (!result.path) {
      vscode.window.showInformationMessage(result.snippet || result.description || 'No location available');
      return;
    }

    try {
      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (!workspaceFolders) {
        return;
      }

      let fileUri: vscode.Uri | undefined;
      for (const folder of workspaceFolders) {
        const potentialUri = vscode.Uri.joinPath(folder.uri, result.path);
        try {
          await vscode.workspace.fs.stat(potentialUri);
          fileUri = potentialUri;
          break;
        } catch {
          continue;
        }
      }

      if (!fileUri) {
        vscode.window.showWarningMessage(`File not found: ${result.path}`);
        return;
      }

      const document = await vscode.workspace.openTextDocument(fileUri);
      const editor = await vscode.window.showTextDocument(document, {
        preview: true,
        viewColumn: vscode.ViewColumn.One
      });

      if (result.line !== undefined && result.line !== null) {
        const line = Math.max(0, result.line - 1);
        const col = result.column ? Math.max(0, result.column - 1) : 0;
        const position = new vscode.Position(line, col);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(
          new vscode.Range(position, position),
          vscode.TextEditorRevealType.InCenter
        );
      }
    } catch (error) {
      vscode.window.showErrorMessage(
        `Failed to open file: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }
}
