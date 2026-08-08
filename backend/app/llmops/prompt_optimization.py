import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math, re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class OptimizationGoal(Enum):
    MINIMIZE_TOKENS = "minimize_tokens"
    MINIMIZE_LATENCY = "minimize_latency"
    MINIMIZE_COST = "minimize_cost"
    MAXIMIZE_ACCURACY = "maximize_accuracy"
    MAXIMIZE_REASONING = "maximize_reasoning"
    BALANCED = "balanced"


class OptimizationTechnique(Enum):
    PROMPT_COMPRESSION = "prompt_compression"
    TEMPLATE_OPTIMIZATION = "template_optimization"
    VARIABLE_EXTRACTION = "variable_extraction"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    FEW_SHOT_SELECTION = "few_shot_selection"
    CONTEXT_TRIMMING = "context_trimming"
    LENGTH_ADAPTATION = "length_adaptation"


@dataclass
class OptimizationRequest:
    id: str = ""
    prompt_id: str = ""
    version: int = 1
    goal: OptimizationGoal = OptimizationGoal.BALANCED
    constraints: dict = field(default_factory=dict)
    techniques: list[OptimizationTechnique] = field(default_factory=list)
    original_content: str = ""
    optimized_content: str = ""
    token_reduction_pct: float = 0.0
    latency_reduction_pct: float = 0.0
    cost_reduction_pct: float = 0.0
    accuracy_impact: float = 0.0
    created_at: str = ""
    status: str = "pending"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["goal"] = self.goal.value
        d["techniques"] = [t.value for t in self.techniques]
        return d

    @staticmethod
    def from_dict(data: dict) -> "OptimizationRequest":
        data = data.copy()
        data["goal"] = OptimizationGoal(data.get("goal", "balanced"))
        data["techniques"] = [OptimizationTechnique(t) for t in data.get("techniques", [])]
        return OptimizationRequest(**data)


@dataclass
class PromptTemplate:
    id: str = ""
    name: str = ""
    template: str = ""
    variables: list[str] = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    description: str = ""
    version: int = 1
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "PromptTemplate":
        return PromptTemplate(**data)


@dataclass
class CompressionResult:
    id: str = ""
    prompt_id: str = ""
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0
    preserved_meaning: float = 0.0
    technique_used: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "CompressionResult":
        return CompressionResult(**data)


