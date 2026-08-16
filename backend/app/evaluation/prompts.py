"""Prompt versioning and evaluation (Volume 34).

Prompts are first-class versioned artifacts. Evaluating a prompt runs it
against a dataset (via the benchmark runner) and compares outcomes across
versions to detect quality/safety/cost/latency/citation regressions.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


class PromptStore:
    """Versioned prompt registry with comparison support."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/prompts.json")

    def register(self, name: str, template: str, version: str = "1",
                 organization_id: str = "", system: str = "",
                 parameters: Optional[dict] = None) -> dict:
        if not name or not name.strip():
            raise ValueError("prompt name must not be empty")
        if not template or not template.strip():
            raise ValueError("prompt template must not be empty")
        prompt_id = uuid.uuid4().hex[:12]
        record = {
            "id": prompt_id, "name": name.strip(), "template": template,
            "version": version, "organization_id": organization_id,
            "system": system, "parameters": parameters or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.storage.set(prompt_id, record)
        return record

    def get(self, prompt_id: str) -> dict:
        record = self.storage.get(prompt_id)
        if not record:
            raise KeyError(f"prompt '{prompt_id}' not found")
        return record

    def list_prompts(self, organization_id: str = "") -> list[dict]:
        prompts = []
        for record in self.storage.get_all().values():
            if not isinstance(record, dict):
                continue
            if organization_id and record.get("organization_id") != organization_id:
                continue
            prompts.append(record)
        return sorted(prompts, key=lambda p: p.get("created_at", ""), reverse=True)

    def compare(self, prompt_a_id: str, prompt_b_id: str) -> dict:
        a = self.get(prompt_a_id)
        b = self.get(prompt_b_id)
        diff = _diff_snippets(a["template"], b["template"])
        if isinstance(diff, dict):
            return {
                "a": {"id": a["id"], "name": a["name"], "version": a["version"]},
                "b": {"id": b["id"], "name": b["name"], "version": b["version"]},
                "template_identical": a["template"] == b["template"],
                **diff,
            }
        return {
            "a": {"id": a["id"], "name": a["name"], "version": a["version"]},
            "b": {"id": b["id"], "name": b["name"], "version": b["version"]},
            "template_identical": a["template"] == b["template"],
            "template_diff": diff,
        }


def _diff_snippets(template_a: str, template_b: str) -> list[dict]:
    """Very small structural diff: changed variable slots + length delta."""
    def slots(template: str) -> set[str]:
        import re
        return set(re.findall(r"\{([a-z_][a-z0-9_]*)\}", template))

    return {
        "only_in_a": sorted(slots(template_a) - slots(template_b)),
        "only_in_b": sorted(slots(template_b) - slots(template_a)),
        "length_delta": len(template_b) - len(template_a),
    }
