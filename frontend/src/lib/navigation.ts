"use client";

export interface NavItem {
  id: string;
  label: string;
  href: string;
  section: "main" | "platform" | "system";
  auth: boolean;
  description: string;
}

/**
 * Application navigation model. Visibility here is a UX affordance only:
 * every route still requires a backend session and the backend remains
 * the authoritative authorization boundary.
 */
export const NAV_ITEMS: Array<NavItem> = [
  { id: "dashboard", label: "Dashboard", href: "/dashboard", section: "main", auth: true, description: "Account, usage and search overview" },
  { id: "ai", label: "AI", href: "/ai", section: "main", auth: true, description: "AI workspace and conversations" },
  { id: "code", label: "Code", href: "/code", section: "main", auth: true, description: "Code intelligence workspace" },
  { id: "knowledge", label: "Knowledge", href: "/knowledge", section: "main", auth: true, description: "Search the knowledge base" },
  { id: "workflows", label: "Workflows", href: "/dashboard", section: "platform", auth: true, description: "Automation runs" },
  { id: "agents", label: "Agents", href: "/ai", section: "platform", auth: true, description: "AI agent workspace" },
  { id: "finops", label: "FinOps", href: "/dashboard", section: "platform", auth: true, description: "Spend and budgets" },
  { id: "integrations", label: "Integrations", href: "/dashboard", section: "platform", auth: true, description: "Connected systems" },
  { id: "security", label: "Security", href: "/docs", section: "system", auth: false, description: "Posture and findings" },
  { id: "governance", label: "Governance", href: "/docs", section: "system", auth: false, description: "Policies and posture" },
  { id: "observability", label: "Observability", href: "/observability", section: "system", auth: true, description: "Operational status and health" },
  { id: "admin", label: "Administration", href: "/settings/organization", section: "system", auth: true, description: "Workspace administration" },
  { id: "settings", label: "Settings", href: "/settings", section: "system", auth: true, description: "Account settings" },
];

export function visibleNavItems(authenticated: boolean): Array<NavItem> {
  return NAV_ITEMS.filter((item) => !item.auth || authenticated);
}
