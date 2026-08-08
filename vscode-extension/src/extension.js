const vscode = require("vscode");

function activate(context) {
  const commands = [
    { id: "novaforge.explainCode", handler: explainCode },
    { id: "novaforge.reviewCode", handler: reviewCode },
    { id: "novaforge.open3DView", handler: open3DView },
    { id: "novaforge.askQuestion", handler: askQuestion },
    { id: "novaforge.generateTests", handler: generateTests },
  ];

  commands.forEach(({ id, handler }) => {
    context.subscriptions.push(
      vscode.commands.registerCommand(id, handler)
    );
  });

  context.subscriptions.push(
    vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100)
  );
}

async function explainCode() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return vscode.window.showWarningMessage("No active editor");
  const selection = editor.document.getText(editor.selection);
  if (!selection) return vscode.window.showWarningMessage("Select code to explain");
  
  const panel = vscode.window.createWebviewPanel("novaforge", "NovaForge: Explain", vscode.ViewColumn.Beside, { enableScripts: true });
  panel.webview.html = `<html><body><h2>NovaForge AI</h2><p>Analyzing...</p></body></html>`;
  
  const apiUrl = vscode.workspace.getConfiguration("novaforge").get("apiUrl");
  try {
    const response = await fetch(`${apiUrl}/code/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: selection, language: editor.document.languageId }),
    });
    const data = await response.json();
    panel.webview.html = `<html><body><h2>Code Analysis</h2><pre>${JSON.stringify(data, null, 2)}</pre></body></html>`;
  } catch (e) {
    panel.webview.html = `<html><body><h2>Error</h2><p>${e.message}</p></body></html>`;
  }
}

async function reviewCode() {
  vscode.window.showInformationMessage("NovaForge: Code review requested");
}

async function open3DView() {
  const panel = vscode.window.createWebviewPanel("novaforge3d", "NovaForge 3D", vscode.ViewColumn.One, { enableScripts: true });
  panel.webview.html = `<!DOCTYPE html><html><body style="margin:0;background:#161309;color:#EAE2CF;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh"><h1>NovaForge 3D View</h1><p>Open your browser at http://localhost:3000 for the full 3D experience.</p></body></html>`;
}

async function askQuestion() {
  const question = await vscode.window.showInputBox({ prompt: "Ask NovaForge AI a question about your code..." });
  if (!question) return;
  vscode.window.showInformationMessage(`NovaForge: "${question}"`);
}

async function generateTests() {
  vscode.window.showInformationMessage("NovaForge: Test generation started");
}

module.exports = { activate };
