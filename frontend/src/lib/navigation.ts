"use client";

import type { Permission } from "@/types/auth";

export type NavGroup = "command" | "engineering" | "knowledge" | "operations" | "security";

export interface NavItem {
  id: string;
  label: string;
  href: string;
  section: "main" | "platform" | "system";
  group: NavGroup;
  auth: boolean;
  description: string;
  /** Optional UX gating permission. Unknown permissions never hide an item. */
  permission?: Permission;
}

/**
 * Enterprise navigation groups rendered in the order below. Visibility is a
 * UX affordance only: every route still requires a backend session and the
 * backend remains the authoritative authorization boundary.
 */
export const NAV_GROUPS: Array<{ id: NavGroup; label: string }> = [
  { id: "command", label: "Command" },
  { id: "engineering", label: "Engineering" },
  { id: "knowledge", label: "Knowledge & Data" },
  { id: "operations", label: "Operations" },
  { id: "security", label: "Security & Governance" },
];

export const NAV_ITEMS: Array<NavItem> = [
  { id: "dashboard", label: "Dashboard", href: "/dashboard", section: "main", group: "command", auth: true, description: "Account, usage and search overview" },
  { id: "ai", label: "AI", href: "/ai", section: "main", group: "command", auth: true, description: "AI workspace and conversations" },
  { id: "command", label: "Command Center", href: "/command", section: "main", group: "command", auth: true, description: "Navigation, discovery and actions" },
  { id: "global-search", label: "Global Search", href: "/knowledge/universal", section: "main", group: "command", auth: true, description: "Universal search across the platform" },
  { id: "code", label: "Code", href: "/code", section: "main", group: "engineering", auth: true, description: "Code intelligence workspace" },
  { id: "agents", label: "Agents", href: "/agents", section: "platform", group: "engineering", auth: true, description: "AI agent platform" },
  { id: "workflows", label: "Workflows", href: "/workflows", section: "platform", group: "engineering", auth: true, description: "Workflow automation" },
  { id: "ml", label: "AI / ML", href: "/ml", section: "platform", group: "engineering", auth: true, description: "Models, evaluations and deployments" },
  { id: "knowledge", label: "Knowledge", href: "/knowledge", section: "main", group: "knowledge", auth: true, description: "Search the knowledge base" },
  { id: "data", label: "Data Platform", href: "/data", section: "platform", group: "knowledge", auth: true, description: "Datasets, pipelines and catalog" },
  { id: "observability", label: "Observability", href: "/observability", section: "system", group: "operations", auth: true, description: "Operational status and health" },
  { id: "integrations", label: "Integrations", href: "/integrations", section: "platform", group: "operations", auth: true, description: "Connected systems" },
  { id: "finops", label: "FinOps", href: "/finops", section: "platform", group: "operations", auth: true, description: "Spend and budgets" },
  { id: "security", label: "Security", href: "/security", section: "system", group: "security", auth: true, description: "Posture, findings and zero trust" },
  { id: "governance", label: "Governance", href: "/governance", section: "system", group: "security", auth: true, description: "Policies, rules and posture" },
  { id: "control-plane", label: "Admin", href: "/admin", section: "system", group: "security", auth: true, description: "Administrative control-plane overview" },
  { id: "settings-organization", label: "Administration", href: "/settings/organization", section: "system", group: "security", auth: true, description: "Workspace administration" },
  { id: "settings", label: "Settings", href: "/settings", section: "system", group: "security", auth: true, description: "Account settings" },
];

export function visibleNavItems(authenticated: boolean): Array<NavItem> {
  return NAV_ITEMS.filter((item) => !item.auth || authenticated);
}

/**
 * Permission-aware navigation filtering. An item is hidden only when the
 * authenticated permission set is known (non-empty) and explicitly lacks the
 * required permission. Unknown permission state never hides an item — the
 * backend remains the authoritative boundary.
 */
export function filterNavByPermission(
  items: Array<NavItem>,
  permissions: string[] | undefined | null,
): Array<NavItem> {
  const known = Array.isArray(permissions) && permissions.length > 0;
  if (!known) return items;
  return items.filter((item) => !item.permission || permissions.includes(item.permission));
}

export interface NavCrumb {
  label: string;
  href?: string;
}

/** Derive a breadcrumb trail for a pathname from the navigation model. */
export function crumbsForPathname(pathname: string): Array<NavCrumb> {
  const item = NAV_ITEMS.find((candidate) => candidate.href === pathname);
  if (!item) return [];
  return [
    { label: "Home", href: "/dashboard" },
    { label: item.label },
  ];
}