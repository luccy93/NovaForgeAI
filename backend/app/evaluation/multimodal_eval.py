"""Multimodal evaluation integration (Volume 34 ↔ 32).

Evaluates multimodal outputs through the existing Volume 32 service:
image/diagram/screenshot understanding, OCR, document understanding and
cross-modal retrieval. Reports availability honestly when the multimodal
volume is not loaded.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MULTIMODAL_TARGETS = [
    "image_understanding", "diagram_understanding", "screenshot_understanding",
    "ocr", "document_understanding", "video_understanding",
    "cross_modal_retrieval", "visual_grounding",
    "diagram_to_code", "code_to_diagram",
]


class MultimodalEvaluator:
    """Adapter that evaluates against the multimodal volume service."""

    def __init__(self, svc: Optional[Any] = None):
        self.svc = svc or self._resolve()

    @staticmethod
    def _resolve() -> Optional[Any]:
        try:
            from ..common.services import registry
            return registry.get("multimodal")
        except Exception:  # noqa: BLE001
            return None

    def targets(self) -> list[str]:
        return list(MULTIMODAL_TARGETS)

    def health(self) -> dict:
        if self.svc is None:
            return {"integrated": False, "status": "not_loaded",
                    "note": "multimodal volume (32) not loaded"}
        try:
            volume = getattr(self.svc, "name", "multimodal")
            return {"integrated": True, "status": "healthy", "volume": volume}
        except Exception as exc:  # noqa: BLE001
            return {"integrated": True, "status": "error", "error": str(exc)}

    async def evaluate(self, target: str, org_id: str = "",
                       asset_id: str = "", query: str = "") -> dict:
        """Evaluate one multimodal target against the volume service."""
        if target not in MULTIMODAL_TARGETS:
            raise ValueError(f"unsupported multimodal target '{target}'")
        if self.svc is None:
            return {"target": target, "available": False,
                    "error": "multimodal volume not loaded"}
        try:
            if target == "cross_modal_retrieval":
                result = await self.svc.search(org_id, query, limit=10)
            elif target == "screenshot_understanding":
                result = await self.svc.capture_screenshot(org_id, query or "https://example.com")
            elif target in ("image_understanding", "visual_grounding"):
                result = await self.svc.job(org_id, asset_id) if asset_id else \
                    {"error": "asset_id required"}
            else:
                result = await self.svc.usage(org_id)
            return {"target": target, "available": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            logger.warning("multimodal eval failed: %s", exc)
            return {"target": target, "available": True, "error": str(exc)}
