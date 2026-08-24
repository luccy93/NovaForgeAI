"""NovaForge SDK — AI Governance & MLOps (Volume 58).

Provides :class:`AIMLMixin` (sync) and :class:`AsyncAIMLMixin` (async) that add
methods for model registry, providers, prompts, evaluations, guardrails,
policies, risks, cards, approvals, gateway, monitoring and provenance. They
compose with ``NovaForgeClient`` / ``AsyncNovaForgeClient`` and return the
parsed JSON responses from the ``/api/v1/ai`` endpoints.

Usage:
    from backend.sdk import NovaForgeClient
    from backend.sdk.aiml import AIMLMixin

    class MyClient(AIMLMixin, NovaForgeClient):
        pass
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Sync mixin
# ---------------------------------------------------------------------------


class AIMLMixin:
    """Mixin that adds AI Governance & MLOps methods to ``NovaForgeClient``.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()``, ``self.delete()`` and ``self._build_url()``.
    """

    # ─── Models ───────────────────────────────────────────────────────────

    def register_model(
        self,
        provider: str,
        name: str,
        version: str,
        type: str = "foundation",  # noqa: A002
        capabilities: Optional[dict] = None,
        license: Optional[str] = None,  # noqa: A002
        region: Optional[str] = None,
        risk_level: str = "LOW",
        owner: Optional[str] = None,
    ) -> dict:
        """Register a new model."""
        payload: dict[str, Any] = {
            "provider": provider,
            "name": name,
            "version": version,
            "type": type,
            "risk_level": risk_level,
        }
        if capabilities is not None:
            payload["capabilities"] = capabilities
        if license is not None:
            payload["license"] = license
        if region is not None:
            payload["region"] = region
        if owner is not None:
            payload["owner"] = owner
        return self.post(self._build_url("/ai/models"), data=payload)

    def get_model(self, model_id: str) -> dict:
        """Get a single model by id."""
        return self.get(self._build_url(f"/ai/models/{model_id}"))

    def list_models(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        type: Optional[str] = None,  # noqa: A002
    ) -> list[dict]:
        """List models with optional filters."""
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        if status is not None:
            params["status"] = status
        if region is not None:
            params["region"] = region
        if type is not None:
            params["type"] = type
        return self.get(self._build_url("/ai/models"), params=params)

    def approve_model(self, model_id: str) -> dict:
        """Approve a model (status -> APPROVED)."""
        return self.post(self._build_url(f"/ai/models/{model_id}/approve"))

    def block_model(self, model_id: str) -> dict:
        """Block a model (status -> BLOCKED)."""
        return self.post(self._build_url(f"/ai/models/{model_id}/block"))

    # alias for spec
    def block(self, model_id: str) -> dict:
        return self.block_model(model_id)

    # ─── Providers ────────────────────────────────────────────────────────

    def register_provider(
        self,
        provider: str,
        display_name: str,
        models: Optional[list] = None,
        regions: Optional[list] = None,
        pricing: Optional[dict] = None,
        data_processing_policy: Optional[dict] = None,
        availability: str = "AVAILABLE",
        security_status: str = "UNKNOWN",
        contract_metadata: Optional[dict] = None,
    ) -> dict:
        """Register a provider."""
        payload: dict[str, Any] = {
            "provider": provider,
            "display_name": display_name,
            "availability": availability,
            "security_status": security_status,
        }
        if models is not None:
            payload["models"] = models
        if regions is not None:
            payload["regions"] = regions
        if pricing is not None:
            payload["pricing"] = pricing
        if data_processing_policy is not None:
            payload["data_processing_policy"] = data_processing_policy
        if contract_metadata is not None:
            payload["contract_metadata"] = contract_metadata
        return self.post(self._build_url("/ai/providers"), data=payload)

    def get_provider(self, provider: str) -> dict:
        """Get a provider by key or id."""
        return self.get(self._build_url(f"/ai/providers/{provider}"))

    def list_providers(
        self,
        provider: Optional[str] = None,
        availability: Optional[str] = None,
        region: Optional[str] = None,
    ) -> list[dict]:
        """List providers."""
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        if availability is not None:
            params["availability"] = availability
        if region is not None:
            params["region"] = region
        return self.get(self._build_url("/ai/providers"), params=params)

    def check_provider(self, provider: str) -> dict:
        """Check provider compliance/status."""
        # Compliance check — uses provider detail endpoint (no claim without evidence)
        return self.get(self._build_url(f"/ai/providers/{provider}"))

    # alias
    def provider_check(self, provider: str) -> dict:
        return self.check_provider(provider)

    # ─── Prompts ──────────────────────────────────────────────────────────

    def register_prompt(
        self,
        prompt_id: str,
        name: str,
        content: str,
        purpose: Optional[str] = None,
        classification: str = "INTERNAL",
        model_compatibility: Optional[list] = None,
        owner: Optional[str] = None,
    ) -> dict:
        """Register a prompt with initial version."""
        payload: dict[str, Any] = {
            "prompt_id": prompt_id,
            "name": name,
            "content": content,
            "classification": classification,
        }
        if purpose is not None:
            payload["purpose"] = purpose
        if model_compatibility is not None:
            payload["model_compatibility"] = model_compatibility
        if owner is not None:
            payload["owner"] = owner
        return self.post(self._build_url("/ai/prompts"), data=payload)

    def get_prompt(self, prompt_id: str, version: Optional[str] = None) -> dict:
        """Get prompt by business id or registry id, optionally version."""
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version
        return self.get(self._build_url(f"/ai/prompts/{prompt_id}"), params=params)

    def list_prompts(self, classification: Optional[str] = None) -> list[dict]:
        """List prompts."""
        params: dict[str, Any] = {}
        if classification is not None:
            params["classification"] = classification
        return self.get(self._build_url("/ai/prompts"), params=params)

    def create_prompt_version(
        self,
        prompt_id: str,
        content: str,
        owner: Optional[str] = None,
        purpose: Optional[str] = None,
        classification: Optional[str] = None,
    ) -> dict:
        """Create a new immutable prompt version."""
        payload: dict[str, Any] = {"content": content}
        if owner is not None:
            payload["owner"] = owner
        if purpose is not None:
            payload["purpose"] = purpose
        if classification is not None:
            payload["classification"] = classification
        return self.post(self._build_url(f"/ai/prompts/{prompt_id}/versions"), data=payload)

    def evaluate_prompt(
        self,
        prompt_id: str,
        dataset_id: str,
        dataset_version: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Evaluate a prompt version against a dataset."""
        payload: dict[str, Any] = {"dataset_id": dataset_id}
        if dataset_version is not None:
            payload["dataset_version"] = dataset_version
        if model is not None:
            payload["model"] = model
        return self.post(self._build_url(f"/ai/prompts/{prompt_id}/evaluate"), data=payload)

    # ─── Evaluations ──────────────────────────────────────────────────────

    def create_suite(
        self,
        name: str,
        suite_type: str,
        dataset_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> dict:
        """Create an evaluation suite."""
        payload: dict[str, Any] = {"name": name, "suite_type": suite_type}
        if dataset_id is not None:
            payload["dataset_id"] = dataset_id
        if config is not None:
            payload["config"] = config
        return self.post(self._build_url("/ai/evaluations/suites"), data=payload)

    def create_run(
        self,
        suite_id: str,
        model_id: Optional[str] = None,
        prompt_version_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> dict:
        """Create an evaluation run."""
        payload: dict[str, Any] = {"suite_id": suite_id}
        if model_id is not None:
            payload["model_id"] = model_id
        if prompt_version_id is not None:
            payload["prompt_version_id"] = prompt_version_id
        if dataset_version is not None:
            payload["dataset_version"] = dataset_version
        if parameters is not None:
            payload["parameters"] = parameters
        return self.post(self._build_url("/ai/evaluations/runs"), data=payload)

    def complete_run(
        self,
        run_id: str,
        metrics: Optional[dict] = None,
        artifacts: Optional[dict] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Complete an evaluation run with metrics."""
        payload: dict[str, Any] = {}
        if metrics is not None:
            payload["metrics"] = metrics
        if artifacts is not None:
            payload["artifacts"] = artifacts
        if status is not None:
            payload["status"] = status
        return self.post(self._build_url(f"/ai/evaluations/runs/{run_id}/complete"), data=payload)

    def compare_evaluations(self, candidate_run_id: str, baseline_run_id: str) -> dict:
        """Compare candidate vs baseline evaluation runs."""
        params: dict[str, Any] = {"candidate_run_id": candidate_run_id, "baseline_run_id": baseline_run_id}
        return self.get(self._build_url("/ai/evaluations/compare"), params=params)

    # alias
    def compare(self, candidate_run_id: str, baseline_run_id: str) -> dict:
        return self.compare_evaluations(candidate_run_id, baseline_run_id)

    # ─── Guardrails ───────────────────────────────────────────────────────

    def create_guardrail(
        self,
        name: str,
        scope: str = "input",
        policy: Optional[dict] = None,
        rate_limit: Optional[int] = None,
        environment: Optional[str] = None,
    ) -> dict:
        """Create a guardrail."""
        payload: dict[str, Any] = {"name": name, "scope": scope}
        if policy is not None:
            payload["policy"] = policy
        if rate_limit is not None:
            payload["rate_limit"] = rate_limit
        if environment is not None:
            payload["environment"] = environment
        return self.post(self._build_url("/ai/guardrails"), data=payload)

    def check_input(
        self,
        content: str,
        classification: str = "INTERNAL",
        environment: Optional[str] = None,
    ) -> dict:
        """Check input content through guardrails."""
        payload: dict[str, Any] = {"content": content, "classification": classification}
        if environment is not None:
            payload["environment"] = environment
        return self.post(self._build_url("/ai/guardrails/check-input"), data=payload)

    def check_output(
        self,
        content: str,
        classification: str = "INTERNAL",
        environment: Optional[str] = None,
    ) -> dict:
        """Check output content through guardrails."""
        payload: dict[str, Any] = {"content": content, "classification": classification}
        if environment is not None:
            payload["environment"] = environment
        return self.post(self._build_url("/ai/guardrails/check-output"), data=payload)

    # aliases
    def check_guardrail_input(self, content: str, classification: str = "INTERNAL", environment: Optional[str] = None) -> dict:
        return self.check_input(content, classification, environment)

    def check_guardrail_output(self, content: str, classification: str = "INTERNAL", environment: Optional[str] = None) -> dict:
        return self.check_output(content, classification, environment)

    # ─── Policies ─────────────────────────────────────────────────────────

    def create_policy(
        self,
        name: str,
        policy_type: str,
        effect: str,
        priority: int = 0,
        conditions: Optional[Any] = None,
    ) -> dict:
        """Create a policy."""
        payload: dict[str, Any] = {"name": name, "policy_type": policy_type, "effect": effect, "priority": priority}
        if conditions is not None:
            payload["conditions"] = conditions
        return self.post(self._build_url("/ai/policies"), data=payload)

    def evaluate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        """Evaluate resource/context against policies."""
        payload: dict[str, Any] = {"resource": resource}
        if context is not None:
            payload["context"] = context
        return self.post(self._build_url("/ai/policies/evaluate"), data=payload)

    def simulate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        """Simulate policy evaluation (dry-run)."""
        payload: dict[str, Any] = {"resource": resource}
        if context is not None:
            payload["context"] = context
        return self.post(self._build_url("/ai/policies/simulate"), data=payload)

    # ─── Risks ────────────────────────────────────────────────────────────

    def create_risk(
        self,
        system: str,
        risk_id: str,
        severity: str,
        likelihood: str,
        impact: str,
        model_id: Optional[str] = None,
        owner: Optional[str] = None,
        mitigation: Optional[str] = None,
    ) -> dict:
        """Create a risk record."""
        payload: dict[str, Any] = {"system": system, "risk_id": risk_id, "severity": severity, "likelihood": likelihood, "impact": impact}
        if model_id is not None:
            payload["model_id"] = model_id
        if owner is not None:
            payload["owner"] = owner
        if mitigation is not None:
            payload["mitigation"] = mitigation
        return self.post(self._build_url("/ai/risks"), data=payload)

    def list_risks(
        self,
        system: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List risks."""
        params: dict[str, Any] = {}
        if system is not None:
            params["system"] = system
        if severity is not None:
            params["severity"] = severity
        if status is not None:
            params["status"] = status
        return self.get(self._build_url("/ai/risks"), params=params)

    # alias
    def create(self, *args, **kwargs):
        return self.create_risk(*args, **kwargs)

    # ─── Cards ────────────────────────────────────────────────────────────

    def create_model_card(
        self,
        model_id: str,
        purpose: Optional[str] = None,
        capabilities: Optional[Any] = None,
        limitations: Optional[Any] = None,
        risk: Optional[str] = None,
        evaluation_summary: Optional[dict] = None,
        data_policy: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        approved_environments: Optional[list] = None,
    ) -> dict:
        """Create a model card."""
        payload: dict[str, Any] = {"model_id": model_id}
        if purpose is not None:
            payload["purpose"] = purpose
        if capabilities is not None:
            payload["capabilities"] = capabilities
        if limitations is not None:
            payload["limitations"] = limitations
        if risk is not None:
            payload["risk"] = risk
        if evaluation_summary is not None:
            payload["evaluation_summary"] = evaluation_summary
        if data_policy is not None:
            payload["data_policy"] = data_policy
        if provider is not None:
            payload["provider"] = provider
        if version is not None:
            payload["version"] = version
        if approved_environments is not None:
            payload["approved_environments"] = approved_environments
        return self.post(self._build_url("/ai/model-cards"), data=payload)

    def get_model_card(self, model_id: str) -> dict:
        """Get model card(s) by model id or card id."""
        return self.get(self._build_url(f"/ai/model-cards/{model_id}"))

    def create_system_card(
        self,
        system: str,
        purpose: Optional[str] = None,
        inputs: Optional[dict] = None,
        outputs: Optional[dict] = None,
        models: Optional[list] = None,
        tools: Optional[list] = None,
        permissions: Optional[list] = None,
        human_oversight: Optional[str] = None,
        failure_modes: Optional[list] = None,
        evaluation: Optional[dict] = None,
        deployment_scope: Optional[str] = None,
    ) -> dict:
        """Create a system card."""
        payload: dict[str, Any] = {"system": system}
        if purpose is not None:
            payload["purpose"] = purpose
        if inputs is not None:
            payload["inputs"] = inputs
        if outputs is not None:
            payload["outputs"] = outputs
        if models is not None:
            payload["models"] = models
        if tools is not None:
            payload["tools"] = tools
        if permissions is not None:
            payload["permissions"] = permissions
        if human_oversight is not None:
            payload["human_oversight"] = human_oversight
        if failure_modes is not None:
            payload["failure_modes"] = failure_modes
        if evaluation is not None:
            payload["evaluation"] = evaluation
        if deployment_scope is not None:
            payload["deployment_scope"] = deployment_scope
        return self.post(self._build_url("/ai/system-cards"), data=payload)

    def get_system_card(self, system: str) -> dict:
        """Get system card(s) by system name or card id."""
        return self.get(self._build_url(f"/ai/system-cards/{system}"))

    # ─── Approvals ────────────────────────────────────────────────────────

    def request_approval(
        self,
        request_type: str,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> dict:
        """Request approval."""
        payload: dict[str, Any] = {"request_type": request_type}
        if model_id is not None:
            payload["model_id"] = model_id
        if provider is not None:
            payload["provider"] = provider
        if version is not None:
            payload["version"] = version
        if reason is not None:
            payload["reason"] = reason
        return self.post(self._build_url("/ai/approvals"), data=payload)

    def decide_approval(self, approval_id: str, approver: str, decision: str) -> dict:
        """Decide approval."""
        payload: dict[str, Any] = {"approver": approver, "decision": decision}
        return self.post(self._build_url(f"/ai/approvals/{approval_id}/decide"), data=payload)

    # alias
    def approve(self, approval_id: str, approver: str, decision: str = "approved") -> dict:
        return self.decide_approval(approval_id, approver, decision)

    # ─── Gateway ──────────────────────────────────────────────────────────

    def gateway_route(
        self,
        purpose: Optional[str] = None,
        data_classification: str = "INTERNAL",
        model_hint: Optional[str] = None,
        provider_hint: Optional[str] = None,
        region_hint: Optional[str] = None,
        budget: Optional[float] = None,
        policy_context: Optional[dict] = None,
    ) -> dict:
        """Route request to best model/provider."""
        payload: dict[str, Any] = {"data_classification": data_classification}
        if purpose is not None:
            payload["purpose"] = purpose
        if model_hint is not None:
            payload["model_hint"] = model_hint
        if provider_hint is not None:
            payload["provider_hint"] = provider_hint
        if region_hint is not None:
            payload["region_hint"] = region_hint
        if budget is not None:
            payload["budget"] = budget
        if policy_context is not None:
            payload["policy_context"] = policy_context
        return self.post(self._build_url("/ai/gateway/route"), data=payload)

    def gateway_invoke(
        self,
        model_id: str,
        prompt: str,
        data_classification: str = "INTERNAL",
        purpose: Optional[str] = None,
    ) -> dict:
        """Invoke a model via gateway."""
        payload: dict[str, Any] = {"model_id": model_id, "prompt": prompt, "data_classification": data_classification}
        if purpose is not None:
            payload["purpose"] = purpose
        return self.post(self._build_url("/ai/gateway/invoke"), data=payload)

    # aliases
    def route(self, *args, **kwargs) -> dict:
        return self.gateway_route(*args, **kwargs)

    def invoke(self, *args, **kwargs) -> dict:
        return self.gateway_invoke(*args, **kwargs)

    # ─── Monitoring ───────────────────────────────────────────────────────

    def record_snapshot(
        self,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        availability: Optional[str] = None,
        latency_ms: Optional[float] = None,
        error_rate: Optional[float] = None,
        token_usage: Optional[int] = None,
        cost: Optional[float] = None,
        quality: Optional[float] = None,
        safety: Optional[float] = None,
        drift: Optional[dict] = None,
    ) -> dict:
        """Record a monitoring snapshot."""
        payload: dict[str, Any] = {}
        if model_id is not None:
            payload["model_id"] = model_id
        if provider is not None:
            payload["provider"] = provider
        if availability is not None:
            payload["availability"] = availability
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if error_rate is not None:
            payload["error_rate"] = error_rate
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if cost is not None:
            payload["cost"] = cost
        if quality is not None:
            payload["quality"] = quality
        if safety is not None:
            payload["safety"] = safety
        if drift is not None:
            payload["drift"] = drift
        return self.post(self._build_url("/ai/monitoring/snapshots"), data=payload)

    def get_snapshots(self, model_id: str, limit: int = 100) -> list[dict]:
        """Get monitoring snapshots for a model."""
        return self.get(self._build_url(f"/ai/monitoring/{model_id}"), params={"limit": limit})

    def detect_drift(
        self,
        model_id: Optional[str] = None,
        window: int = 100,
    ) -> dict:
        """Detect drift for a model."""
        payload: dict[str, Any] = {"window": window}
        if model_id is not None:
            payload["model_id"] = model_id
        return self.post(self._build_url("/ai/monitoring/drift"), data=payload)

    # ─── Provenance ───────────────────────────────────────────────────────

    def record_provenance(
        self,
        model_id: str,
        provider: Optional[str] = None,
        artifact: Optional[str] = None,
        source: Optional[str] = None,
        training_metadata: Optional[dict] = None,
        evaluation_version: Optional[str] = None,
        deployment_version: Optional[str] = None,
        policy_version: Optional[str] = None,
    ) -> dict:
        """Record provenance for a model version."""
        payload: dict[str, Any] = {"model_id": model_id}
        if provider is not None:
            payload["provider"] = provider
        if artifact is not None:
            payload["artifact"] = artifact
        if source is not None:
            payload["source"] = source
        if training_metadata is not None:
            payload["training_metadata"] = training_metadata
        if evaluation_version is not None:
            payload["evaluation_version"] = evaluation_version
        if deployment_version is not None:
            payload["deployment_version"] = deployment_version
        if policy_version is not None:
            payload["policy_version"] = policy_version
        return self.post(self._build_url(f"/ai/provenance/{model_id}"), data=payload)

    def get_provenance(self, model_id: str) -> dict:
        """Get provenance for a model."""
        return self.get(self._build_url(f"/ai/provenance/{model_id}"))

    # also support generic record/get
    def record(self, model_id: str, **kwargs) -> dict:
        return self.record_provenance(model_id, **kwargs)


# ---------------------------------------------------------------------------
# Async mixin
# ---------------------------------------------------------------------------


class AsyncAIMLMixin:
    """Mixin that adds AI Governance & MLOps methods to ``AsyncNovaForgeClient``.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()``, ``self.delete()`` and ``self._build_url()``.
    """

    # ─── Models ───────────────────────────────────────────────────────────

    async def register_model(
        self,
        provider: str,
        name: str,
        version: str,
        type: str = "foundation",  # noqa: A002
        capabilities: Optional[dict] = None,
        license: Optional[str] = None,  # noqa: A002
        region: Optional[str] = None,
        risk_level: str = "LOW",
        owner: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "provider": provider,
            "name": name,
            "version": version,
            "type": type,
            "risk_level": risk_level,
        }
        if capabilities is not None:
            payload["capabilities"] = capabilities
        if license is not None:
            payload["license"] = license
        if region is not None:
            payload["region"] = region
        if owner is not None:
            payload["owner"] = owner
        return await self.post(self._build_url("/ai/models"), data=payload)

    async def get_model(self, model_id: str) -> dict:
        return await self.get(self._build_url(f"/ai/models/{model_id}"))

    async def list_models(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        type: Optional[str] = None,  # noqa: A002
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        if status is not None:
            params["status"] = status
        if region is not None:
            params["region"] = region
        if type is not None:
            params["type"] = type
        return await self.get(self._build_url("/ai/models"), params=params)

    async def approve_model(self, model_id: str) -> dict:
        return await self.post(self._build_url(f"/ai/models/{model_id}/approve"))

    async def block_model(self, model_id: str) -> dict:
        return await self.post(self._build_url(f"/ai/models/{model_id}/block"))

    async def block(self, model_id: str) -> dict:
        return await self.block_model(model_id)

    # ─── Providers ────────────────────────────────────────────────────────

    async def register_provider(
        self,
        provider: str,
        display_name: str,
        models: Optional[list] = None,
        regions: Optional[list] = None,
        pricing: Optional[dict] = None,
        data_processing_policy: Optional[dict] = None,
        availability: str = "AVAILABLE",
        security_status: str = "UNKNOWN",
        contract_metadata: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "provider": provider,
            "display_name": display_name,
            "availability": availability,
            "security_status": security_status,
        }
        if models is not None:
            payload["models"] = models
        if regions is not None:
            payload["regions"] = regions
        if pricing is not None:
            payload["pricing"] = pricing
        if data_processing_policy is not None:
            payload["data_processing_policy"] = data_processing_policy
        if contract_metadata is not None:
            payload["contract_metadata"] = contract_metadata
        return await self.post(self._build_url("/ai/providers"), data=payload)

    async def get_provider(self, provider: str) -> dict:
        return await self.get(self._build_url(f"/ai/providers/{provider}"))

    async def list_providers(
        self,
        provider: Optional[str] = None,
        availability: Optional[str] = None,
        region: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        if availability is not None:
            params["availability"] = availability
        if region is not None:
            params["region"] = region
        return await self.get(self._build_url("/ai/providers"), params=params)

    async def check_provider(self, provider: str) -> dict:
        return await self.get(self._build_url(f"/ai/providers/{provider}"))

    async def provider_check(self, provider: str) -> dict:
        return await self.check_provider(provider)

    # ─── Prompts ──────────────────────────────────────────────────────────

    async def register_prompt(
        self,
        prompt_id: str,
        name: str,
        content: str,
        purpose: Optional[str] = None,
        classification: str = "INTERNAL",
        model_compatibility: Optional[list] = None,
        owner: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "prompt_id": prompt_id,
            "name": name,
            "content": content,
            "classification": classification,
        }
        if purpose is not None:
            payload["purpose"] = purpose
        if model_compatibility is not None:
            payload["model_compatibility"] = model_compatibility
        if owner is not None:
            payload["owner"] = owner
        return await self.post(self._build_url("/ai/prompts"), data=payload)

    async def get_prompt(self, prompt_id: str, version: Optional[str] = None) -> dict:
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version
        return await self.get(self._build_url(f"/ai/prompts/{prompt_id}"), params=params)

    async def list_prompts(self, classification: Optional[str] = None) -> list[dict]:
        params: dict[str, Any] = {}
        if classification is not None:
            params["classification"] = classification
        return await self.get(self._build_url("/ai/prompts"), params=params)

    async def create_prompt_version(
        self,
        prompt_id: str,
        content: str,
        owner: Optional[str] = None,
        purpose: Optional[str] = None,
        classification: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"content": content}
        if owner is not None:
            payload["owner"] = owner
        if purpose is not None:
            payload["purpose"] = purpose
        if classification is not None:
            payload["classification"] = classification
        return await self.post(self._build_url(f"/ai/prompts/{prompt_id}/versions"), data=payload)

    async def evaluate_prompt(
        self,
        prompt_id: str,
        dataset_id: str,
        dataset_version: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"dataset_id": dataset_id}
        if dataset_version is not None:
            payload["dataset_version"] = dataset_version
        if model is not None:
            payload["model"] = model
        return await self.post(self._build_url(f"/ai/prompts/{prompt_id}/evaluate"), data=payload)

    # ─── Evaluations ──────────────────────────────────────────────────────

    async def create_suite(
        self,
        name: str,
        suite_type: str,
        dataset_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"name": name, "suite_type": suite_type}
        if dataset_id is not None:
            payload["dataset_id"] = dataset_id
        if config is not None:
            payload["config"] = config
        return await self.post(self._build_url("/ai/evaluations/suites"), data=payload)

    async def create_run(
        self,
        suite_id: str,
        model_id: Optional[str] = None,
        prompt_version_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"suite_id": suite_id}
        if model_id is not None:
            payload["model_id"] = model_id
        if prompt_version_id is not None:
            payload["prompt_version_id"] = prompt_version_id
        if dataset_version is not None:
            payload["dataset_version"] = dataset_version
        if parameters is not None:
            payload["parameters"] = parameters
        return await self.post(self._build_url("/ai/evaluations/runs"), data=payload)

    async def complete_run(
        self,
        run_id: str,
        metrics: Optional[dict] = None,
        artifacts: Optional[dict] = None,
        status: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if metrics is not None:
            payload["metrics"] = metrics
        if artifacts is not None:
            payload["artifacts"] = artifacts
        if status is not None:
            payload["status"] = status
        return await self.post(self._build_url(f"/ai/evaluations/runs/{run_id}/complete"), data=payload)

    async def compare_evaluations(self, candidate_run_id: str, baseline_run_id: str) -> dict:
        params: dict[str, Any] = {"candidate_run_id": candidate_run_id, "baseline_run_id": baseline_run_id}
        return await self.get(self._build_url("/ai/evaluations/compare"), params=params)

    async def compare(self, candidate_run_id: str, baseline_run_id: str) -> dict:
        return await self.compare_evaluations(candidate_run_id, baseline_run_id)

    # ─── Guardrails ───────────────────────────────────────────────────────

    async def create_guardrail(
        self,
        name: str,
        scope: str = "input",
        policy: Optional[dict] = None,
        rate_limit: Optional[int] = None,
        environment: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"name": name, "scope": scope}
        if policy is not None:
            payload["policy"] = policy
        if rate_limit is not None:
            payload["rate_limit"] = rate_limit
        if environment is not None:
            payload["environment"] = environment
        return await self.post(self._build_url("/ai/guardrails"), data=payload)

    async def check_input(
        self,
        content: str,
        classification: str = "INTERNAL",
        environment: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"content": content, "classification": classification}
        if environment is not None:
            payload["environment"] = environment
        return await self.post(self._build_url("/ai/guardrails/check-input"), data=payload)

    async def check_output(
        self,
        content: str,
        classification: str = "INTERNAL",
        environment: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"content": content, "classification": classification}
        if environment is not None:
            payload["environment"] = environment
        return await self.post(self._build_url("/ai/guardrails/check-output"), data=payload)

    async def check_guardrail_input(self, content: str, classification: str = "INTERNAL", environment: Optional[str] = None) -> dict:
        return await self.check_input(content, classification, environment)

    async def check_guardrail_output(self, content: str, classification: str = "INTERNAL", environment: Optional[str] = None) -> dict:
        return await self.check_output(content, classification, environment)

    # ─── Policies ─────────────────────────────────────────────────────────

    async def create_policy(
        self,
        name: str,
        policy_type: str,
        effect: str,
        priority: int = 0,
        conditions: Optional[Any] = None,
    ) -> dict:
        payload: dict[str, Any] = {"name": name, "policy_type": policy_type, "effect": effect, "priority": priority}
        if conditions is not None:
            payload["conditions"] = conditions
        return await self.post(self._build_url("/ai/policies"), data=payload)

    async def evaluate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        payload: dict[str, Any] = {"resource": resource}
        if context is not None:
            payload["context"] = context
        return await self.post(self._build_url("/ai/policies/evaluate"), data=payload)

    async def simulate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        payload: dict[str, Any] = {"resource": resource}
        if context is not None:
            payload["context"] = context
        return await self.post(self._build_url("/ai/policies/simulate"), data=payload)

    # ─── Risks ────────────────────────────────────────────────────────────

    async def create_risk(
        self,
        system: str,
        risk_id: str,
        severity: str,
        likelihood: str,
        impact: str,
        model_id: Optional[str] = None,
        owner: Optional[str] = None,
        mitigation: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"system": system, "risk_id": risk_id, "severity": severity, "likelihood": likelihood, "impact": impact}
        if model_id is not None:
            payload["model_id"] = model_id
        if owner is not None:
            payload["owner"] = owner
        if mitigation is not None:
            payload["mitigation"] = mitigation
        return await self.post(self._build_url("/ai/risks"), data=payload)

    async def list_risks(
        self,
        system: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if system is not None:
            params["system"] = system
        if severity is not None:
            params["severity"] = severity
        if status is not None:
            params["status"] = status
        return await self.get(self._build_url("/ai/risks"), params=params)

    # ─── Cards ────────────────────────────────────────────────────────────

    async def create_model_card(
        self,
        model_id: str,
        purpose: Optional[str] = None,
        capabilities: Optional[Any] = None,
        limitations: Optional[Any] = None,
        risk: Optional[str] = None,
        evaluation_summary: Optional[dict] = None,
        data_policy: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        approved_environments: Optional[list] = None,
    ) -> dict:
        payload: dict[str, Any] = {"model_id": model_id}
        if purpose is not None:
            payload["purpose"] = purpose
        if capabilities is not None:
            payload["capabilities"] = capabilities
        if limitations is not None:
            payload["limitations"] = limitations
        if risk is not None:
            payload["risk"] = risk
        if evaluation_summary is not None:
            payload["evaluation_summary"] = evaluation_summary
        if data_policy is not None:
            payload["data_policy"] = data_policy
        if provider is not None:
            payload["provider"] = provider
        if version is not None:
            payload["version"] = version
        if approved_environments is not None:
            payload["approved_environments"] = approved_environments
        return await self.post(self._build_url("/ai/model-cards"), data=payload)

    async def get_model_card(self, model_id: str) -> dict:
        return await self.get(self._build_url(f"/ai/model-cards/{model_id}"))

    async def create_system_card(
        self,
        system: str,
        purpose: Optional[str] = None,
        inputs: Optional[dict] = None,
        outputs: Optional[dict] = None,
        models: Optional[list] = None,
        tools: Optional[list] = None,
        permissions: Optional[list] = None,
        human_oversight: Optional[str] = None,
        failure_modes: Optional[list] = None,
        evaluation: Optional[dict] = None,
        deployment_scope: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"system": system}
        if purpose is not None:
            payload["purpose"] = purpose
        if inputs is not None:
            payload["inputs"] = inputs
        if outputs is not None:
            payload["outputs"] = outputs
        if models is not None:
            payload["models"] = models
        if tools is not None:
            payload["tools"] = tools
        if permissions is not None:
            payload["permissions"] = permissions
        if human_oversight is not None:
            payload["human_oversight"] = human_oversight
        if failure_modes is not None:
            payload["failure_modes"] = failure_modes
        if evaluation is not None:
            payload["evaluation"] = evaluation
        if deployment_scope is not None:
            payload["deployment_scope"] = deployment_scope
        return await self.post(self._build_url("/ai/system-cards"), data=payload)

    async def get_system_card(self, system: str) -> dict:
        return await self.get(self._build_url(f"/ai/system-cards/{system}"))

    # ─── Approvals ────────────────────────────────────────────────────────

    async def request_approval(
        self,
        request_type: str,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"request_type": request_type}
        if model_id is not None:
            payload["model_id"] = model_id
        if provider is not None:
            payload["provider"] = provider
        if version is not None:
            payload["version"] = version
        if reason is not None:
            payload["reason"] = reason
        return await self.post(self._build_url("/ai/approvals"), data=payload)

    async def decide_approval(self, approval_id: str, approver: str, decision: str) -> dict:
        payload: dict[str, Any] = {"approver": approver, "decision": decision}
        return await self.post(self._build_url(f"/ai/approvals/{approval_id}/decide"), data=payload)

    async def approve(self, approval_id: str, approver: str, decision: str = "approved") -> dict:
        return await self.decide_approval(approval_id, approver, decision)

    # ─── Gateway ──────────────────────────────────────────────────────────

    async def gateway_route(
        self,
        purpose: Optional[str] = None,
        data_classification: str = "INTERNAL",
        model_hint: Optional[str] = None,
        provider_hint: Optional[str] = None,
        region_hint: Optional[str] = None,
        budget: Optional[float] = None,
        policy_context: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"data_classification": data_classification}
        if purpose is not None:
            payload["purpose"] = purpose
        if model_hint is not None:
            payload["model_hint"] = model_hint
        if provider_hint is not None:
            payload["provider_hint"] = provider_hint
        if region_hint is not None:
            payload["region_hint"] = region_hint
        if budget is not None:
            payload["budget"] = budget
        if policy_context is not None:
            payload["policy_context"] = policy_context
        return await self.post(self._build_url("/ai/gateway/route"), data=payload)

    async def gateway_invoke(
        self,
        model_id: str,
        prompt: str,
        data_classification: str = "INTERNAL",
        purpose: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"model_id": model_id, "prompt": prompt, "data_classification": data_classification}
        if purpose is not None:
            payload["purpose"] = purpose
        return await self.post(self._build_url("/ai/gateway/invoke"), data=payload)

    async def route(self, *args, **kwargs) -> dict:
        return await self.gateway_route(*args, **kwargs)

    async def invoke(self, *args, **kwargs) -> dict:
        return await self.gateway_invoke(*args, **kwargs)

    # ─── Monitoring ───────────────────────────────────────────────────────

    async def record_snapshot(
        self,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        availability: Optional[str] = None,
        latency_ms: Optional[float] = None,
        error_rate: Optional[float] = None,
        token_usage: Optional[int] = None,
        cost: Optional[float] = None,
        quality: Optional[float] = None,
        safety: Optional[float] = None,
        drift: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if model_id is not None:
            payload["model_id"] = model_id
        if provider is not None:
            payload["provider"] = provider
        if availability is not None:
            payload["availability"] = availability
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if error_rate is not None:
            payload["error_rate"] = error_rate
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if cost is not None:
            payload["cost"] = cost
        if quality is not None:
            payload["quality"] = quality
        if safety is not None:
            payload["safety"] = safety
        if drift is not None:
            payload["drift"] = drift
        return await self.post(self._build_url("/ai/monitoring/snapshots"), data=payload)

    async def get_snapshots(self, model_id: str, limit: int = 100) -> list[dict]:
        return await self.get(self._build_url(f"/ai/monitoring/{model_id}"), params={"limit": limit})

    async def detect_drift(
        self,
        model_id: Optional[str] = None,
        window: int = 100,
    ) -> dict:
        payload: dict[str, Any] = {"window": window}
        if model_id is not None:
            payload["model_id"] = model_id
        return await self.post(self._build_url("/ai/monitoring/drift"), data=payload)

    # ─── Provenance ───────────────────────────────────────────────────────

    async def record_provenance(
        self,
        model_id: str,
        provider: Optional[str] = None,
        artifact: Optional[str] = None,
        source: Optional[str] = None,
        training_metadata: Optional[dict] = None,
        evaluation_version: Optional[str] = None,
        deployment_version: Optional[str] = None,
        policy_version: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {"model_id": model_id}
        if provider is not None:
            payload["provider"] = provider
        if artifact is not None:
            payload["artifact"] = artifact
        if source is not None:
            payload["source"] = source
        if training_metadata is not None:
            payload["training_metadata"] = training_metadata
        if evaluation_version is not None:
            payload["evaluation_version"] = evaluation_version
        if deployment_version is not None:
            payload["deployment_version"] = deployment_version
        if policy_version is not None:
            payload["policy_version"] = policy_version
        return await self.post(self._build_url(f"/ai/provenance/{model_id}"), data=payload)

    async def get_provenance(self, model_id: str) -> dict:
        return await self.get(self._build_url(f"/ai/provenance/{model_id}"))

    async def record(self, model_id: str, **kwargs) -> dict:
        return await self.record_provenance(model_id, **kwargs)