class PromptOptimizer:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._requests_file = self.storage_dir / "optimization_requests.json"
        self._compressions_file = self.storage_dir / "compression_results.json"
        self._requests: dict[str, OptimizationRequest] = {}
        self._compressions: dict[str, CompressionResult] = {}
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("PromptOptimizer initialized at %s", storage_dir)

    def _save(self):
        try:
            self._requests_file.write_text(json.dumps({k: v.to_dict() for k, v in self._requests.items()}, indent=2))
            self._compressions_file.write_text(json.dumps({k: v.to_dict() for k, v in self._compressions.items()}, indent=2))
        except Exception as e:
            logger.error("Failed to save optimization data: %s", e)
            raise

    def _load(self):
        try:
            if self._requests_file.exists():
                data = json.loads(self._requests_file.read_text())
                self._requests = {k: OptimizationRequest.from_dict(v) for k, v in data.items()}
            if self._compressions_file.exists():
                data = json.loads(self._compressions_file.read_text())
                self._compressions = {k: CompressionResult.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error("Failed to load optimization data: %s", e)

    def _estimate_tokens(self, content: str) -> int:
        return len(re.findall(r"\S+", content)) + len(content) // 4

    def _remove_redundant_whitespace(self, content: str) -> str:
        return re.sub(r"\s+", " ", content).strip()

    def _remove_redundant_instructions(self, content: str) -> str:
        lines = content.splitlines()
        filtered = [l for l in lines if not re.match(r"^\s*(Note:|Hint:|Remember:|Important:)", l, re.IGNORECASE)]
        return "\n".join(filtered)

    def _shorten_examples(self, content: str, max_examples: int = 2) -> str:
        lines = content.splitlines()
        result = []
        example_count = 0
        for line in lines:
            if re.match(r"^\s*(Example|e\.g\.|for example)", line, re.IGNORECASE):
                example_count += 1
                if example_count > max_examples:
                    continue
            result.append(line)
        return "\n".join(result)

    def optimize(self, request: OptimizationRequest) -> OptimizationRequest:
        request.status = "running"
        original = request.original_content
        optimized = original
        for technique in request.techniques:
            if technique == OptimizationTechnique.PROMPT_COMPRESSION:
                optimized = self._remove_redundant_whitespace(optimized)
                optimized = self._remove_redundant_instructions(optimized)
                optimized = self._shorten_examples(optimized)
            elif technique == OptimizationTechnique.CONTEXT_TRIMMING:
                max_len = request.constraints.get("max_tokens", 2048)
                tokens = self._estimate_tokens(optimized)
                if tokens > max_len:
                    ratio = max_len / tokens
                    trim_len = int(len(optimized) * ratio)
                    optimized = optimized[:trim_len]
            elif technique == OptimizationTechnique.LENGTH_ADAPTATION:
                target_len = request.constraints.get("target_length", 500)
                if len(optimized) > target_len:
                    optimized = optimized[:target_len]
        orig_tokens = self._estimate_tokens(original)
        opt_tokens = self._estimate_tokens(optimized)
        request.optimized_content = optimized
        request.token_reduction_pct = round((1 - opt_tokens / max(orig_tokens, 1)) * 100, 2)
        request.latency_reduction_pct = round(request.token_reduction_pct * 0.8, 2)
        request.cost_reduction_pct = round(request.token_reduction_pct * 0.9, 2)
        request.accuracy_impact = round(max(0, request.token_reduction_pct * 0.01), 4)
        request.status = "completed"
        self._requests[request.id] = request
        if request.token_reduction_pct > 0:
            cr = CompressionResult(
                prompt_id=request.prompt_id,
                original_tokens=orig_tokens,
                compressed_tokens=opt_tokens,
                compression_ratio=round(opt_tokens / max(orig_tokens, 1), 4),
                preserved_meaning=round(1.0 - request.accuracy_impact, 4),
                technique_used=",".join(t.value for t in request.techniques),
            )
            self._compressions[cr.id] = cr
        self._save()
        self._telemetry["optimizations_completed"] += 1
        return request

    def compress_prompt(self, prompt_id: str, content: str, target_tokens: Optional[int] = None) -> CompressionResult:
        orig_tokens = self._estimate_tokens(content)
        compressed = self._remove_redundant_whitespace(self._remove_redundant_instructions(content))
        if target_tokens:
            tokens = self._estimate_tokens(compressed)
            if tokens > target_tokens:
                ratio = target_tokens / tokens
                trim_len = int(len(compressed) * ratio)
                compressed = compressed[:trim_len]
        comp_tokens = self._estimate_tokens(compressed)
        result = CompressionResult(
            prompt_id=prompt_id,
            original_tokens=orig_tokens,
            compressed_tokens=comp_tokens,
            compression_ratio=round(comp_tokens / max(orig_tokens, 1), 4),
            preserved_meaning=round(1.0 - (orig_tokens - comp_tokens) / max(orig_tokens, 1) * 0.1, 4),
            technique_used="prompt_compression",
        )
        self._compressions[result.id] = result
        self._save()
        self._telemetry["compressions_completed"] += 1
        return result

    def extract_variables(self, content: str) -> list[str]:
        pattern = r"\{\{(\w+)\}\}|<(\w+)>|\{(\w+)\}"
        matches = re.findall(pattern, content)
        variables = set()
        for m in matches:
            for g in m:
                if g:
                    variables.add(g)
        return sorted(variables)

    def suggest_template(self, content: str) -> str:
        variables = self.extract_variables(content)
        templated = content
        for var in variables:
            templated = templated.replace(f"{{{var}}}", f"{{{{{var}}}}}")
            templated = templated.replace(f"<{var}>", f"{{{{{var}}}}}")
        return templated

    def analyze_token_usage(self, content: str) -> dict:
        tokens = self._estimate_tokens(content)
        words = len(re.findall(r"\S+", content))
        chars = len(content)
        lines = len(content.splitlines())
        return {
            "tokens": tokens,
            "words": words,
            "characters": chars,
            "lines": lines,
            "avg_tokens_per_line": round(tokens / max(lines, 1), 2),
            "avg_chars_per_token": round(chars / max(tokens, 1), 2),
        }

    def suggest_chunking(self, content: str, chunk_size: int = 512) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", content)
        chunks = []
        current = []
        current_len = 0
        for sentence in sentences:
            sent_tokens = self._estimate_tokens(sentence)
            if current_len + sent_tokens > chunk_size and current:
                chunks.append(" ".join(current))
                current = [sentence]
                current_len = sent_tokens
            else:
                current.append(sentence)
                current_len += sent_tokens
        if current:
            chunks.append(" ".join(current))
        return chunks

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


class TemplateManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._templates_file = self.storage_dir / "prompt_templates.json"
        self._templates: dict[str, PromptTemplate] = {}
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("TemplateManager initialized at %s", storage_dir)

    def _save(self):
        try:
            self._templates_file.write_text(json.dumps({k: v.to_dict() for k, v in self._templates.items()}, indent=2))
        except Exception as e:
            logger.error("Failed to save templates: %s", e)
            raise

    def _load(self):
        try:
            if self._templates_file.exists():
                data = json.loads(self._templates_file.read_text())
                self._templates = {k: PromptTemplate.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error("Failed to load templates: %s", e)

    def create_template(self, name: str, template: str, variables: list[str],
                        defaults: dict, description: str = "") -> PromptTemplate:
        pt = PromptTemplate(
            name=name,
            template=template,
            variables=variables,
            defaults=defaults,
            description=description,
        )
        self._templates[pt.id] = pt
        self._save()
        self._telemetry["templates_created"] += 1
        return pt

    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        return self._templates.get(template_id)

    def update_template(self, template_id: str, **updates) -> Optional[PromptTemplate]:
        pt = self._templates.get(template_id)
        if not pt:
            return None
        for key, val in updates.items():
            if hasattr(pt, key):
                setattr(pt, key, val)
        pt.version += 1
        self._save()
        self._telemetry["templates_updated"] += 1
        return pt

    def render_template(self, template_id: str, variables: dict[str, str]) -> Optional[str]:
        pt = self._templates.get(template_id)
        if not pt:
            return None
        content = pt.template
        merged = {**pt.defaults, **variables}
        for var in pt.variables:
            placeholder = "{{" + var + "}}"
            value = merged.get(var, "")
            content = content.replace(placeholder, value)
        self._telemetry["templates_rendered"] += 1
        return content

    def list_templates(self) -> list[PromptTemplate]:
        return list(self._templates.values())

    def suggest_variables(self, template: str) -> list[str]:
        pattern = r"\{\{(\w+)\}\}"
        return sorted(set(re.findall(pattern, template)))

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


class OptimizationEngine(PromptOptimizer, TemplateManager):
    def __init__(self, storage_dir: str):
        PromptOptimizer.__init__(self, storage_dir)
        TemplateManager.__init__(self, storage_dir)
        self._suggestions_file = self.storage_dir / "optimization_suggestions.json"
        self._suggestions: list[dict] = []
        self._load_suggestions()
        logger.info("OptimizationEngine initialized at %s", storage_dir)

    def _load_suggestions(self):
        try:
            if self._suggestions_file.exists():
                self._suggestions = json.loads(self._suggestions_file.read_text())
        except Exception as e:
            logger.error("Failed to load optimization suggestions: %s", e)

    def _save_suggestions(self):
        try:
            self._suggestions_file.write_text(json.dumps(self._suggestions, indent=2))
        except Exception as e:
            logger.error("Failed to save optimization suggestions: %s", e)

    def auto_optimize(self, prompt_id: str, content: str, goal: OptimizationGoal = OptimizationGoal.BALANCED) -> OptimizationRequest:
        techniques = []
        if goal in (OptimizationGoal.MINIMIZE_TOKENS, OptimizationGoal.BALANCED):
            techniques.append(OptimizationTechnique.PROMPT_COMPRESSION)
        if goal == OptimizationGoal.MINIMIZE_COST:
            techniques.extend([OptimizationTechnique.PROMPT_COMPRESSION, OptimizationTechnique.LENGTH_ADAPTATION])
        if goal == OptimizationGoal.MAXIMIZE_ACCURACY:
            techniques.append(OptimizationTechnique.CHAIN_OF_THOUGHT)
        if goal == OptimizationGoal.MINIMIZE_LATENCY:
            techniques.extend([OptimizationTechnique.PROMPT_COMPRESSION, OptimizationTechnique.CONTEXT_TRIMMING])
        request = OptimizationRequest(
            prompt_id=prompt_id,
            goal=goal,
            techniques=techniques,
            original_content=content,
        )
        return self.optimize(request)

    def batch_optimize(self, items: list[dict]) -> list[OptimizationRequest]:
        results = []
        for item in items:
            req = self.auto_optimize(
                prompt_id=item.get("prompt_id", ""),
                content=item.get("content", ""),
                goal=OptimizationGoal(item.get("goal", "balanced")),
            )
            results.append(req)
        self._telemetry["batch_optimizations"] += 1
        return results

    def get_optimization_suggestions(self, content: str) -> list[dict]:
        suggestions = []
        analysis = self.analyze_token_usage(content)
        if analysis["tokens"] > 1000:
            suggestions.append({
                "type": "compression",
                "message": f"Prompt has {analysis['tokens']} tokens. Consider compression.",
                "estimated_savings": f"~{int(analysis['tokens'] * 0.3)} tokens",
            })
        variables = self.extract_variables(content)
        if variables:
            suggestions.append({
                "type": "template",
                "message": f"Found {len(variables)} variables: {', '.join(variables)}. Consider creating a template.",
                "variables": variables,
            })
        lines = content.splitlines()
        long_lines = [i + 1 for i, l in enumerate(lines) if len(l) > 500]
        if long_lines:
            suggestions.append({
                "type": "chunking",
                "message": f"Long lines detected at lines {long_lines}. Consider chunking.",
                "lines": long_lines,
            })
        self._suggestions.extend(suggestions)
        self._save_suggestions()
        self._telemetry["suggestions_generated"] += 1
        return suggestions
