import logging
import json
import uuid
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    NOTIFICATION = "notification"
    LOGS = "logs"
    METRICS = "metrics"
    SEARCH = "search"
    AI_STREAM = "ai_stream"
    DEPLOYMENT = "deployment"
    COLLABORATION = "collaboration"


class StreamStatus(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class StreamChannel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_type: ChannelType = ChannelType.NOTIFICATION
    name: str = ""
    org_id: str = ""
    workspace_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    subscribers: int = 0
    config: dict = field(default_factory=dict)
    status: StreamStatus = StreamStatus.CONNECTED

    def to_dict(self) -> dict:
        d = asdict(self)
        d["channel_type"] = self.channel_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StreamChannel":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "channel_type" in data:
            val = data["channel_type"]
            if isinstance(val, str):
                for m in ChannelType:
                    if m.value == val or m.name == val:
                        clean["channel_type"] = m
                        break
        if "status" in data:
            val = data["status"]
            if isinstance(val, str):
                for m in StreamStatus:
                    if m.value == val or m.name == val:
                        clean["status"] = m
                        break
        return cls(**clean)


@dataclass
class StreamEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str = ""
    event_type: str = ""
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""
    severity: str = "info"
    correlation_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StreamEvent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StreamSubscription:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str = ""
    subscriber_id: str = ""
    event_types: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StreamSubscription":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Notification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str = ""
    title: str = ""
    body: str = ""
    notification_type: str = "info"
    priority: int = 0
    recipient_id: str = ""
    read: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    delivered_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Notification":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LiveMetric:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metric_name: str = ""
    value: float = 0.0
    unit: str = ""
    tags: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LiveMetric":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class _PlatformStore:
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.channels: dict[str, StreamChannel] = {}
        self.subscriptions: dict[str, StreamSubscription] = {}
        self.events: dict[str, list[StreamEvent]] = defaultdict(list)
        self.notifications: dict[str, Notification] = {}
        self.metrics: dict[str, list[LiveMetric]] = defaultdict(list)
        self.metric_registry: dict[str, dict] = {}
        self.collaboration_sessions: dict[str, dict] = {}
        self.deployment_events: list[dict] = []
        self.telemetry: dict = defaultdict(int)
        os.makedirs(storage_dir, exist_ok=True)

    def channels_path(self) -> str:
        return os.path.join(self.storage_dir, "channels.json")

    def subscriptions_path(self) -> str:
        return os.path.join(self.storage_dir, "subscriptions.json")

    def notifications_path(self) -> str:
        return os.path.join(self.storage_dir, "notifications.json")

    def metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "metrics.json")

    def sessions_path(self) -> str:
        return os.path.join(self.storage_dir, "sessions.json")

    def save_all(self):
        try:
            with open(self.channels_path(), "w", encoding="utf-8") as f:
                json.dump({cid: ch.to_dict() for cid, ch in self.channels.items()}, f, indent=2, default=str)
            with open(self.subscriptions_path(), "w", encoding="utf-8") as f:
                json.dump({sid: sub.to_dict() for sid, sub in self.subscriptions.items()}, f, indent=2, default=str)
            with open(self.notifications_path(), "w", encoding="utf-8") as f:
                json.dump({nid: n.to_dict() for nid, n in self.notifications.items()}, f, indent=2, default=str)
            metrics_snapshot = {name: [m.to_dict() for m in vals[-100:]] for name, vals in self.metrics.items()}
            with open(self.metrics_path(), "w", encoding="utf-8") as f:
                json.dump(metrics_snapshot, f, indent=2, default=str)
            with open(self.sessions_path(), "w", encoding="utf-8") as f:
                json.dump(self.collaboration_sessions, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save platform data: %s", e)

    def load_all(self):
        try:
            if os.path.exists(self.channels_path()):
                with open(self.channels_path(), "r", encoding="utf-8") as f:
                    for cid, cd in json.load(f).items():
                        try:
                            self.channels[cid] = StreamChannel.from_dict(cd)
                        except Exception:
                            pass
            if os.path.exists(self.subscriptions_path()):
                with open(self.subscriptions_path(), "r", encoding="utf-8") as f:
                    for sid, sd in json.load(f).items():
                        try:
                            self.subscriptions[sid] = StreamSubscription.from_dict(sd)
                        except Exception:
                            pass
            if os.path.exists(self.notifications_path()):
                with open(self.notifications_path(), "r", encoding="utf-8") as f:
                    for nid, nd in json.load(f).items():
                        try:
                            self.notifications[nid] = Notification.from_dict(nd)
                        except Exception:
                            pass
            if os.path.exists(self.metrics_path()):
                with open(self.metrics_path(), "r", encoding="utf-8") as f:
                    for mname, mvals in json.load(f).items():
                        self.metrics[mname] = [LiveMetric.from_dict(md) for md in mvals]
            if os.path.exists(self.sessions_path()):
                with open(self.sessions_path(), "r", encoding="utf-8") as f:
                    self.collaboration_sessions = json.load(f)
        except Exception as e:
            logger.error("Failed to load platform data: %s", e)


class _PlatformBase:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "_platform_store"):
            self._platform_store = _PlatformStore(storage_dir)
            self._platform_store.load_all()


