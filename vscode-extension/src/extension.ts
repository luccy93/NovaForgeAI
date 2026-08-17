import * as vscode from 'vscode';
import { NovaForgeAPI } from './client/api';
import { AuthManager } from './client/auth';
import { ChatPanelProvider } from './chat/chatProvider';
import { NovaForgeCodeActionProvider } from './codeactions/codeActions';
import { NovaForgeCodeLensProvider } from './codeactions/codeLens';
import { ReviewProvider } from './review/reviewProvider';
import { SearchProvider } from './search/searchProvider';
import { StatusBarManager } from './status/statusBar';
import { TelemetryManager } from './utils/telemetry';
import { CancellationManager } from './utils/cancellation';

let api: NovaForgeAPI;
let auth: AuthManager;
let chatProvider: ChatPanelProvider;
let codeActionProvider: NovaForgeCodeActionProvider;
let codeLensProvider: NovaForgeCodeLensProvider;
let reviewProvider: ReviewProvider;
let searchProvider: SearchProvider;
let statusBar: StatusBarManager;
let telemetry: TelemetryManager;
let cancellation: CancellationManager;
let dashboardUrl: string = 'https://novaforge.dev';

export function activate(context: vscode.ExtensionContext): void {
  api = new NovaForgeAPI();
  auth = new AuthManager(api, context.secrets);
  statusBar = new StatusBarManager();
  telemetry = TelemetryManager.getInstance();
  cancellation = new CancellationManager();

  telemetry.initialize(context);
  statusBar.createStatusBarItem();

  chatProvider = new ChatPanelProvider(api);
  codeActionProvider = new NovaForgeCodeActionProvider(api);
  codeLensProvider = new NovaForgeCodeLensProvider(api);
  reviewProvider = new ReviewProvider(api);
  searchProvider = new SearchProvider(api);

  const chatView = vscode.window.registerWebviewViewProvider(
    ChatPanelProvider.viewType,
    chatProvider,
    { webviewOptions: { retainContextWhenHidden: true } }
  );

  const codeActions = vscode.languages.registerCodeActionsProvider(
    { scheme: 'file', pattern: '**/*' },
    codeActionProvider,
    {
      providedCodeActionKinds:
        NovaForgeCodeActionProvider.providedCodeActionKinds
    }
  );

  const codeLens = vscode.languages.registerCodeLensProvider(
    { scheme: 'file', pattern: '**/*' },
    codeLensProvider
  );

  const config = vscode.workspace.getConfiguration('novaforge');
  dashboardUrl = config.get<string>('dashboardUrl', 'https://novaforge.dev');

  const disposables = [
    chatView,
    codeActions,
    codeLens,
    statusBar,
    codeLensProvider,
    reviewProvider,
    telemetry,
    cancellation,
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('novaforge')) {
        updateConfiguration();
      }
    })
  ];

  registerCommand(context, 'novaforge.chat', async () => {
    const authenticated = await auth.ensureAuthenticated();
    if (authenticated) {
      const token = await auth.getToken();
      chatProvider.setToken(token);
      chatProvider.show();
    }
  });

  registerCommand(context, 'novaforge.explain', async (args?: unknown) => {
    await executeCodeAction('explain', args);
  });

  registerCommand(context, 'novaforge.fix', async (args?: unknown) => {
    await executeCodeAction('fix', args);
  });

  registerCommand(context, 'novaforge.refactor', async (args?: unknown) => {
    await executeCodeAction('refactor', args);
  });

  registerCommand(context, 'novaforge.optimize', async (args?: unknown) => {
    await executeCodeAction('optimize', args);
  });

  registerCommand(context, 'novaforge.generateTests', async (args?: unknown) => {
    await executeCodeAction('generate_tests', args);
  });

  registerCommand(context, 'novaforge.generateDocs', async (args?: unknown) => {
    await executeCodeAction('generate_docs', args);
  });

  registerCommand(context, 'novaforge.securityReview', async (args?: unknown) => {
    await executeCodeAction('security_review', args);
  });

  registerCommand(context, 'novaforge.reviewCode', async () => {
    await reviewProvider.reviewFile();
  });

  registerCommand(context, 'novaforge.searchRepo', async () => {
    await searchProvider.searchRepository();
  });

  registerCommand(context, 'novaforge.searchSymbol', async () => {
    await searchProvider.searchSymbol();
  });

  registerCommand(context, 'novaforge.runAgent', async () => {
    const agentName = await vscode.window.showInputBox({
      prompt: 'Agent name',
      placeHolder: 'e.g., code-reviewer, test-generator'
    });
    if (!agentName) {
      return;
    }

    const task = await vscode.window.showInputBox({
      prompt: 'Task description',
      placeHolder: 'Describe what the agent should do...'
    });
    if (!task) {
      return;
    }

    const authenticated = await auth.ensureAuthenticated();
    if (!authenticated) {
      return;
    }

    const token = await auth.getToken();
    statusBar.showProgress('Running agent...');

    try {
      const result = await api.runAgent(agentName, task, token);
      statusBar.updateStatus('connected');

      const choice = await vscode.window.showInformationMessage(
        `Agent "${agentName}" completed: ${result.result.substring(0, 200)}`,
        'Copy Result',
        'Dismiss'
      );
      if (choice === 'Copy Result') {
        await vscode.env.clipboard.writeText(result.result);
      }
    } catch (error) {
      statusBar.showError('Agent execution failed');
      vscode.window.showErrorMessage(
        `Agent failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  });

  registerCommand(context, 'novaforge.runWorkflow', async () => {
    const workflowId = await vscode.window.showInputBox({
      prompt: 'Workflow ID',
      placeHolder: 'Enter the workflow ID to run'
    });
    if (!workflowId) {
      return;
    }

    const authenticated = await auth.ensureAuthenticated();
    if (!authenticated) {
      return;
    }

    const token = await auth.getToken();
    statusBar.showProgress('Running workflow...');

    try {
      const result = await api.runWorkflow(workflowId, {}, token);
      statusBar.updateStatus('connected');

      const output = typeof result.result === 'string'
        ? result.result
        : JSON.stringify(result.result, null, 2);

      const choice = await vscode.window.showInformationMessage(
        `Workflow completed: ${output.substring(0, 200)}`,
        'Copy Result',
        'Dismiss'
      );
      if (choice === 'Copy Result') {
        await vscode.env.clipboard.writeText(output);
      }
    } catch (error) {
      statusBar.showError('Workflow execution failed');
      vscode.window.showErrorMessage(
        `Workflow failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  });

  registerCommand(context, 'novaforge.login', async () => {
    const success = await auth.login();
    if (success) {
      statusBar.updateStatus('connected');
      const email = await auth.getEmail();
      if (email) {
        statusBar.updateOrg(email);
      }
    }
  });

  registerCommand(context, 'novaforge.logout', async () => {
    await auth.logout();
    statusBar.showDisconnected();
    chatProvider.setToken(undefined);
  });

  registerCommand(context, 'novaforge.status', async () => {
    const isAuth = await auth.isAuthenticated();
    const email = await auth.getEmail();
    const sbState = statusBar.getState();

    const items: string[] = [
      `**Authentication:** ${isAuth ? 'Logged in' : 'Not logged in'}`,
      email ? `**Email:** ${email}` : '',
      `**Connection:** ${sbState.status}`,
      sbState.orgName ? `**Organization:** ${sbState.orgName}` : '',
      sbState.modelName ? `**Model:** ${sbState.modelName}` : ''
    ].filter(Boolean);

    vscode.window.showInformationMessage(items.join(' | '));
  });

  registerCommand(context, 'novaforge.settings', async () => {
    await vscode.commands.executeCommand('workbench.action.openSettings', 'novaforge');
  });

  registerCommand(context, 'novaforge.openDashboard', async () => {
    vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
  });

  registerCommand(context, 'novaforge.selectOrg', async () => {
    const authenticated = await auth.ensureAuthenticated();
    if (!authenticated) {
      return;
    }

    const token = await auth.getToken();
    statusBar.showProgress('Loading organizations...');

    try {
      const orgs = await api.listOrganizations(token);
      statusBar.updateStatus('connected');

      if (!orgs || orgs.length === 0) {
        vscode.window.showInformationMessage('No organizations found.');
        return;
      }

      const items = orgs.map(org => ({
        label: org.name,
        description: org.slug,
        detail: org.role ? `Role: ${org.role}` : undefined,
        org
      }));

      const selected = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select an organization'
      });

      if (selected) {
        statusBar.updateOrg(selected.org.name);
        vscode.window.showInformationMessage(`Switched to organization: ${selected.org.name}`);
      }
    } catch (error) {
      statusBar.showError('Failed to load organizations');
      vscode.window.showErrorMessage(
        `Failed to load organizations: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  });

  registerCommand(context, 'novaforge.selectRepo', async () => {
    const authenticated = await auth.ensureAuthenticated();
    if (!authenticated) {
      return;
    }

    const token = await auth.getToken();
    statusBar.showProgress('Loading repositories...');

    try {
      const repos = await api.listRepositories(token);
      statusBar.updateStatus('connected');

      if (!repos || repos.length === 0) {
        vscode.window.showInformationMessage('No repositories found.');
        return;
      }

      const items = repos.map(repo => ({
        label: repo.name,
        description: repo.fullName,
        detail: repo.defaultBranch ? `Default branch: ${repo.defaultBranch}` : undefined,
        repo
      }));

      const selected = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select a repository'
      });

      if (selected) {
        vscode.window.showInformationMessage(`Selected repository: ${selected.repo.fullName}`);
      }
    } catch (error) {
      statusBar.showError('Failed to load repositories');
      vscode.window.showErrorMessage(
        `Failed to load repositories: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  });

  context.subscriptions.push(...disposables);

  checkAuthStatus();
}

async function executeCodeAction(action: string, args?: unknown): Promise<void> {
  const authenticated = await auth.ensureAuthenticated();
  if (!authenticated) {
    return;
  }

  const actionArgs = args as {
    filePath?: string;
    language?: string;
    code?: string;
    startLine?: number;
    endLine?: number;
  } | undefined;

  let filePath = actionArgs?.filePath;
  let language = actionArgs?.language;
  let code = actionArgs?.code;
  let startLine = actionArgs?.startLine;
  let endLine = actionArgs?.endLine;

  const editor = vscode.window.activeTextEditor;
  if (editor) {
    const selection = editor.selection;
    const selectedText = editor.document.getText(selection);

    filePath = filePath || editor.document.uri.fsPath;
    language = language || editor.document.languageId;

    if (selectedText.trim().length > 0) {
      code = selectedText;
      startLine = startLine || selection.start.line + 1;
      endLine = endLine || selection.end.line + 1;
    } else if (!code) {
      vscode.window.showWarningMessage('Select some code to perform this action.');
      return;
    }
  } else if (!code) {
    vscode.window.showWarningMessage('No active editor. Open a file first.');
    return;
  }

  await codeActionProvider.executeAction(action, {
    filePath: filePath!,
    language: language || 'unknown',
    code: code!,
    startLine,
    endLine
  });
}

function registerCommand(
  context: vscode.ExtensionContext,
  command: string,
  callback: (...args: unknown[]) => Promise<void>
): void {
  const disposable = vscode.commands.registerCommand(command, async (...args: unknown[]) => {
    const startMs = Date.now();
    try {
      telemetry.track(command);
      await callback(...args);
    } catch (error) {
      telemetry.trackError(command, error);
      if (!isCancellationError(error)) {
        vscode.window.showErrorMessage(
          `NovaForge: ${command} failed - ${error instanceof Error ? error.message : String(error)}`
        );
      }
    } finally {
      telemetry.trackLatency(command, startMs);
    }
  });

  context.subscriptions.push(disposable);
}

function isCancellationError(error: unknown): boolean {
  if (error instanceof vscode.CancellationError) {
    return true;
  }
  if (error instanceof Error) {
    return error.name === 'Canceled' || error.message.includes('cancelled');
  }
  return false;
}

async function checkAuthStatus(): Promise<void> {
  try {
    const isAuth = await auth.isAuthenticated();
    if (isAuth) {
      statusBar.updateStatus('connected');
      const email = await auth.getEmail();
      if (email) {
        statusBar.updateOrg(email);
      }
    } else {
      statusBar.updateStatus('idle');
    }
  } catch {
    statusBar.updateStatus('disconnected');
  }
}

function updateConfiguration(): void {
  const config = vscode.workspace.getConfiguration('novaforge');
  dashboardUrl = config.get<string>('dashboardUrl', 'https://novaforge.dev');
}

export function deactivate(): void {
  cancellation.cancelAll();
  statusBar.dispose();
  chatProvider.dispose();
  reviewProvider.dispose();
  codeLensProvider.dispose();
  telemetry.dispose();
  cancellation.dispose();
}
