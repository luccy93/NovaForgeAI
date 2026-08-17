import * as vscode from 'vscode';
import { NovaForgeAPI, ChatMessage, ChatStreamChunk } from '../client/api';

interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  repoId?: string;
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId?: string;
  selectedModel?: string;
  contextMode: 'none' | 'file' | 'selection' | 'repository';
}

export class ChatPanelProvider implements vscode.WebviewViewProvider {
  static readonly viewType = 'novaforge.chat';
  private view: vscode.WebviewView | undefined;
  private api: NovaForgeAPI;
  private token: string | undefined;
  private state: ChatState = {
    conversations: [],
    contextMode: 'none'
  };
  private streamingAbort: AbortController | undefined;
  private static readonly MAX_MESSAGES_PER_CONVERSATION = 100;

  constructor(api: NovaForgeAPI) {
    this.api = api;
  }

  setToken(token: string | undefined): void {
    this.token = token;
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: []
    };

    webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (message) => {
      await this.handleWebviewMessage(message);
    });

    webviewView.onDidDispose(() => {
      this.view = undefined;
      this.cancelStreaming();
    });
  }

  async sendMessage(message: string, useStream: boolean = true): Promise<void> {
    if (!this.view || !message.trim()) {
      return;
    }

    if (!this.token) {
      this.view.webview.postMessage({
        type: 'error',
        content: 'Please log in to use NovaForge Chat.'
      });
      return;
    }

    let conversation = this.getActiveConversation();
    if (!conversation) {
      conversation = this.createConversation(message);
      this.state.activeConversationId = conversation.id;
    }

    const userMessage: ChatMessage = {
      role: 'user',
      content: message,
      timestamp: Date.now()
    };

    conversation.messages.push(userMessage);
    this.updateConversationTitle(conversation, message);

    this.view.webview.postMessage({
      type: 'userMessage',
      content: message,
      conversationId: conversation.id
    });

    this.view.webview.postMessage({
      type: 'streamStart'
    });

    try {
      if (useStream) {
        await this.streamResponse(message, conversation);
      } else {
        await this.normalResponse(message, conversation);
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      this.view.webview.postMessage({
        type: 'error',
        content: `Error: ${errorMsg}`
      });
    } finally {
      this.view.webview.postMessage({
        type: 'streamEnd'
      });
    }
  }

  private async streamResponse(message: string, conversation: Conversation): Promise<void> {
    this.streamingAbort = new AbortController();

    const stream = await this.api.chatStream(
      message,
      conversation.id,
      conversation.repoId,
      this.token
    );

    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullResponse = '';

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        if (this.streamingAbort?.signal.aborted) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            continue;
          }

          if (trimmed.startsWith('data: ')) {
            const data = trimmed.substring(6);

            if (data === '[DONE]') {
              break;
            }

            try {
              const chunk: ChatStreamChunk = JSON.parse(data);

              if (chunk.content) {
                fullResponse += chunk.content;
                this.view?.webview.postMessage({
                  type: 'streamChunk',
                  content: chunk.content,
                  fullContent: fullResponse
                });
              }

              if (chunk.conversation_id && !conversation.id.startsWith('conv_')) {
                conversation.id = chunk.conversation_id;
              }
            } catch {
              // Non-JSON data line, skip
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (fullResponse) {
      conversation.messages.push({
        role: 'assistant',
        content: fullResponse,
        timestamp: Date.now()
      });
    }
  }

  private async normalResponse(message: string, conversation: Conversation): Promise<void> {
    const response = await this.api.chat(
      message,
      conversation.id,
      conversation.repoId,
      this.token
    );

    if (response.message) {
      conversation.messages.push({
        role: 'assistant',
        content: response.message,
        timestamp: Date.now()
      });

      this.view?.webview.postMessage({
        type: 'assistantMessage',
        content: response.message,
        conversationId: response.conversation_id,
        citations: response.citations
      });
    }

    if (response.conversation_id) {
      conversation.id = response.conversation_id;
    }
  }

  private cancelStreaming(): void {
    if (this.streamingAbort) {
      this.streamingAbort.abort();
      this.streamingAbort = undefined;
    }
  }

  private async handleWebviewMessage(message: Record<string, unknown>): Promise<void> {
    switch (message.type) {
      case 'sendMessage':
        await this.sendMessage(message.content as string, true);
        break;
      case 'stopStreaming':
        this.cancelStreaming();
        break;
      case 'newConversation':
        this.state.activeConversationId = undefined;
        this.view?.webview.postMessage({ type: 'clearChat' });
        break;
      case 'selectConversation':
        this.state.activeConversationId = message.conversationId as string;
        this.loadConversation(message.conversationId as string);
        break;
      case 'deleteConversation':
        this.deleteConversation(message.conversationId as string);
        break;
      case 'setContextMode':
        this.state.contextMode = (message.mode as ChatState['contextMode']) || 'none';
        break;
      case 'setModel':
        this.state.selectedModel = message.model as string;
        break;
      case 'openFile':
        if (message.filePath) {
          const uri = vscode.Uri.file(message.filePath as string);
          const doc = await vscode.workspace.openTextDocument(uri);
          await vscode.window.showTextDocument(doc);
        }
        break;
    }
  }

  private getActiveConversation(): Conversation | undefined {
    if (!this.state.activeConversationId) {
      return undefined;
    }
    return this.state.conversations.find(c => c.id === this.state.activeConversationId);
  }

  private createConversation(firstMessage: string): Conversation {
    const id = `conv_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const conversation: Conversation = {
      id,
      title: firstMessage.substring(0, 50) + (firstMessage.length > 50 ? '...' : ''),
      messages: [],
      createdAt: Date.now(),
      repoId: undefined
    };

    this.state.conversations.unshift(conversation);

    if (this.state.conversations.length > 50) {
      this.state.conversations = this.state.conversations.slice(0, 50);
    }

    this.view?.webview.postMessage({
      type: 'conversationCreated',
      conversation: {
        id: conversation.id,
        title: conversation.title,
        createdAt: conversation.createdAt
      }
    });

    return conversation;
  }

  private updateConversationTitle(conversation: Conversation, firstUserMessage: string): void {
    if (conversation.messages.filter(m => m.role === 'user').length === 1) {
      conversation.title = firstUserMessage.substring(0, 50) +
        (firstUserMessage.length > 50 ? '...' : '');
    }
  }

  private loadConversation(conversationId: string): void {
    const conversation = this.state.conversations.find(c => c.id === conversationId);
    if (!conversation) {
      return;
    }

    this.view?.webview.postMessage({
      type: 'loadConversation',
      conversation: {
        id: conversation.id,
        title: conversation.title,
        messages: conversation.messages
      }
    });
  }

  private deleteConversation(conversationId: string): void {
    this.state.conversations = this.state.conversations.filter(c => c.id !== conversationId);

    if (this.state.activeConversationId === conversationId) {
      this.state.activeConversationId = undefined;
      this.view?.webview.postMessage({ type: 'clearChat' });
    }

    this.view?.webview.postMessage({
      type: 'conversationDeleted',
      conversationId
    });
  }

  private getContextSnippet(): string {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return '';
    }

    const selection = editor.selection;
    const document = editor.document;
    const selectedText = document.getText(selection);

    switch (this.state.contextMode) {
      case 'file':
        return `\n\n[File: ${document.fileName}]\n\`\`\`${document.languageId}\n${document.getText()}\n\`\`\``;
      case 'selection':
        if (selectedText.trim()) {
          return `\n\n[Selection from ${document.fileName} lines ${selection.start.line + 1}-${selection.end.line + 1}]\n\`\`\`${document.languageId}\n${selectedText}\n\`\`\``;
        }
        return '';
      case 'repository':
        return `\n\n[Repository context: ${vscode.workspace.workspaceFolders?.[0]?.name || 'unknown'}]`;
      default:
        return '';
    }
  }

  private getHtmlForWebview(webview: vscode.Webview): string {
    const nonce = this.getNonce();

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>NovaForge Chat</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      display: flex;
      height: 100vh;
      overflow: hidden;
    }
    .sidebar {
      width: 200px;
      border-right: 1px solid var(--vscode-widget-border);
      display: flex;
      flex-direction: column;
      background: var(--vscode-sideBar-background);
    }
    .sidebar-header {
      padding: 8px 12px;
      border-bottom: 1px solid var(--vscode-widget-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .sidebar-header h3 { font-size: 12px; font-weight: 600; }
    .new-chat-btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      padding: 4px 8px;
      border-radius: 3px;
      cursor: pointer;
      font-size: 11px;
    }
    .new-chat-btn:hover { background: var(--vscode-button-hoverBackground); }
    .conversation-list {
      flex: 1;
      overflow-y: auto;
      padding: 4px;
    }
    .conversation-item {
      padding: 6px 8px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .conversation-item:hover { background: var(--vscode-list-hoverBackground); }
    .conversation-item.active { background: var(--vscode-list-activeSelectionBackground); }
    .conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; }
    .conv-delete {
      opacity: 0;
      background: none;
      border: none;
      color: var(--vscode-descriptionForeground);
      cursor: pointer;
      padding: 0 4px;
      font-size: 14px;
    }
    .conversation-item:hover .conv-delete { opacity: 1; }
    .main-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .toolbar {
      padding: 6px 12px;
      border-bottom: 1px solid var(--vscode-widget-border);
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .toolbar select, .toolbar button {
      padding: 3px 8px;
      border-radius: 3px;
      border: 1px solid var(--vscode-widget-border);
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      font-size: 11px;
    }
    .toolbar button { cursor: pointer; }
    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 8px;
      line-height: 1.5;
      word-wrap: break-word;
    }
    .message.user {
      align-self: flex-end;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border-bottom-right-radius: 2px;
    }
    .message.assistant {
      align-self: flex-start;
      background: var(--vscode-editor-inactiveSelectionBackground);
      border-bottom-left-radius: 2px;
    }
    .message.error {
      align-self: center;
      background: var(--vscode-inputValidation-errorBackground);
      color: var(--vscode-errorForeground);
      font-size: 12px;
    }
    .message pre {
      background: var(--vscode-editor-background);
      padding: 8px;
      border-radius: 4px;
      overflow-x: auto;
      margin: 6px 0;
      font-family: var(--vscode-editor-font-family);
      font-size: var(--vscode-editor-font-size);
    }
    .message code {
      font-family: var(--vscode-editor-font-family);
      background: var(--vscode-editor-background);
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 0.9em;
    }
    .message pre code {
      background: none;
      padding: 0;
    }
    .citations {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--vscode-widget-border);
      font-size: 11px;
      color: var(--vscode-descriptionForeground);
    }
    .citation {
      padding: 2px 0;
      cursor: pointer;
    }
    .citation:hover { color: var(--vscode-textLink-foreground); }
    .input-area {
      padding: 12px 16px;
      border-top: 1px solid var(--vscode-widget-border);
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }
    .input-wrapper {
      flex: 1;
      position: relative;
    }
    #chat-input {
      width: 100%;
      padding: 8px 12px;
      border-radius: 6px;
      border: 1px solid var(--vscode-widget-border);
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      resize: none;
      min-height: 36px;
      max-height: 150px;
      outline: none;
    }
    #chat-input:focus {
      border-color: var(--vscode-focusBorder);
    }
    .send-btn, .stop-btn {
      padding: 8px 16px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
    }
    .send-btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
    }
    .send-btn:hover { background: var(--vscode-button-hoverBackground); }
    .stop-btn {
      background: var(--vscode-errorForeground);
      color: white;
    }
    .streaming-indicator {
      display: none;
      padding: 4px 0;
      font-size: 12px;
      color: var(--vscode-descriptionForeground);
    }
    .streaming-indicator.active { display: block; }
    .typing-cursor {
      display: inline-block;
      width: 2px;
      height: 1em;
      background: var(--vscode-cursor-foreground);
      animation: blink 1s infinite;
      vertical-align: text-bottom;
    }
    @keyframes blink {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }
    .empty-state {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--vscode-descriptionForeground);
      gap: 8px;
    }
    .empty-state h2 { font-size: 18px; font-weight: 400; }
    .empty-state p { font-size: 13px; }
    .context-indicator {
      font-size: 11px;
      color: var(--vscode-descriptionForeground);
      padding: 0 4px;
    }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-header">
      <h3>Conversations</h3>
      <button class="new-chat-btn" id="new-chat-btn">+ New</button>
    </div>
    <div class="conversation-list" id="conversation-list"></div>
  </div>
  <div class="main-panel">
    <div class="toolbar">
      <select id="context-selector">
        <option value="none">No Context</option>
        <option value="file">Current File</option>
        <option value="selection">Selection</option>
        <option value="repository">Repository</option>
      </select>
      <select id="model-selector">
        <option value="default">Default Model</option>
        <option value="gpt-4">GPT-4</option>
        <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
        <option value="claude-3">Claude 3</option>
      </select>
      <span class="context-indicator" id="context-indicator"></span>
    </div>
    <div class="messages" id="messages">
      <div class="empty-state" id="empty-state">
        <h2>NovaForge Chat</h2>
        <p>Ask questions about your code, get explanations, generate code, and more.</p>
        <p>Prefix with @agent to invoke a specific agent.</p>
      </div>
    </div>
    <div class="streaming-indicator" id="streaming-indicator">
      NovaForge is thinking...
    </div>
    <div class="input-area">
      <div class="input-wrapper">
        <textarea id="chat-input" placeholder="Ask NovaForge... (@agent for agent mode)" rows="1"></textarea>
      </div>
      <button class="send-btn" id="send-btn">Send</button>
      <button class="stop-btn" id="stop-btn" style="display:none;">Stop</button>
    </div>
  </div>
  <script nonce="${nonce}">
    (function() {
      const vscode = acquireVsCodeApi();
      const messagesEl = document.getElementById('messages');
      const inputEl = document.getElementById('chat-input');
      const sendBtn = document.getElementById('send-btn');
      const stopBtn = document.getElementById('stop-btn');
      const newChatBtn = document.getElementById('new-chat-btn');
      const contextSelector = document.getElementById('context-selector');
      const modelSelector = document.getElementById('model-selector');
      const streamingIndicator = document.getElementById('streaming-indicator');
      const conversationList = document.getElementById('conversation-list');
      const emptyState = document.getElementById('empty-state');
      const contextIndicator = document.getElementById('context-indicator');

      let isStreaming = false;
      let currentContent = '';

      function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || isStreaming) return;

        if (emptyState) emptyState.style.display = 'none';
        inputEl.value = '';
        inputEl.style.height = 'auto';

        vscode.postMessage({ type: 'sendMessage', content: text });

        isStreaming = true;
        sendBtn.style.display = 'none';
        stopBtn.style.display = 'block';
        streamingIndicator.classList.add('active');
      }

      function stopStreaming() {
        vscode.postMessage({ type: 'stopStreaming' });
        finishStreaming();
      }

      function finishStreaming() {
        isStreaming = false;
        sendBtn.style.display = 'block';
        stopBtn.style.display = 'none';
        streamingIndicator.classList.remove('active');
      }

      sendBtn.addEventListener('click', sendMessage);
      stopBtn.addEventListener('click', stopStreaming);

      inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });

      inputEl.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
      });

      newChatBtn.addEventListener('click', function() {
        vscode.postMessage({ type: 'newConversation' });
      });

      contextSelector.addEventListener('change', function() {
        vscode.postMessage({ type: 'setContextMode', mode: this.value });
        contextIndicator.textContent = this.value !== 'none' ? 'Context: ' + this.options[this.selectedIndex].text : '';
      });

      modelSelector.addEventListener('change', function() {
        vscode.postMessage({ type: 'setModel', model: this.value });
      });

      function addMessage(role, content, citations) {
        const div = document.createElement('div');
        div.className = 'message ' + role;
        div.innerHTML = renderMarkdown(content);

        if (citations && citations.length > 0) {
          const citationsDiv = document.createElement('div');
          citationsDiv.className = 'citations';
          citationsDiv.innerHTML = '<strong>Sources:</strong><br>' +
            citations.map(function(c) {
              const label = c.title || c.path || 'Source';
              const loc = c.line ? ':' + c.line : '';
              return '<div class="citation" data-file="' + (c.path || '') + '" data-line="' + (c.line || 0) + '">' +
                '&#128196; ' + escapeHtml(label) + loc + '</div>';
            }).join('');
          div.appendChild(citationsDiv);

          citationsDiv.querySelectorAll('.citation').forEach(function(el) {
            el.addEventListener('click', function() {
              vscode.postMessage({
                type: 'openFile',
                filePath: this.dataset.file,
                line: parseInt(this.dataset.line || '0')
              });
            });
          });
        }

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
      }

      let streamingDiv = null;
      let streamingContent = '';

      function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
      }

      function renderMarkdown(text) {
        var html = escapeHtml(text);
        html = html.replace(/\\`\\`\\`(\\w*)\\n([\\s\\S]*?)\\`\\`\\`/g, '<pre><code class="language-$1">$2</code></pre>');
        html = html.replace(/\\`([^\\`]+)\\`/g, '<code>$1</code>');
        html = html.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
        html = html.replace(/\\n/g, '<br>');
        return html;
      }

      window.addEventListener('message', function(event) {
        var msg = event.data;
        switch (msg.type) {
          case 'userMessage':
            addMessage('user', msg.content);
            break;
          case 'assistantMessage':
            addMessage('assistant', msg.content, msg.citations);
            finishStreaming();
            break;
          case 'streamStart':
            streamingContent = '';
            streamingDiv = addMessage('assistant', '');
            break;
          case 'streamChunk':
            streamingContent = msg.fullContent || (streamingContent + msg.content);
            if (streamingDiv) {
              streamingDiv.innerHTML = renderMarkdown(streamingContent) + '<span class="typing-cursor"></span>';
              messagesEl.scrollTop = messagesEl.scrollHeight;
            }
            break;
          case 'streamEnd':
            if (streamingDiv) {
              streamingDiv.innerHTML = renderMarkdown(streamingContent);
              streamingDiv = null;
            }
            streamingContent = '';
            finishStreaming();
            break;
          case 'error':
            addMessage('error', msg.content);
            finishStreaming();
            break;
          case 'clearChat':
            messagesEl.innerHTML = '';
            if (emptyState) {
              messagesEl.appendChild(emptyState);
              emptyState.style.display = '';
            }
            streamingDiv = null;
            streamingContent = '';
            break;
          case 'loadConversation':
            messagesEl.innerHTML = '';
            if (msg.conversation && msg.conversation.messages) {
              msg.conversation.messages.forEach(function(m) {
                addMessage(m.role, m.content);
              });
            }
            break;
          case 'conversationCreated':
          case 'conversationDeleted':
            break;
        }
      });
    })();
  </script>
</body>
</html>`;
  }

  private getNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
      text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
  }

  show(): void {
    if (this.view) {
      this.view.show(true);
    }
  }

  dispose(): void {
    this.cancelStreaming();
    this.view?.dispose();
  }
}
