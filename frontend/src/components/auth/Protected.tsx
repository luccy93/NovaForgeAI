"use client";

import { useEffect, type ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { Permission } from "@/types/auth";
import { hasAnyPermission } from "@/lib/permissions";

function Forbidden({ message }: { message: string }) {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-16 lg:px-6">
      <div className="border border-error bg-surface p-8 text-center" role="alert">
        <p className="font-mono text-xs uppercase tracking-widest text-error">403 — Forbidden</p>
        <p className="mt-2 text-on-surface">{message}</p>
        <a
          href="/dashboard"
          className="mt-4 inline-block border border-outline px-4 py-2 text-xs font-bold uppercase tracking-widest text-on-surface hover:border-primary-container"
        >
          Back to dashboard
        </a>
      </div>
    </div>
  );
}

export function Protected({
  children,
  requiredPermissions = [],
  grantedPermissions = [],
}: {
  children: ReactNode;
  requiredPermissions?: Array<Permission>;
  /** Permissions the backend reports for this session; empty = unknown = denied for gated content. */
  grantedPermissions?: Array<string>;
}) {
  const status = useAuthStore((state) => state.status);
  const hydrate = useAuthStore((state) => state.hydrate);

  useEffect(() => {
    if (status === "loading") void hydrate();
  }, [status, hydrate]);

  useEffect(() => {
    if (status === "unauthenticated" || status === "expired") {
      window.location.href = "/auth/login";
    }
  }, [status]);

  if (status === "loading") {
    return (
      <div className="mx-auto w-full max-w-[1400px] px-4 py-16 lg:px-6">
        <BrutalSkeleton className="h-48" label="Checking session" />
      </div>
    );
  }
  if (status !== "authenticated") return null;
  if (requiredPermissions.length > 0 && !hasAnyPermission(grantedPermissions, requiredPermissions)) {
    return <Forbidden message="Your account is not authorized for this area." />;
  }
  return <>{children}</>;
}
