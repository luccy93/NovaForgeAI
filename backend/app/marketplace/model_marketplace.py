"""Model Marketplace — hosted, open source, private, enterprise, embedding, vision, reasoning, code, fine-tuned."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceModel:
    id: str; org_id: str; name: str; model_type: str  # hosted, open_source, private, enterprise, embedding, vision, reasoning, code, fine_tuned
    provider: str = ""; version: str = "1.0"; pricing_per_token: float = 0.0
    context_length: int = 8192; is_verified: bool = False
    rating: float = 0.0; downloads: int = 0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ModelMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/models"):
        self.storage_dir = storage_dir; self._models: dict[str, MarketplaceModel] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "models.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._models[k] = MarketplaceModel(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._models.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, model_type: str, provider: str = "", pricing: float = 0.0) -> MarketplaceModel:
        m = MarketplaceModel(id=str(uuid.uuid4()), org_id=org_id, name=name, model_type=model_type, provider=provider, pricing_per_token=pricing)
        self._models[m.id] = m; self._save(); return m

    def get_by_type(self, model_type: str) -> list[MarketplaceModel]:
        return [m for m in self._models.values() if m.model_type == model_type]

    def get_telemetry(self) -> dict: return {"models": len(self._models)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceWorkflow:
    id: str; org_id: str; name: str; workflow_type: str; description: str = ""
    steps: list = field(default_factory=list); price: float = 0.0
    downloads: int = 0; rating: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class WorkflowMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/workflows"):
        self.storage_dir = storage_dir; self._workflows: dict[str, MarketplaceWorkflow] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "workflows.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._workflows[k] = MarketplaceWorkflow(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._workflows.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, workflow_type: str, steps: list = None, price: float = 0.0) -> MarketplaceWorkflow:
        w = MarketplaceWorkflow(id=str(uuid.uuid4()), org_id=org_id, name=name, workflow_type=workflow_type, steps=steps or [], price=price)
        self._workflows[w.id] = w; self._save(); return w

    def get_telemetry(self) -> dict: return {"workflows": len(self._workflows)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceTemplate:
    id: str; org_id: str; name: str; template_type: str; description: str = ""
    files: list = field(default_factory=list); price: float = 0.0
    downloads: int = 0; rating: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TemplateMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/templates"):
        self.storage_dir = storage_dir; self._templates: dict[str, MarketplaceTemplate] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "templates.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._templates[k] = MarketplaceTemplate(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._templates.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, template_type: str, files: list = None, price: float = 0.0) -> MarketplaceTemplate:
        t = MarketplaceTemplate(id=str(uuid.uuid4()), org_id=org_id, name=name, template_type=template_type, files=files or [], price=price)
        self._templates[t.id] = t; self._save(); return t

    def get_telemetry(self) -> dict: return {"templates": len(self._templates)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceConnector:
    id: str; org_id: str; name: str; target: str; description: str = ""
    config_schema: dict = field(default_factory=dict); is_verified: bool = False
    downloads: int = 0; rating: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ConnectorMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/connectors"):
        self.storage_dir = storage_dir; self._connectors: dict[str, MarketplaceConnector] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "connectors.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._connectors[k] = MarketplaceConnector(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._connectors.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, target: str, config_schema: dict = None) -> MarketplaceConnector:
        c = MarketplaceConnector(id=str(uuid.uuid4()), org_id=org_id, name=name, target=target, config_schema=config_schema or {})
        self._connectors[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"connectors": len(self._connectors)}
