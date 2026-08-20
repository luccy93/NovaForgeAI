"""AI Software Quality Engine -- Prompt Versioning (Volume 48).

Version review prompts. Track prompt version, model, tools, retrieval version.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PromptVersion:
    version: str
    prompt_hash: str
    model_id: str
    tools: list[str] = field(default_factory=list)
    retrieval_version: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    created_at: str = ""


class PromptVersionManager:
    """Manage versioned review prompts."""

    def __init__(self):
        self._versions: dict[str, PromptVersion] = {}
        self._active_version: str = "1.0"
        self._register_default()

    def _register_default(self) -> None:
        default = PromptVersion(
            version="1.0",
            prompt_hash=hashlib.sha256(b"quality_review_v1").hexdigest()[:32],
            model_id="default",
            tools=["code_analysis", "security_scan", "test_analysis"],
            retrieval_version="1.0",
            config={"mode": "standard"},
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._versions["1.0"] = default

    def register_version(
        self,
        version: str,
        prompt_text: str,
        model_id: str = "",
        tools: list[str] | None = None,
        retrieval_version: str = "",
        config: dict[str, Any] | None = None,
    ) -> PromptVersion:
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:32]
        pv = PromptVersion(
            version=version,
            prompt_hash=prompt_hash,
            model_id=model_id,
            tools=tools or [],
            retrieval_version=retrieval_version,
            config=config or {},
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._versions[version] = pv
        return pv

    def get_version(self, version: str) -> PromptVersion | None:
        return self._versions.get(version)

    def get_active_version(self) -> PromptVersion:
        return self._versions.get(self._active_version, self._versions["1.0"])

    def set_active(self, version: str) -> bool:
        if version in self._versions:
            self._active_version = version
            return True
        return False

    def list_versions(self) -> list[dict[str, Any]]:
        return [
            {
                "version": pv.version,
                "prompt_hash": pv.prompt_hash,
                "model_id": pv.model_id,
                "tools": pv.tools,
                "active": pv.active,
                "is_current": pv.version == self._active_version,
                "created_at": pv.created_at,
            }
            for pv in self._versions.values()
        ]

    def has_changed(self, version: str, new_prompt_hash: str) -> bool:
        pv = self._versions.get(version)
        if not pv:
            return True
        return pv.prompt_hash != new_prompt_hash
