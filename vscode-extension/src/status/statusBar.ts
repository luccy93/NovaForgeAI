import * as vscode from 'vscode';

export type ConnectionStatus = 'connected' | 'disconnected' | 'processing' | 'error' | 'idle';

interface StatusBarState {
  status: ConnectionStatus;
  orgName?: string;
  modelName?: string;
  progressMessage?: string;
}

export class StatusBarManager {
  private statusBarItem: vscode.StatusBarItem;
  private orgStatusBarItem: vscode.StatusBarItem;
  private modelStatusBarItem: vscode.StatusBarItem;
  private progressDisposable: vscode.Disposable | undefined;
  private state: StatusBarState = { status: 'idle' };
  private static readonly STATUS_ICONS: Record<ConnectionStatus, string> = {
    connected: '$(check)',
    disconnected: '$(circle-slash)',
    processing: '$(loading~spin)',
    error: '$(error)',
    idle: '$(zap)'
  };

  private static readonly STATUS_COLORS: Record<ConnectionStatus, string> = {
    connected: 'statusBarItem.warningBackground',
    disconnected: 'statusBarItem.errorBackground',
    processing: 'statusBarItem.warningBackground',
    error: 'statusBarItem.errorBackground',
    idle: 'statusBarItem.remoteBackground'
  };

  private static readonly STATUS_TOOLTIPS: Record<ConnectionStatus, string> = {
    connected: 'NovaForge: Connected',
    disconnected: 'NovaForge: Disconnected',
    processing: 'NovaForge: Processing...',
    error: 'NovaForge: Error',
    idle: 'NovaForge: Ready'
  };

  constructor() {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
    this.statusBarItem.command = 'novaforge.status';

    this.orgStatusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      99
    );
    this.orgStatusBarItem.command = 'novaforge.selectOrg';

    this.modelStatusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      98
    );
    this.modelStatusBarItem.command = 'novaforge.settings';
  }

  createStatusBarItem(): void {
    this.updateStatus('idle');
    this.statusBarItem.show();
    this.orgStatusBarItem.hide();
    this.modelStatusBarItem.hide();
  }

  updateStatus(status: ConnectionStatus): void {
    this.state.status = status;

    const icon = StatusBarManager.STATUS_ICONS[status];
    const tooltip = StatusBarManager.STATUS_TOOLTIPS[status];
    const color = StatusBarManager.STATUS_COLORS[status];

    this.statusBarItem.text = `${icon} NovaForge`;
    this.statusBarItem.tooltip = tooltip;
    this.statusBarItem.backgroundColor = undefined;

    try {
      const colorTheme = vscode.workspace.getConfiguration('workbench').get<string>('colorTheme', '');
      if (status === 'error') {
        this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
      } else if (status === 'disconnected') {
        this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
      } else if (status === 'processing') {
        this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
      } else if (status === 'connected') {
        this.statusBarItem.backgroundColor = undefined;
      }
    } catch {
      // Fallback: no custom color
    }

    this.statusBarItem.show();
  }

  updateOrg(orgName: string | undefined): void {
    this.state.orgName = orgName;

    if (orgName) {
      this.orgStatusBarItem.text = `$(organization) ${orgName}`;
      this.orgStatusBarItem.tooltip = `Organization: ${orgName} (click to change)`;
      this.orgStatusBarItem.show();
    } else {
      this.orgStatusBarItem.hide();
    }
  }

  updateModel(modelName: string | undefined): void {
    this.state.modelName = modelName;

    if (modelName) {
      this.modelStatusBarItem.text = `$(symbol-method) ${modelName}`;
      this.modelStatusBarItem.tooltip = `Model: ${modelName} (click to change)`;
      this.modelStatusBarItem.show();
    } else {
      this.modelStatusBarItem.hide();
    }
  }

  showProgress(message: string): void {
    this.state.progressMessage = message;
    this.updateStatus('processing');
    this.statusBarItem.tooltip = `NovaForge: ${message}`;

    this.progressDisposable = vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.StatusBar,
        title: 'NovaForge',
        cancellable: true
      },
      async (progress, token) => {
        progress.report({ message });

        return new Promise<void>((resolve) => {
          const checkInterval = setInterval(() => {
            if (token.isCancellationRequested || this.state.status !== 'processing') {
              clearInterval(checkInterval);
              resolve();
            }
          }, 500);

          token.onCancellationRequested(() => {
            clearInterval(checkInterval);
            resolve();
          });
        });
      }
    );
  }

  hideProgress(): void {
    if (this.progressDisposable) {
      this.progressDisposable.dispose();
      this.progressDisposable = undefined;
    }
    this.state.progressMessage = undefined;
  }

  showError(message: string): void {
    this.updateStatus('error');
    this.statusBarItem.tooltip = `NovaForge Error: ${message}`;
  }

  showConnected(orgName?: string, modelName?: string): void {
    this.updateStatus('connected');
    if (orgName) {
      this.updateOrg(orgName);
    }
    if (modelName) {
      this.updateModel(modelName);
    }
  }

  showDisconnected(): void {
    this.updateStatus('disconnected');
    this.orgStatusBarItem.hide();
    this.modelStatusBarItem.hide();
  }

  getState(): Readonly<StatusBarState> {
    return { ...this.state };
  }

  dispose(): void {
    this.hideProgress();
    this.statusBarItem.dispose();
    this.orgStatusBarItem.dispose();
    this.modelStatusBarItem.dispose();
  }
}
