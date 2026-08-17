import * as vscode from 'vscode';

interface ManagedCancellation {
  source: vscode.CancellationTokenSource;
  label: string;
  createdAt: number;
}

export class CancellationManager {
  private activeSources: Map<string, ManagedCancellation> = new Map();
  private idCounter: number = 0;

  createCancellationTokenSource(label?: string): vscode.CancellationTokenSource {
    const id = `op_${++this.idCounter}`;
    const source = new vscode.CancellationTokenSource();
    const managed: ManagedCancellation = {
      source,
      label: label || id,
      createdAt: Date.now()
    };

    this.activeSources.set(id, managed);

    source.token.onCancellationRequested(() => {
      this.activeSources.delete(id);
    });

    return source;
  }

  createLinkedToken(externalToken: vscode.CancellationToken, label?: string): vscode.CancellationTokenSource {
    const source = this.createCancellationTokenSource(label);

    if (externalToken.isCancellationRequested) {
      source.cancel();
      return source;
    }

    externalToken.onCancellationRequested(() => {
      source.cancel();
    });

    return source;
  }

  cancelAll(): void {
    for (const [id, managed] of this.activeSources) {
      try {
        managed.source.cancel();
      } catch {
        // Source may already be disposed
      }
      this.activeSources.delete(id);
    }
  }

  cancelByLabel(label: string): boolean {
    let cancelled = false;
    for (const [id, managed] of this.activeSources) {
      if (managed.label === label) {
        try {
          managed.source.cancel();
          cancelled = true;
        } catch {
          // Source may already be disposed
        }
        this.activeSources.delete(id);
      }
    }
    return cancelled;
  }

  isCancelled(token?: vscode.CancellationToken): boolean {
    if (!token) {
      return false;
    }
    return token.isCancellationRequested;
  }

  get activeCount(): number {
    return this.activeSources.size;
  }

  getActiveOperations(): Array<{ label: string; durationMs: number }> {
    const now = Date.now();
    const operations: Array<{ label: string; durationMs: number }> = [];

    for (const managed of this.activeSources.values()) {
      operations.push({
        label: managed.label,
        durationMs: now - managed.createdAt
      });
    }

    return operations;
  }

  async withCancellation<T>(
    operation: (token: vscode.CancellationToken) => Promise<T>,
    externalToken?: vscode.CancellationToken,
    label?: string
  ): Promise<T> {
    const source = this.createLinkedToken(
      externalToken || new vscode.CancellationTokenSource().token,
      label
    );

    try {
      if (source.token.isCancellationRequested) {
        throw new vscode.CancellationError('Operation cancelled before start');
      }

      const result = await operation(source.token);
      return result;
    } catch (error) {
      if (error instanceof vscode.CancellationError || 
          (error instanceof Error && error.name === 'Canceled')) {
        throw new vscode.CancellationError(
          label ? `Operation '${label}' was cancelled` : 'Operation cancelled'
        );
      }
      throw error;
    } finally {
      this.cleanupSource(source);
    }
  }

  private cleanupSource(source: vscode.CancellationTokenSource): void {
    for (const [id, managed] of this.activeSources) {
      if (managed.source === source) {
        this.activeSources.delete(id);
        break;
      }
    }

    try {
      source.dispose();
    } catch {
      // Already disposed
    }
  }

  dispose(): void {
    this.cancelAll();
    this.activeSources.clear();
  }
}
