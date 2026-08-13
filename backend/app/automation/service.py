"""Automation service registration (Volume 33).

Registers the AutomationGateway as 'automation' on the global service
registry so CLI/API/health can reach it through the standard pattern.
The gateway is built lazily and reused across requests.
"""
import logging
from typing import Optional

from ..common.services import AsyncService, registry
from .gateway import AutomationGateway
from .workers import WorkerPool as _WorkerPool

logger = logging.getLogger(__name__)

SERVICE_NAME = "automation"


class AutomationService(AsyncService):
    """AsyncService facade over the automation gateway + worker pool."""

    def __init__(self, gateway: Optional[AutomationGateway] = None,
                 pool: Optional[_WorkerPool] = None):
        super().__init__(SERVICE_NAME)
        self.gateway = gateway or AutomationGateway()
        self.pool = pool or _WorkerPool(
            executor=lambda request: self._execute(request), workers=2)

    def _execute(self, request) -> dict:
        self.record_op("run")
        return self.gateway.run(request.workflow_id, request.organization_id,
                                request.inputs,
                                trigger=request.trigger)

    def health(self) -> dict:
        base = dict(super().health())
        base.update(self.gateway.health())
        base["pool"] = self.pool.health()
        return base

    def submit(self, workflow_id: str, organization_id: str = "",
               inputs: dict | None = None) -> dict:
        request = self.pool.submit(workflow_id, organization_id, inputs)
        return {"queued": True, "workflow_id": workflow_id,
                "organization_id": organization_id,
                "pending": self.pool.pending()}


svc = AutomationService()
registry.register(svc)