class LiveNotifications(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def create_channel(self, channel_type: ChannelType, name: str, org_id: str,
                       workspace_id: Optional[str] = None, config: Optional[dict] = None) -> StreamChannel:
        ch = StreamChannel(
            channel_type=channel_type, name=name, org_id=org_id,
            workspace_id=workspace_id, config=config or {},
        )
        self._platform_store.channels[ch.id] = ch
        self._platform_store.save_all()
        self._platform_store.telemetry["channels_created"] += 1
        return ch

    def subscribe(self, channel_id: str, subscriber_id: str,
                  event_types: Optional[list[str]] = None, filters: Optional[dict] = None) -> Optional[StreamSubscription]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch:
            logger.warning("Channel %s not found", channel_id)
            return None
        sub = StreamSubscription(
            channel_id=channel_id, subscriber_id=subscriber_id,
            event_types=event_types or [], filters=filters or {},
        )
        self._platform_store.subscriptions[sub.id] = sub
        ch.subscribers += 1
        self._platform_store.save_all()
        self._platform_store.telemetry["subscriptions_created"] += 1
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        sub = self._platform_store.subscriptions.pop(subscription_id, None)
        if sub:
            ch = self._platform_store.channels.get(sub.channel_id)
            if ch and ch.subscribers > 0:
                ch.subscribers -= 1
            self._platform_store.save_all()
            self._platform_store.telemetry["subscriptions_removed"] += 1
            return True
        return False

    def send_notification(self, channel_id: str, title: str, body: str,
                          notification_type: str = "info", priority: int = 0,
                          recipient_id: str = "", metadata: Optional[dict] = None) -> Optional[Notification]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch:
            logger.warning("Channel %s not found for notification", channel_id)
            return None
        notif = Notification(
            channel_id=channel_id, title=title, body=body,
            notification_type=notification_type, priority=priority,
            recipient_id=recipient_id, metadata=metadata or {},
        )
        self._platform_store.notifications[notif.id] = notif
        notif.delivered_at = datetime.now(timezone.utc).isoformat()
        self._platform_store.save_all()
        self._platform_store.telemetry["notifications_sent"] += 1
        return notif

    def list_notifications(self, recipient_id: str = "", channel_id: str = "",
                           limit: int = 100, offset: int = 0) -> list[Notification]:
        items = list(self._platform_store.notifications.values())
        if recipient_id:
            items = [n for n in items if n.recipient_id == recipient_id]
        if channel_id:
            items = [n for n in items if n.channel_id == channel_id]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[offset:offset + limit]

    def mark_read(self, notification_id: str) -> bool:
        notif = self._platform_store.notifications.get(notification_id)
        if notif:
            notif.read = True
            self._platform_store.save_all()
            self._platform_store.telemetry["notifications_read"] += 1
            return True
        return False

    def get_unread_count(self, recipient_id: str = "") -> int:
        if recipient_id:
            return sum(1 for n in self._platform_store.notifications.values()
                       if n.recipient_id == recipient_id and not n.read)
        return sum(1 for n in self._platform_store.notifications.values() if not n.read)

    def get_notification_stats(self) -> dict:
        total = len(self._platform_store.notifications)
        unread = self.get_unread_count()
        by_type = defaultdict(int)
        for n in self._platform_store.notifications.values():
            by_type[n.notification_type] += 1
        return {
            "total": total,
            "unread": unread,
            "by_type": dict(by_type),
            "channels_active": len(self._platform_store.channels),
        }


class StreamingLogs(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def create_log_stream(self, name: str, org_id: str, workspace_id: Optional[str] = None,
                          config: Optional[dict] = None) -> StreamChannel:
        ch = StreamChannel(
            channel_type=ChannelType.LOGS, name=name, org_id=org_id,
            workspace_id=workspace_id, config=config or {},
        )
        self._platform_store.channels[ch.id] = ch
        self._platform_store.save_all()
        self._platform_store.telemetry["log_streams_created"] += 1
        return ch

    def subscribe_logs(self, channel_id: str, subscriber_id: str,
                       filters: Optional[dict] = None) -> Optional[StreamSubscription]:
        return LiveNotifications.subscribe(self, channel_id, subscriber_id, filters=filters)

    def emit_log(self, channel_id: str, message: str, source: str = "",
                 severity: str = "info", correlation_id: str = "",
                 metadata: Optional[dict] = None) -> Optional[StreamEvent]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch or ch.channel_type != ChannelType.LOGS:
            logger.warning("Invalid log channel %s", channel_id)
            return None
        event = StreamEvent(
            channel_id=channel_id, event_type="log", source=source,
            severity=severity, correlation_id=correlation_id,
            data={"message": message, **(metadata or {})},
        )
        self._platform_store.events[channel_id].append(event)
        if len(self._platform_store.events[channel_id]) > 10000:
            self._platform_store.events[channel_id] = self._platform_store.events[channel_id][-5000:]
        self._platform_store.save_all()
        self._platform_store.telemetry["logs_emitted"] += 1
        return event

    def get_log_history(self, channel_id: str, limit: int = 100, offset: int = 0) -> list[StreamEvent]:
        events = self._platform_store.events.get(channel_id, [])
        events.sort(key=lambda x: x.timestamp, reverse=True)
        return events[offset:offset + limit]

    def search_logs(self, channel_id: str = "", query_text: str = "",
                    severity: str = "", limit: int = 100) -> list[StreamEvent]:
        results = []
        for cid, evts in self._platform_store.events.items():
            if channel_id and cid != channel_id:
                continue
            for evt in evts:
                if severity and evt.severity != severity:
                    continue
                if query_text:
                    ql = query_text.lower()
                    msg = evt.data.get("message", "")
                    if ql not in msg.lower() and ql not in evt.source.lower():
                        continue
                results.append(evt)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get_log_stats(self) -> dict:
        total_logs = sum(len(evts) for evts in self._platform_store.events.values())
        by_severity = defaultdict(int)
        for evts in self._platform_store.events.values():
            for e in evts:
                by_severity[e.severity] += 1
        return {
            "total_logs": total_logs,
            "by_severity": dict(by_severity),
            "active_streams": sum(1 for c in self._platform_store.channels.values()
                                  if c.channel_type == ChannelType.LOGS),
        }


class StreamingAI(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def create_ai_stream(self, name: str, org_id: str, workspace_id: Optional[str] = None,
                         config: Optional[dict] = None) -> StreamChannel:
        ch = StreamChannel(
            channel_type=ChannelType.AI_STREAM, name=name, org_id=org_id,
            workspace_id=workspace_id, config=config or {},
        )
        self._platform_store.channels[ch.id] = ch
        self._platform_store.save_all()
        self._platform_store.telemetry["ai_streams_created"] += 1
        return ch

    def subscribe_ai(self, channel_id: str, subscriber_id: str,
                     event_types: Optional[list[str]] = None,
                     filters: Optional[dict] = None) -> Optional[StreamSubscription]:
        return LiveNotifications.subscribe(self, channel_id, subscriber_id, event_types, filters)

    def emit_ai_event(self, channel_id: str, event_type: str, data: dict,
                      source: str = "", correlation_id: str = "") -> Optional[StreamEvent]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch or ch.channel_type != ChannelType.AI_STREAM:
            logger.warning("Invalid AI stream channel %s", channel_id)
            return None
        event = StreamEvent(
            channel_id=channel_id, event_type=event_type, data=data,
            source=source, correlation_id=correlation_id,
        )
        self._platform_store.events[channel_id].append(event)
        if len(self._platform_store.events[channel_id]) > 10000:
            self._platform_store.events[channel_id] = self._platform_store.events[channel_id][-5000:]
        self._platform_store.save_all()
        self._platform_store.telemetry["ai_events_emitted"] += 1
        return event

    def get_ai_stream_history(self, channel_id: str, limit: int = 100, offset: int = 0) -> list[StreamEvent]:
        events = self._platform_store.events.get(channel_id, [])
        events.sort(key=lambda x: x.timestamp, reverse=True)
        return events[offset:offset + limit]

    def get_ai_stream_stats(self) -> dict:
        total_events = sum(len(evts) for cid, evts in self._platform_store.events.items()
                           if self._platform_store.channels.get(cid, StreamChannel()).channel_type == ChannelType.AI_STREAM)
        active_streams = sum(1 for c in self._platform_store.channels.values()
                             if c.channel_type == ChannelType.AI_STREAM)
        return {"total_events": total_events, "active_streams": active_streams}


class LiveMetrics(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def register_metric(self, metric_name: str, unit: str = "",
                        description: str = "", metadata: Optional[dict] = None) -> bool:
        if metric_name in self._platform_store.metric_registry:
            return False
        self._platform_store.metric_registry[metric_name] = {
            "name": metric_name, "unit": unit, "description": description,
            "metadata": metadata or {}, "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._platform_store.telemetry["metrics_registered"] += 1
        return True

    def emit_metric(self, metric_name: str, value: float, tags: Optional[dict] = None,
                    source: str = "") -> Optional[LiveMetric]:
        if metric_name not in self._platform_store.metric_registry:
            logger.warning("Metric %s not registered", metric_name)
            return None
        metric = LiveMetric(
            metric_name=metric_name, value=value,
            unit=self._platform_store.metric_registry[metric_name].get("unit", ""),
            tags=tags or {}, source=source,
        )
        self._platform_store.metrics[metric_name].append(metric)
        if len(self._platform_store.metrics[metric_name]) > 10000:
            self._platform_store.metrics[metric_name] = self._platform_store.metrics[metric_name][-5000:]
        self._platform_store.save_all()
        self._platform_store.telemetry["metrics_emitted"] += 1
        return metric

    def get_metric_history(self, metric_name: str, limit: int = 100,
                           offset: int = 0) -> list[LiveMetric]:
        metrics = self._platform_store.metrics.get(metric_name, [])
        metrics.sort(key=lambda x: x.timestamp, reverse=True)
        return metrics[offset:offset + limit]

    def get_current_metrics(self) -> dict[str, float]:
        current = {}
        for name, vals in self._platform_store.metrics.items():
            if vals:
                current[name] = vals[-1].value
        return current

    def subscribe_metrics(self, channel_id: str, subscriber_id: str,
                          metric_names: Optional[list[str]] = None) -> Optional[StreamSubscription]:
        return LiveNotifications.subscribe(self, channel_id, subscriber_id,
                                           event_types=metric_names)

    def get_metric_stats(self) -> dict:
        return {
            "registered_metrics": len(self._platform_store.metric_registry),
            "active_metrics": len(self._platform_store.metrics),
            "total_datapoints": sum(len(v) for v in self._platform_store.metrics.values()),
            "registry": dict(self._platform_store.metric_registry),
        }


class LiveSearch(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def subscribe_search_results(self, channel_id: str, subscriber_id: str,
                                 query_filters: Optional[dict] = None) -> Optional[StreamSubscription]:
        return LiveNotifications.subscribe(self, channel_id, subscriber_id, event_types=["search_result"],
                                           filters=query_filters)

    def emit_search_update(self, channel_id: str, query: str, results: list[dict],
                           source: str = "", correlation_id: str = "") -> Optional[StreamEvent]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch or ch.channel_type != ChannelType.SEARCH:
            logger.warning("Invalid search channel %s", channel_id)
            return None
        event = StreamEvent(
            channel_id=channel_id, event_type="search_result", source=source,
            correlation_id=correlation_id,
            data={"query": query, "results": results, "result_count": len(results)},
        )
        self._platform_store.events[channel_id].append(event)
        if len(self._platform_store.events[channel_id]) > 10000:
            self._platform_store.events[channel_id] = self._platform_store.events[channel_id][-5000:]
        self._platform_store.save_all()
        self._platform_store.telemetry["search_updates_emitted"] += 1
        return event


class LiveDeployment(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def subscribe_deployment_events(self, channel_id: str, subscriber_id: str,
                                    filters: Optional[dict] = None) -> Optional[StreamSubscription]:
        return LiveNotifications.subscribe(self, channel_id, subscriber_id,
                                           event_types=["deployment"], filters=filters)

    def emit_deployment_event(self, channel_id: str, event_type: str, data: dict,
                              source: str = "", correlation_id: str = "") -> Optional[StreamEvent]:
        ch = self._platform_store.channels.get(channel_id)
        if not ch or ch.channel_type != ChannelType.DEPLOYMENT:
            logger.warning("Invalid deployment channel %s", channel_id)
            return None
        event = StreamEvent(
            channel_id=channel_id, event_type=event_type, data=data,
            source=source, correlation_id=correlation_id,
        )
        self._platform_store.events[channel_id].append(event)
        if len(self._platform_store.events[channel_id]) > 10000:
            self._platform_store.events[channel_id] = self._platform_store.events[channel_id][-5000:]
        self._platform_store.deployment_events.append({
            "channel_id": channel_id, "event_type": event_type,
            "data": data, "timestamp": event.timestamp,
        })
        if len(self._platform_store.deployment_events) > 5000:
            self._platform_store.deployment_events = self._platform_store.deployment_events[-2500:]
        self._platform_store.save_all()
        self._platform_store.telemetry["deployment_events_emitted"] += 1
        return event

    def get_deployment_history(self, channel_id: str = "", limit: int = 100) -> list[dict]:
        items = list(self._platform_store.deployment_events)
        if channel_id:
            items = [d for d in items if d["channel_id"] == channel_id]
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items[:limit]


class LiveCollaboration(_PlatformBase):
    def __init__(self, storage_dir: str):
        _PlatformBase.__init__(self, storage_dir)

    def create_collaboration_session(self, name: str, org_id: str,
                                     workspace_id: Optional[str] = None,
                                     config: Optional[dict] = None) -> dict:
        session = {
            "id": str(uuid.uuid4()),
            "name": name,
            "org_id": org_id,
            "workspace_id": workspace_id,
            "config": config or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
            "participants": [],
            "event_count": 0,
        }
        self._platform_store.collaboration_sessions[session["id"]] = session
        ch = StreamChannel(
            channel_type=ChannelType.COLLABORATION, name=name,
            org_id=org_id, workspace_id=workspace_id,
            config={"session_id": session["id"], **(config or {})},
        )
        self._platform_store.channels[ch.id] = ch
        self._platform_store.save_all()
        self._platform_store.telemetry["collab_sessions_created"] += 1
        return session

    def subscribe_session(self, session_id: str, subscriber_id: str,
                          event_types: Optional[list[str]] = None) -> Optional[StreamSubscription]:
        session = self._platform_store.collaboration_sessions.get(session_id)
        if not session:
            logger.warning("Collaboration session %s not found", session_id)
            return None
        channel_id = None
        for cid, ch in self._platform_store.channels.items():
            if ch.config.get("session_id") == session_id:
                channel_id = cid
                break
        if not channel_id:
            return None
        sub = LiveNotifications.subscribe(self, channel_id, subscriber_id, event_types)
        if sub and subscriber_id not in session["participants"]:
            session["participants"].append(subscriber_id)
            self._platform_store.save_all()
        return sub

    def emit_event(self, session_id: str, event_type: str, data: dict,
                   source: str = "") -> Optional[StreamEvent]:
        session = self._platform_store.collaboration_sessions.get(session_id)
        if not session:
            logger.warning("Collaboration session %s not found", session_id)
            return None
        channel_id = None
        for cid, ch in self._platform_store.channels.items():
            if ch.config.get("session_id") == session_id:
                channel_id = cid
                break
        if not channel_id:
            return None
        event = StreamEvent(
            channel_id=channel_id, event_type=event_type, data=data, source=source,
        )
        self._platform_store.events[channel_id].append(event)
        if len(self._platform_store.events[channel_id]) > 10000:
            self._platform_store.events[channel_id] = self._platform_store.events[channel_id][-5000:]
        session["event_count"] = session.get("event_count", 0) + 1
        self._platform_store.save_all()
        self._platform_store.telemetry["collab_events_emitted"] += 1
        return event

    def get_session_history(self, session_id: str, limit: int = 100,
                            offset: int = 0) -> list[StreamEvent]:
        channel_id = None
        for cid, ch in self._platform_store.channels.items():
            if ch.config.get("session_id") == session_id:
                channel_id = cid
                break
        if not channel_id:
            return []
        events = self._platform_store.events.get(channel_id, [])
        events.sort(key=lambda x: x.timestamp, reverse=True)
        return events[offset:offset + limit]

    def list_active_sessions(self, org_id: str = "") -> list[dict]:
        sessions = list(self._platform_store.collaboration_sessions.values())
        if org_id:
            sessions = [s for s in sessions if s.get("org_id") == org_id]
        return [s for s in sessions if s.get("active", False)]


class RealTimePlatform(LiveNotifications, StreamingLogs, StreamingAI, LiveMetrics,
                       LiveSearch, LiveDeployment, LiveCollaboration):
    def __init__(self, storage_dir: str):
        os.makedirs(storage_dir, exist_ok=True)
        LiveNotifications.__init__(self, storage_dir)
        StreamingLogs.__init__(self, storage_dir)
        StreamingAI.__init__(self, storage_dir)
        LiveMetrics.__init__(self, storage_dir)
        LiveSearch.__init__(self, storage_dir)
        LiveDeployment.__init__(self, storage_dir)
        LiveCollaboration.__init__(self, storage_dir)

    def get_platform_status(self) -> dict:
        ch = self._platform_store.channels
        return {
            "uptime": datetime.now(timezone.utc).isoformat(),
            "total_channels": len(ch),
            "total_subscriptions": len(self._platform_store.subscriptions),
            "total_notifications": len(self._platform_store.notifications),
            "total_events": sum(len(v) for v in self._platform_store.events.values()),
            "total_metrics": len(self._platform_store.metrics),
            "active_sessions": len([s for s in self._platform_store.collaboration_sessions.values()
                                    if s.get("active")]),
            "storage_dir": self._platform_store.storage_dir,
        }

    def get_active_streams(self) -> list[dict]:
        active = []
        for ch in self._platform_store.channels.values():
            if ch.status == StreamStatus.CONNECTED:
                active.append({
                    "id": ch.id, "name": ch.name,
                    "channel_type": ch.channel_type.value,
                    "subscribers": ch.subscribers,
                    "created_at": ch.created_at,
                })
        return active

    def get_global_metrics(self) -> dict:
        telem = dict(self._platform_store.telemetry)
        telem["status"] = self.get_platform_status()
        telem["current_metric_values"] = LiveMetrics.get_current_metrics(self)
        return telem
