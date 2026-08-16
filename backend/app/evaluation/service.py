"""Evaluation service registration (Volume 34).

Registers the EvaluationGateway as 'evaluation' on the global service
registry so CLI/API/health can reach it through the standard pattern.
The gateway is built lazily and reused across requests.
"""
import logging
from typing import Optional

from ..common.services import AsyncService, registry
from .gateway import EvaluationGateway

logger = logging.getLogger(__name__)

SERVICE_NAME = "evaluation"


class EvaluationService(AsyncService):
    """AsyncService facade over the evaluation gateway."""

    def __init__(self, gateway: Optional[EvaluationGateway] = None):
        super().__init__(SERVICE_NAME)
        self.gateway = gateway or EvaluationGateway()

    def health(self) -> dict:
        base = dict(super().health())
        base.update(self.gateway.health())
        return base

    async def health_check(self) -> dict:
        return self.health()


svc = EvaluationService()
registry.register(svc)
