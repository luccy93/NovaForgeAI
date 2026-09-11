export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "expired";

export interface SessionUser {
  id: string;
  email: string;
  username: string;
}

/** Backend permission strings (mirror of IAMPermission values). UX-only. */
export const PERMISSIONS = {
  orgRead: "organization:read",
  billingRead: "billing:read",
  billingAdmin: "billing:admin",
  auditRead: "audit:read",
  admin: "settings:admin",
  opsAdmin: "admin:all",
  secOpsRead: "secops:read",
  secOpsWrite: "secops:write",
  zeroTrustWrite: "zero_trust:write",
  dataWrite: "data:write",
  dataExport: "data:export",
  workflowExecute: "workflow:execute",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
