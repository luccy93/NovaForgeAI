"""10x Enhanced service layer for Volume 25 — Real-Time Collaboration."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import realtime_gateway, presence_service, workspace_sync, session_manager
from . import conflict_resolver, collaboration_bus, shared_memory, activity_stream
from . import notification_engine, chat_service, meeting_assistant, whiteboard_service
from . import live_collaboration, collaborative_ai, engineering_discussions, shared_knowledge
from . import task_collaboration, live_code_review, shared_agents, team_intelligence
from . import file_sharing, sync_engine, cross_org, search, observability

logger = logging.getLogger(__name__)


class RTCService(AsyncService):
    def __init__(self):
        super().__init__("realtime_collaboration", JsonFileStorage("data/rtc/service.json"))
        self.gateway = realtime_gateway.RealtimeGateway()
        self.presence = presence_service.PresenceService()
        self.workspaces = workspace_sync.WorkspaceSync("data/rtc/workspaces")
        self.sessions = session_manager.SessionManager("data/rtc/sessions")
        self.resolver = conflict_resolver.ConflictResolver("data/rtc/ops")
        self.bus = collaboration_bus.CollaborationBus()
        self.memory = shared_memory.SharedMemory()
        self.activity = activity_stream.ActivityStream("data/rtc/activity")
        self.notifications = notification_engine.NotificationEngine("data/rtc/notifications")
        self.chat = chat_service.ChatService("data/rtc/chat")
        self.meetings = meeting_assistant.MeetingAssistant("data/rtc/meetings")
        self.whiteboards = whiteboard_service.WhiteboardService("data/rtc/whiteboards")
        self.live = live_collaboration.LiveCollaboration("data/rtc/live")
        self.ai_collab = collaborative_ai.CollaborativeAI("data/rtc/ai")
        self.discussions = engineering_discussions.EngineeringDiscussions("data/rtc/discussions")
        self.knowledge = shared_knowledge.SharedKnowledge("data/rtc/knowledge")
        self.tasks = task_collaboration.TaskCollaboration("data/rtc/tasks")
        self.reviews = live_code_review.LiveCodeReview("data/rtc/reviews")
        self.shared_agents = shared_agents.SharedAgents("data/rtc/agents")
        self.team_intel = team_intelligence.TeamIntelligence("data/rtc/insights")
        self.files = file_sharing.FileSharing("data/rtc/files")
        self.sync = sync_engine.SyncEngine("data/rtc/sync")
        self.cross_org = cross_org.CrossOrg("data/rtc/cross_org")
        self.search_svc = search.CollaborationSearch("data/rtc/search")
        self.obs = observability.RTCObservability("data/rtc/observability")

    async def send_message(self, org_id: str, channel_id: str, sender_id: str, content: str):
        Validator.non_empty(org_id, "org_id"); Validator.non_empty(content, "content")
        msg = self.chat.send_message(channel_id, sender_id, content)
        if msg:
            asyncio.create_task(self.gateway.publish(f"channel:{channel_id}", "message", {"msg_id": msg.id, "sender": sender_id}))
            self.telemetry.increment("messages_sent")
        return msg

    async def join_session(self, session_id: str, user_id: str):
        s = self.sessions.join(session_id, user_id)
        if s:
            asyncio.create_task(self.gateway.publish(f"session:{session_id}", "user_joined", {"user_id": user_id}))
            self.telemetry.increment("session_joins")
        return s

    async def start_meeting(self, org_id: str, title: str, organizer_id: str = ""):
        m = self.meetings.schedule(org_id, title, organizer_id)
        self.meetings.start(m.id)
        self.telemetry.increment("meetings_started")
        return m

    async def health_check(self) -> dict:
        return self.health()


svc = RTCService()
registry.register(svc)
