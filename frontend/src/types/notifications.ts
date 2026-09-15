/**
 * Notification types (Phase 29) — mirror the verified backend contracts:
 *   backend/app/schemas/__init__.py  (NotificationOut, NotificationChannelOut,
 *                                     NotificationPreferenceItem,
 *                                     NotificationPreferencesOut, enums)
 *   backend/app/models/support.py    (Notification, NotificationChannel tables)
 *
 * All /api/v1/notifications endpoints are AUTH (Bearer) and USER-scoped
 * (filtered by current_user.id). Auth-only — no additional IAM permission.
 */

export interface Notification {
  id: string;
  title: string;
  body: string;
  notification_type: string;
  is_read: boolean;
  read_at: string | null;
  action_url: string | null;
  created_at: string;
}

/** Backend /notifications/channels response never includes `config`. */
export interface NotificationChannel {
  id: string;
  channel_type: string;
  name: string;
  is_active: boolean;
  verified_at: string | null;
  created_at: string;
}

export const NOTIFICATION_CHANNEL_TYPES = [
  "email",
  "slack",
  "discord",
  "webhook",
  "in_app",
] as const;

export type NotificationChannelType = (typeof NOTIFICATION_CHANNEL_TYPES)[number];

export interface NotificationPreferenceItem {
  event_type: string;
  channels: NotificationChannelType[];
  enabled: boolean;
}

export interface NotificationPreferences {
  preferences: NotificationPreferenceItem[];
}

export interface NotificationChannelCreate {
  channel_type: NotificationChannelType;
  name: string;
  config?: Record<string, unknown>;
}

export interface NotificationChannelUpdate {
  name?: string;
  is_active?: boolean;
}

export interface NotificationsUnreadCount {
  count: number;
}