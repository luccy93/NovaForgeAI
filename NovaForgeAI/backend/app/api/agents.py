from typing import Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()

try:
    from agents import AgentOrchestrator
except ImportError:
    AgentOrchestrator = None  # type: ignore


class AgentInfo(BaseModel):
    name: str
    description: str
    capabilities: list[str]


class AgentRunRequest(BaseModel):
    input: str
    config: Optional[dict[str, Any]] = None


class AgentRunResponse(BaseModel):
    agent: str
    output: str
    status: str


class PipelineRequest(BaseModel):
    agents: list[str]
    input: str


class PipelineResponse(BaseModel):
    results: list[AgentRunResponse]
    final_output: str


class ParallelRequest(BaseModel):
    agents: list[str]
    input: str


class ParallelResponse(BaseModel):
    results: list[AgentRunResponse]


_AVAILABLE_AGENTS: list[AgentInfo] = [
    AgentInfo(
        name="code_reviewer",
        description="Reviews code and suggests improvements",
        capabilities=["linting", "style", "best practices"],
    ),
    AgentInfo(
        name="documenter",
        description="Generates documentation from source code",
        capabilities=["docstrings", "readme", "api docs"],
    ),
    AgentInfo(
        name="tester",
        description="Writes unit tests for code",
        capabilities=["unit tests", "test generation"],
    ),
    AgentInfo(
        name="explainer",
        description="Explains code in natural language",
        capabilities=["code explanation", "summarization"],
    ),
    AgentInfo(
        name="refactorer",
        description="Suggests refactoring opportunities",
        capabilities=["refactoring", "code smell detection"],
    ),
]


def _get_orchestrator() -> Any:
    if AgentOrchestrator is None:
        raise HTTPException(
            status_code=501,
            detail="AgentOrchestrator not available. Install the 'agents' package.",
        )
    return AgentOrchestrator()


@router.get("", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    return _AVAILABLE_AGENTS


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_name: str,
    request: AgentRunRequest,
) -> AgentRunResponse:
    agent_names = {a.name for a in _AVAILABLE_AGENTS}
    if agent_name not in agent_names:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available: {sorted(agent_names)}",
        )

    orchestrator = _get_orchestrator()
    try:
        output = orchestrator.run_single(agent_name, request.input, request.config or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    return AgentRunResponse(agent=agent_name, output=str(output), status="completed")


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(
    request: PipelineRequest,
) -> PipelineResponse:
    agent_names = {a.name for a in _AVAILABLE_AGENTS}
    for name in request.agents:
        if name not in agent_names:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{name}' not found. Available: {sorted(agent_names)}",
            )

    orchestrator = _get_orchestrator()
    results: list[AgentRunResponse] = []
    current_input = request.input

    try:
        for agent_name in request.agents:
            output = orchestrator.run_single(agent_name, current_input)
            results.append(
                AgentRunResponse(agent=agent_name, output=str(output), status="completed")
            )
            current_input = str(output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed at '{agent_name}': {e}")

    return PipelineResponse(results=results, final_output=current_input)


@router.post("/parallel", response_model=ParallelResponse)
async def run_agents_parallel(
    request: ParallelRequest,
) -> ParallelResponse:
    agent_names = {a.name for a in _AVAILABLE_AGENTS}
    for name in request.agents:
        if name not in agent_names:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{name}' not found. Available: {sorted(agent_names)}",
            )

    orchestrator = _get_orchestrator()
    results: list[AgentRunResponse] = []

    try:
        outputs = orchestrator.run_parallel(request.agents, request.input)
        for agent_name, output in zip(request.agents, outputs):
            results.append(
                AgentRunResponse(agent=agent_name, output=str(output), status="completed")
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parallel execution failed: {e}")

    return ParallelResponse(results=results)
