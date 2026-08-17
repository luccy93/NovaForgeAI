import * as vscode from 'vscode';

interface TelemetryEvent {
  command: string;
  timestamp: number;
  properties?: Record<string, string>;
  latencyMs?: number;
  error?: string;
  errorName?: string;
}

interface TelemetrySettings {
  enabled: boolean;
  endpoint?: string;
}

const TELEMETRY_SECRET_KEY = 'novaforge.telemetry.enabled';

export class TelemetryManager {
  private static instance: TelemetryManager | undefined;
  private enabled: boolean = true;
  private bufferedEvents: TelemetryEvent[] = [];
  private flushInterval: NodeJS.Timeout | undefined;
  private static readonly BUFFER_LIMIT = 50;
  private static readonly FLUSH_INTERVAL_MS = 30000;
  private static readonly SENSITIVE_KEYS = [
    'code', 'source', 'content', 'password', 'token', 'secret',
    'api_key', 'apiKey', 'email', 'license_key'
  ];

  private constructor() {}

  static getInstance(): TelemetryManager {
    if (!TelemetryManager.instance) {
      TelemetryManager.instance = new TelemetryManager();
    }
    return TelemetryManager.instance;
  }

  async initialize(context: vscode.ExtensionContext): Promise<void> {
    const stored = context.globalState.get<boolean>(TELEMETRY_SECRET_KEY);
    if (stored !== undefined) {
      this.enabled = stored;
    } else {
      this.enabled = true;
      await context.globalState.update(TELEMETRY_SECRET_KEY, true);
    }

    this.flushInterval = setInterval(() => {
      this.flush();
    }, TelemetryManager.FLUSH_INTERVAL_MS);
  }

  async setEnabled(enabled: boolean, context?: vscode.ExtensionContext): Promise<void> {
    this.enabled = enabled;
    if (context) {
      await context.globalState.update(TELEMETRY_SECRET_KEY, enabled);
    }
    if (!enabled) {
      this.bufferedEvents = [];
    }
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  track(command: string, properties?: Record<string, string>): void {
    if (!this.enabled) {
      return;
    }

    const sanitizedProps = properties ? this.sanitizeProperties(properties) : undefined;

    const event: TelemetryEvent = {
      command,
      timestamp: Date.now(),
      properties: sanitizedProps
    };

    this.bufferedEvents.push(event);

    if (this.bufferedEvents.length >= TelemetryManager.BUFFER_LIMIT) {
      this.flush();
    }
  }

  trackError(command: string, error: Error | unknown): void {
    if (!this.enabled) {
      return;
    }

    let errorName = 'UnknownError';
    let errorMessage = 'An unknown error occurred';

    if (error instanceof Error) {
      errorName = error.name;
      errorMessage = this.sanitizeErrorMessage(error.message);
    } else if (typeof error === 'string') {
      errorMessage = this.sanitizeErrorMessage(error);
      errorName = 'StringError';
    }

    const event: TelemetryEvent = {
      command,
      timestamp: Date.now(),
      error: errorMessage,
      errorName
    };

    this.bufferedEvents.push(event);

    if (this.bufferedEvents.length >= TelemetryManager.BUFFER_LIMIT) {
      this.flush();
    }
  }

  trackLatency(command: string, startMs: number): void {
    if (!this.enabled) {
      return;
    }

    const latencyMs = Date.now() - startMs;

    const event: TelemetryEvent = {
      command,
      timestamp: Date.now(),
      latencyMs
    };

    this.bufferedEvents.push(event);

    if (this.bufferedEvents.length >= TelemetryManager.BUFFER_LIMIT) {
      this.flush();
    }
  }

  private sanitizeProperties(properties: Record<string, string>): Record<string, string> {
    const sanitized: Record<string, string> = {};

    for (const [key, value] of Object.entries(properties)) {
      const lowerKey = key.toLowerCase();

      if (TelemetryManager.SENSITIVE_KEYS.some(sk => lowerKey.includes(sk))) {
        sanitized[key] = '[REDACTED]';
      } else if (typeof value === 'string' && value.length > 200) {
        sanitized[key] = value.substring(0, 200) + '...[truncated]';
      } else {
        sanitized[key] = value;
      }
    }

    return sanitized;
  }

  private sanitizeErrorMessage(message: string): string {
    let sanitized = message;

    const patterns = [
      /password[=:]\s*\S+/gi,
      /token[=:]\s*\S+/gi,
      /api[_-]?key[=:]\s*\S+/gi,
      /secret[=:]\s*\S+/gi,
      /bearer\s+\S+/gi,
      /\b[\w.-]+@[\w.-]+\.\w+\b/g,
      /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g,
      /(?:https?:\/\/)[^\s]+/gi
    ];

    for (const pattern of patterns) {
      sanitized = sanitized.replace(pattern, '[REDACTED]');
    }

    if (sanitized.length > 500) {
      sanitized = sanitized.substring(0, 500) + '...[truncated]';
    }

    return sanitized;
  }

  private async flush(): Promise<void> {
    if (this.bufferedEvents.length === 0) {
      return;
    }

    const events = [...this.bufferedEvents];
    this.bufferedEvents = [];

    for (const event of events) {
      try {
        await this.sendEvent(event);
      } catch {
        this.bufferedEvents.push(event);
      }
    }
  }

  private async sendEvent(event: TelemetryEvent): Promise<void> {
    const config = vscode.workspace.getConfiguration('novaforge');
    const settings: TelemetrySettings = {
      enabled: config.get<boolean>('telemetry.enabled', true),
      endpoint: config.get<string>('telemetry.endpoint')
    };

    if (!settings.enabled || !settings.endpoint) {
      return;
    }

    try {
      const response = await fetch(settings.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          event: event.command,
          timestamp: event.timestamp,
          properties: event.properties,
          latencyMs: event.latencyMs,
          error: event.error,
          errorName: event.errorName,
          clientId: this.getClientId()
        }),
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        throw new Error(`Telemetry HTTP ${response.status}`);
      }
    } catch {
      throw new Error('Failed to send telemetry event');
    }
  }

  private getClientId(): string {
    const hash = this.simpleHash(vscode.env.machineId);
    return hash;
  }

  private simpleHash(input: string): string {
    let hash = 0;
    for (let i = 0; i < input.length; i++) {
      const char = input.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(36);
  }

  dispose(): void {
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = undefined;
    }

    this.flush().catch(() => {
      // Best-effort flush on dispose
    });

    TelemetryManager.instance = undefined;
  }
}
