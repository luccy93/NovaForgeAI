"""Research Datasets — maintain code corpus, documentation corpus, security corpus, architecture corpus, repository corpus, bug corpus, testing corpus, prompt corpus, evaluation corpus, synthetic datasets. Version every dataset."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class DatasetCategory(Enum):
    CODE = "code"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    REPOSITORY = "repository"
    BUG = "bug"
    TESTING = "testing"
    PROMPT = "prompt"
    EVALUATION = "evaluation"
    SYNTHETIC = "synthetic"


@dataclass
class DatasetVersion:
    version: int
    size: int
    record_count: int
    hash: str
    changes: str = ""
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Dataset:
    id: str
    org_id: str
    name: str
    category: DatasetCategory
    description: str = ""
    records: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    current_version: int = 1
    tags: list = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    source: str = ""
    total_records: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Dataset":
        data = data.copy()
        data["category"] = DatasetCategory(data.get("category", "code"))
        return cls(**data)


class ResearchDatasets:
    def __init__(self, storage_dir: str = "research_data/datasets"):
        self.storage_dir = storage_dir
        self._datasets: dict[str, Dataset] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "datasets.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._datasets[k] = Dataset.from_dict(v)
                    except Exception as e: logger.warning("Skipping dataset %s: %s", k, e)
            except Exception as e: logger.error("Failed to load datasets: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._datasets.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save datasets: %s", e)

    def _compute_hash(self, records: list) -> str:
        return hashlib.sha256(json.dumps(records, default=str).encode()).hexdigest()[:16]

    def create_dataset(self, name: str, org_id: str, category: DatasetCategory = DatasetCategory.CODE, description: str = "", schema: dict = None) -> Dataset:
        ds = Dataset(id=str(uuid.uuid4()), org_id=org_id, name=name, category=category, description=description, schema=schema or {})
        self._datasets[ds.id] = ds
        self._save()
        return ds

    def get_dataset(self, ds_id: str) -> Optional[Dataset]: return self._datasets.get(ds_id)

    def add_records(self, ds_id: str, records: list, changes: str = "") -> Optional[Dataset]:
        ds = self._datasets.get(ds_id)
        if not ds: return None
        ds.current_version += 1
        ds.records.extend(records)
        ds.total_records = len(ds.records)
        ds.versions.append(DatasetVersion(
            version=ds.current_version, size=len(json.dumps(records, default=str).encode()),
            record_count=len(records), hash=self._compute_hash(records),
            changes=changes or f"Added {len(records)} records",
        ))
        ds.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return ds

    def update_records(self, ds_id: str, records: list, changes: str = "") -> Optional[Dataset]:
        ds = self._datasets.get(ds_id)
        if not ds: return None
        ds.current_version += 1
        ds.records = records
        ds.total_records = len(records)
        ds.versions.append(DatasetVersion(
            version=ds.current_version, size=len(json.dumps(records, default=str).encode()),
            record_count=len(records), hash=self._compute_hash(records),
            changes=changes or f"Replaced with {len(records)} records",
        ))
        ds.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return ds

    def get_version(self, ds_id: str, version: int) -> Optional[DatasetVersion]:
        ds = self._datasets.get(ds_id)
        if not ds: return None
        for v in ds.versions:
            if v.version == version: return v
        return None

    def list_datasets(self, org_id: str = "", category: Optional[DatasetCategory] = None) -> list[Dataset]:
        results = list(self._datasets.values())
        if org_id: results = [d for d in results if d.org_id == org_id]
        if category: results = [d for d in results if d.category == category]
        return results

    def search_datasets(self, query: str) -> list[Dataset]:
        q = query.lower()
        return [d for d in self._datasets.values() if q in d.name.lower() or q in d.description.lower()]

    def delete_dataset(self, ds_id: str) -> bool:
        if ds_id not in self._datasets: return False
        del self._datasets[ds_id]
        self._save()
        return True

    def generate_synthetic_dataset(self, name: str, org_id: str, template: dict, count: int = 100) -> Dataset:
        import random, string
        ds = self.create_dataset(name, org_id, DatasetCategory.SYNTHETIC, f"Synthetic dataset with {count} records")
        records = []
        for _ in range(count):
            record = {}
            for key, val_type in template.items():
                if val_type == "string": record[key] = "".join(random.choices(string.ascii_lowercase, k=10))
                elif val_type == "int": record[key] = random.randint(0, 1000)
                elif val_type == "float": record[key] = round(random.uniform(0, 1), 4)
                elif val_type == "bool": record[key] = random.choice([True, False])
                else: record[key] = val_type
            records.append(record)
        self.add_records(ds.id, records, "Auto-generated synthetic dataset")
        return ds

    def get_telemetry(self) -> dict: return dict(self._telemetry)
