import { describe, expect, it } from "vitest";
import { hasAnyPermission, hasPermission, PERMISSIONS } from "@/lib/permissions";

describe("permissions (UX-only)", () => {
  it("grants only listed permissions", () => {
    expect(hasPermission(["organization:read"], PERMISSIONS.orgRead)).toBe(true);
    expect(hasPermission(["organization:read"], PERMISSIONS.billingAdmin)).toBe(false);
  });

  it("denies unknown permissions by default", () => {
    expect(hasPermission([], PERMISSIONS.auditRead)).toBe(false);
    expect(hasAnyPermission(["organization:read"], [PERMISSIONS.billingRead])).toBe(false);
  });
});
