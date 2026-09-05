"use client";

import { PERMISSIONS, type Permission } from "@/types/auth";

/**
 * Frontend permission checks are UX controls only — the backend remains
 * authoritative. Unknown permissions default to denied.
 */
export function hasPermission(granted: ReadonlyArray<string>, required: Permission): boolean {
  if (!required) return false;
  return granted.includes(required);
}

export function hasAnyPermission(granted: ReadonlyArray<string>, required: ReadonlyArray<Permission>): boolean {
  return required.some((permission) => hasPermission(granted, permission));
}

export { PERMISSIONS };
export type { Permission };
