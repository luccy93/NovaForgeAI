"use client";

/* eslint-disable react-hooks/set-state-in-effect -- initial data load from server is intentional */

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { useAuthStore } from "@/stores/auth";
import { getToken, api } from "@/lib/api";
import type { SessionOut, ApiKeyOut, WhoAmI } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";

export default function SecurityPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const pushToast = useToastStore((s) => s.push);
  const email = user?.email ?? null;

  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
  const [sessions, setSessions] = useState<SessionOut[] | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // MFA state
  const [mfaCode, setMfaCode] = useState("");
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; uri: string; backup_codes: string[] } | null>(null);

  // Password change
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwBusy, setPwBusy] = useState(false);

  // API key creation
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [w, s, k] = await Promise.all([
        api.whoami(token).catch(() => null),
        api.listSessions(token).catch(() => null),
        api.listApiKeys(token).catch(() => null),
      ]);
      if (w) setWhoami(w as WhoAmI);
      if (s) setSessions(s as SessionOut[]);
      if (k) setApiKeys(k as ApiKeyOut[]);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        useAuthStore.getState().markExpired();
        window.location.href = "/auth/login";
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load security data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleSetupMfa() {
    const token = getToken();
    if (!token) return;
    setMfaBusy(true);
    try {
      const res = await api.setupMfa(token);
      setMfaSetup(res);
      pushToast("success", "MFA setup generated. Scan the QR or enter the secret, then verify.");
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "MFA setup failed");
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleVerifyMfa() {
    const token = getToken();
    if (!token || !mfaCode.trim()) { setError("Enter a 6-digit code"); return; }
    setMfaBusy(true);
    try {
      await api.verifyMfa(token, mfaCode.trim());
      pushToast("success", "MFA enabled");
      setMfaCode("");
      setMfaSetup(null);
      void refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Verification failed");
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleDisableMfa() {
    const token = getToken();
    if (!token || !mfaCode.trim()) { setError("Enter code to disable MFA"); return; }
    setMfaBusy(true);
    try {
      await api.disableMfa(token, mfaCode.trim());
      pushToast("success", "MFA disabled");
      setMfaCode("");
      void refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Disable failed");
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwError("");
    if (!currentPassword || !newPassword) { setPwError("Both fields are required"); return; }
    if (newPassword.length < 8) { setPwError("New password must be at least 8 characters"); return; }
    const token = getToken();
    if (!token) return;
    setPwBusy(true);
    try {
      await api.changePassword(token, currentPassword, newPassword);
      pushToast("success", "Password updated");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setPwError(err instanceof ApiError ? err.message : "Password update failed");
    } finally {
      setPwBusy(false);
    }
  }

  async function handleRevokeSession(id: string) {
    const token = getToken();
    if (!token) return;
    try {
      await api.revokeSession(token, id);
      pushToast("success", "Session revoked");
      void refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Revoke failed");
    }
  }

  async function handleRevokeOthers() {
    const token = getToken();
    if (!token) return;
    try {
      await api.revokeAllOtherSessions(token);
      pushToast("success", "Other sessions revoked");
      void refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Failed");
    }
  }

  async function handleCreateKey(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !newKeyName.trim()) return;
    setKeyBusy(true);
    setCreatedKey(null);
    try {
      const created = await api.createApiKey(token, newKeyName.trim());
      setCreatedKey(created.full_key);
      pushToast("success", "API key created. Copy it now — it won't be shown again.");
      setNewKeyName("");
      void refresh();
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : "Create failed");
    } finally {
      setKeyBusy(false);
    }
  }

  async function handleDeleteKey(id: string) {
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteApiKey(token, id);
      pushToast("success", "Key deleted");
      void refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Delete failed");
    }
  }

  const handleLogout = () => {
    logout("Signed out");
    window.location.href = "/auth/login";
  };

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame eyebrow="Settings" title="Security" description="Sessions, credentials and authentication controls. Tokens are never displayed in full except once at creation." crumbs={[{ label: "Home", href: "/" }, { label: "Settings", href: "/settings/profile" }, { label: "Security" }]}>
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={refresh} /></div> : null}

          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Authentication" title="Two-factor authentication">
              {loading ? <BrutalSkeleton className="h-24" /> : (
                <div className="space-y-4">
                  <p className="text-sm text-on-surface-variant">Status: <BrutalBadge tone={whoami?.mfa_enabled ? "yellow" : "muted"}>{whoami?.mfa_enabled ? "Enabled" : "Disabled"}</BrutalBadge></p>
                  {mfaSetup ? (
                    <div className="border border-outline bg-surface p-4 text-sm break-all">
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Secret</p><p className="font-mono text-on-surface">{mfaSetup.secret}</p>
                      <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">URI</p><p className="text-xs text-on-surface break-all">{mfaSetup.uri}</p>
                      <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Backup codes (save once)</p><ul className="list-disc pl-4 text-on-surface">{mfaSetup.backup_codes.map((c) => <li key={c} className="font-mono text-xs">{c}</li>)}</ul>
                    </div>
                  ) : null}
                  <div className="flex gap-2">
                    <BrutalButton variant="default" onClick={handleSetupMfa} disabled={mfaBusy}>Generate setup</BrutalButton>
                  </div>
                  <div className="flex gap-2">
                    <BrutalInput placeholder="123456" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} aria-label="MFA code" />
                  </div>
                  <div className="flex gap-2">
                    <BrutalButton variant="yellow" onClick={handleVerifyMfa} disabled={mfaBusy}>Verify & enable</BrutalButton>
                    <BrutalButton variant="ghost" onClick={handleDisableMfa} disabled={mfaBusy}>Disable</BrutalButton>
                  </div>
                </div>
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Password" title="Change password">
              <form onSubmit={handleChangePassword} noValidate className="space-y-4">
                <BrutalInput label="Current password" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoComplete="current-password" />
                <BrutalInput label="New password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
                {pwError ? <p role="alert" className="text-sm text-error">{pwError}</p> : null}
                <BrutalButton type="submit" variant="yellow" disabled={pwBusy}>{pwBusy ? "Updating…" : "Update password"}</BrutalButton>
              </form>
            </BrutalCard>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Sessions" title="Active sessions" actions={<BrutalButton variant="ghost" size="sm" onClick={handleRevokeOthers}>Revoke others</BrutalButton>}>
              {loading ? <BrutalSkeleton className="h-32" /> : sessions && sessions.length ? (
                <ul className="space-y-2">
                  {sessions.map((s) => (
                    <li key={s.id} className="flex items-center justify-between border border-outline p-3">
                      <div><p className="font-mono text-xs text-on-surface break-all">ID: {s.id.slice(0, 8)}… {s.is_current ? <BrutalBadge tone="yellow">current</BrutalBadge> : null}</p><p className="text-xs text-on-surface-variant">{s.ip_address || "unknown IP"} · {s.user_agent || "unknown agent"}</p></div>
                      {!s.is_current ? <BrutalButton variant="ghost" size="sm" onClick={() => handleRevokeSession(s.id)}>Revoke</BrutalButton> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No sessions" description="Session data unavailable." />
              )}
            </BrutalCard>

            <BrutalCard eyebrow="API keys" title="Personal keys">
              <form onSubmit={handleCreateKey} className="mb-4 flex gap-2">
                <BrutalInput placeholder="Key name" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} aria-label="New API key name" />
                <BrutalButton type="submit" variant="yellow" disabled={keyBusy || !newKeyName.trim()}>{keyBusy ? "Creating…" : "Create"}</BrutalButton>
              </form>
              {createdKey ? <div className="mb-4 border border-primary-container bg-surface p-3"><p className="font-mono text-xs uppercase tracking-widest text-primary-container">Copy now — shown once</p><p className="mt-2 break-all font-mono text-sm text-on-surface">{createdKey}</p></div> : null}
              {loading ? <BrutalSkeleton className="h-32" /> : apiKeys && apiKeys.length ? (
                <ul className="space-y-2">
                  {apiKeys.map((k) => (
                    <li key={k.id} className="flex items-center justify-between border border-outline p-3">
                      <div><p className="text-sm font-bold text-on-surface">{k.name} <span className="font-mono text-xs text-on-surface-variant">{k.key_prefix}…</span></p><p className="text-xs text-on-surface-variant">{k.scopes.join(", ") || "no scopes"}</p></div>
                      <BrutalButton variant="ghost" size="sm" onClick={() => handleDeleteKey(k.id)}>Delete</BrutalButton>
                    </li>
                  ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No keys" description="Create a key for API access." />
              )}
            </BrutalCard>
          </div>

          <div className="mt-6">
            <BrutalCard eyebrow="Session" title="Sign out">
              <p className="text-sm text-on-surface-variant">Ends your session on this device and clears local state.</p>
              <div className="mt-4"><BrutalButton variant="default" onClick={handleLogout}>Sign out</BrutalButton></div>
            </BrutalCard>
          </div>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
