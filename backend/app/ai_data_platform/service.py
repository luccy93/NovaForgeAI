"""10x Enhanced service layer for Volume 29 — AI & Data Platform."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import model_registry, ai_pipeline_orchestrator, data_pipeline_engine
from . import feature_store, embedding_service, mlflow_integration, prompt_engine
from . import ai_guardrails, model_serving, training_platform, data_labeling
from . import vector_database, experiment_tracking, model_monitoring
from . import ai_integration_hub, enterprise_ai, data_governance, ai_security, observability

logger = logging.getLogger(__name__)


class AIDataService(AsyncService):
    def __init__(self):
        super().__init__("ai_data_platform", JsonFileStorage("data/ai_data/service.json"))
        self.registry = model_registry.ModelRegistry("data/ai_data/models")
        self.pipeline = ai_pipeline_orchestrator.AIPipelineOrchestrator("data/ai_data/pipelines")
        self.data = data_pipeline_engine.DataPipelineEngine("data/ai_data/data_pipelines")
        self.features = feature_store.FeatureStore("data/ai_data/features")
        self.embeddings = embedding_service.EmbeddingService("data/ai_data/embeddings")
        self.mlflow = mlflow_integration.MLflowIntegration("data/ai_data/mlflow")
        self.prompt = prompt_engine.PromptEngine("data/ai_data/prompts")
        self.guardrails = ai_guardrails.AIGuardrails("data/ai_data/guardrails")
        self.serving = model_serving.ModelServing("data/ai_data/serving")
        self.training = training_platform.TrainingPlatform("data/ai_data/training")
        self.labeling = data_labeling.DataLabeling("data/ai_data/labeling")
        self.vector = vector_database.VectorDatabase("data/ai_data/vectors")
        self.experiments = experiment_tracking.ExperimentTracking("data/ai_data/experiments")
        self.monitoring = model_monitoring.ModelMonitoring("data/ai_data/monitoring")
        self.hub = ai_integration_hub.AIIntegrationHub("data/ai_data/hub")
        self.ent_ai = enterprise_ai.EnterpriseAI("data/ai_data/enterprise")
        self.governance = data_governance.DataGovernance("data/ai_data/governance")
        self.ai_sec = ai_security.AISecurity("data/ai_data/security")
        self.obs = observability.AIDataObservability("data/ai_data/observability")

    async def run_pipeline(self, org_id: str, pipeline_id: str, params: dict = None):
        result = self.pipeline.run(pipeline_id, params or {})
        self.telemetry.increment("pipelines_run")
        return result

    async def register_model(self, org_id: str, name: str, version: str, uri: str, framework: str = ""):
        model = self.registry.register(name, version, uri, framework)
        self.telemetry.increment("models_registered")
        return model

    async def query_embeddings(self, org_id: str, collection: str, query: str, top_k: int = 5):
        results = self.embeddings.search(collection, query, top_k)
        self.telemetry.increment("embedding_queries")
        return results

    async def health_check(self) -> dict:
        return self.health()


svc = AIDataService()
registry.register(svc)
