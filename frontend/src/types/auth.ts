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
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
