import * as vscode from 'vscode';
import { NovaForgeAPI, TokenResponse } from './api';

const TOKEN_KEY = 'novaforge.auth.token';
const REFRESH_TOKEN_KEY = 'novaforge.auth.refreshToken';
const TOKEN_EXPIRY_KEY = 'novaforge.auth.tokenExpiry';
const EMAIL_KEY = 'novaforge.auth.email';

export interface StoredAuth {
  token: string;
  refreshToken?: string;
  expiresAt?: number;
  email?: string;
}

export class AuthManager {
  private api: NovaForgeAPI;
  private secrets: vscode.SecretStorage;
  private static readonly TOKEN_BUFFER_MS = 60 * 1000;

  constructor(api: NovaForgeAPI, secrets: vscode.SecretStorage) {
    this.api = api;
    this.secrets = secrets;
  }

  async getStoredToken(): Promise<string | undefined> {
    return this.secrets.get(TOKEN_KEY);
  }

  async storeToken(token: string): Promise<void> {
    await this.secrets.store(TOKEN_KEY, token);
    const expiresAt = Date.now() + 3600 * 1000;
    await this.secrets.store(TOKEN_EXPIRY_KEY, expiresAt.toString());
  }

  async getRefreshToken(): Promise<string | undefined> {
    return this.secrets.get(REFRESH_TOKEN_KEY);
  }

  async storeRefreshToken(token: string): Promise<void> {
    await this.secrets.store(REFRESH_TOKEN_KEY, token);
  }

  async clearTokens(): Promise<void> {
    await this.secrets.delete(TOKEN_KEY);
    await this.secrets.delete(REFRESH_TOKEN_KEY);
    await this.secrets.delete(TOKEN_EXPIRY_KEY);
    await this.secrets.delete(EMAIL_KEY);
  }

  async isAuthenticated(): Promise<boolean> {
    const token = await this.getStoredToken();
    return !!token && token.length > 0;
  }

  async ensureAuthenticated(): Promise<boolean> {
    const isAuth = await this.isAuthenticated();
    if (isAuth) {
      return true;
    }

    const choice = await vscode.window.showWarningMessage(
      'NovaForge requires authentication. Would you like to log in?',
      'Login',
      'Cancel'
    );

    if (choice === 'Login') {
      return await this.login();
    }

    return false;
  }

  async login(): Promise<boolean> {
    const email = await vscode.window.showInputBox({
      prompt: 'NovaForge Account Email',
      placeHolder: 'you@example.com',
      validateInput: (value) => {
        if (!value || !value.includes('@')) {
          return 'Please enter a valid email address';
        }
        return null;
      }
    });

    if (!email) {
      return false;
    }

    const password = await vscode.window.showInputBox({
      prompt: 'NovaForge Password',
      password: true,
      placeHolder: 'Enter your password'
    });

    if (!password) {
      return false;
    }

    const progressOptions: vscode.ProgressOptions = {
      location: vscode.ProgressLocation.Notification,
      title: 'NovaForge: Logging in...',
      cancellable: false
    };

    try {
      const result = await vscode.window.withProgress(progressOptions, async () => {
        const tokenResponse = await this.api.login(email, password);
        return tokenResponse;
      });

      if (result && result.access_token) {
        await this.storeToken(result.access_token);

        if (result.refresh_token) {
          await this.storeRefreshToken(result.refresh_token);
        }

        if (result.expires_in) {
          const expiresAt = Date.now() + result.expires_in * 1000;
          await this.secrets.store(TOKEN_EXPIRY_KEY, expiresAt.toString());
        }

        await this.secrets.store(EMAIL_KEY, email);

        vscode.window.showInformationMessage(
          `NovaForge: Successfully logged in as ${email}`
        );
        return true;
      }

      vscode.window.showErrorMessage('NovaForge: Login failed - no token received.');
      return false;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      vscode.window.showErrorMessage(`NovaForge: Login failed - ${message}`);
      return false;
    }
  }

  async logout(): Promise<void> {
    await this.clearTokens();
    vscode.window.showInformationMessage('NovaForge: Successfully logged out.');
  }

  async getToken(): Promise<string | undefined> {
    const token = await this.getStoredToken();
    if (!token) {
      return undefined;
    }

    const isExpired = await this.isTokenExpired();
    if (!isExpired) {
      return token;
    }

    const refreshed = await this.attemptRefresh();
    if (refreshed) {
      return refreshed;
    }

    await this.clearTokens();
    return undefined;
  }

  async getEmail(): Promise<string | undefined> {
    return this.secrets.get(EMAIL_KEY);
  }

  private async isTokenExpired(): Promise<boolean> {
    const expiryStr = await this.secrets.get(TOKEN_EXPIRY_KEY);
    if (!expiryStr) {
      return false;
    }

    const expiry = parseInt(expiryStr, 10);
    if (isNaN(expiry)) {
      return false;
    }

    return Date.now() >= expiry - AuthManager.TOKEN_BUFFER_MS;
  }

  private async attemptRefresh(): Promise<string | undefined> {
    const refreshToken = await this.getRefreshToken();
    if (!refreshToken) {
      return undefined;
    }

    try {
      const result = await this.api.refreshToken(refreshToken);

      if (result && result.access_token) {
        await this.storeToken(result.access_token);

        if (result.refresh_token) {
          await this.storeRefreshToken(result.refresh_token);
        }

        if (result.expires_in) {
          const expiresAt = Date.now() + result.expires_in * 1000;
          await this.secrets.store(TOKEN_EXPIRY_KEY, expiresAt.toString());
        }

        return result.access_token;
      }

      return undefined;
    } catch {
      return undefined;
    }
  }

  dispose(): void {
    // No persistent resources to dispose
  }
}
