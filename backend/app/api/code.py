from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.code_analysis import CodeAnalysisService

router = APIRouter()


class AnalyzeRequest(BaseModel):
    content: str
    language: str


class AnalyzeResponse(BaseModel):
    language: str
    size_bytes: int
    line_count: int
    functions: list[dict]
    classes: list[dict]
    complexity: int
    dependencies: list[str]
    has_syntax_tree: bool


class FunctionsRequest(BaseModel):
    content: str
    language: str


class FunctionsResponse(BaseModel):
    functions: list[dict]


class ComplexityRequest(BaseModel):
    content: str
    language: str


class ComplexityResponse(BaseModel):
    cyclomatic_complexity: int
    language: str


class DependenciesRequest(BaseModel):
    content: str
    language: str


class DependenciesResponse(BaseModel):
    dependencies: list[str]
    language: str


_SUPPORTED_LANGUAGES = {"python", "typescript", "javascript", "go", "rust", "java"}


def _validate_language(language: str) -> None:
    if language.lower() not in _SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{language}'. Supported: {sorted(_SUPPORTED_LANGUAGES)}",
        )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_code(request: AnalyzeRequest) -> AnalyzeResponse:
    _validate_language(request.language)
    service = CodeAnalysisService()
    result = service.analyze_file(request.content, request.language)
    return AnalyzeResponse(**result)


@router.post("/functions", response_model=FunctionsResponse)
async def extract_functions(request: FunctionsRequest) -> FunctionsResponse:
    _validate_language(request.language)
    service = CodeAnalysisService()
    functions = service.extract_functions(request.content, request.language)
    return FunctionsResponse(functions=functions)


@router.post("/complexity", response_model=ComplexityResponse)
async def compute_complexity(request: ComplexityRequest) -> ComplexityResponse:
    _validate_language(request.language)
    service = CodeAnalysisService()
    complexity = service.compute_complexity(request.content, request.language)
    return ComplexityResponse(cyclomatic_complexity=complexity, language=request.language)


@router.post("/dependencies", response_model=DependenciesResponse)
async def detect_dependencies(request: DependenciesRequest) -> DependenciesResponse:
    _validate_language(request.language)
    service = CodeAnalysisService()
    deps = service.detect_dependencies(request.content, request.language)
    return DependenciesResponse(dependencies=deps, language=request.language)
