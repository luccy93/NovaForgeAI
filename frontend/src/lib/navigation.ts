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
  { id: "ai", label: "AI", href: "/ai-kit", section: "main", auth: false, description: "Agents, tools and playground" },
  { id: "code", label: "Code", href: "/examples", section: "main", auth: false, description: "Code search and examples" },
  { id: "knowledge", label: "Knowledge", href: "/dashboard", section: "main", auth: true, description: "Search the knowledge base" },
  { id: "workflows", label: "Workflows", href: "/dashboard", section: "platform", auth: true, description: "Automation runs" },
  { id: "agents", label: "Agents", href: "/ai-kit", section: "platform", auth: false, description: "Agent registry" },
  { id: "finops", label: "FinOps", href: "/dashboard", section: "platform", auth: true, description: "Spend and budgets" },
  { id: "integrations", label: "Integrations", href: "/dashboard", section: "platform", auth: true, description: "Connected systems" },
  { id: "security", label: "Security", href: "/docs", section: "system", auth: false, description: "Posture and findings" },
  { id: "governance", label: "Governance", href: "/docs", section: "system", auth: false, description: "Policies and posture" },
  { id: "observability", label: "Observability", href: "/docs", section: "system", auth: false, description: "Metrics and traces" },
  { id: "admin", label: "Administration", href: "/settings/organization", section: "system", auth: true, description: "Workspace administration" },
  { id: "settings", label: "Settings", href: "/settings", section: "system", auth: true, description: "Account settings" },
];

export function visibleNavItems(authenticated: boolean): Array<NavItem> {
  return NAV_ITEMS.filter((item) => !item.auth || authenticated);
}
