export interface Organization {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  plan: string;
  is_active: boolean;
  created_at: string;
}

export interface OrganizationMember {
  user_id: string;
  email: string;
  username: string;
  role: string;
  joined_at?: string;
}

export interface InviteResult {
  id: string;
  email: string;
  role: string;
  token: string;
  expires_at: string;
  created_at: string;
}

export interface Workspace {
  id: string;
  org_id?: string;
  organization_id?: string;
  name: string;
  slug?: string;
  description?: string | null;
  created_at?: string;
}

export interface Role {
  id: string;
  name: string;
  description?: string;
  permissions: string[];
  is_system?: boolean;
}

export interface PermissionInfo {
  permission: string;
  granted: boolean;
}
