from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class ContentType(str, Enum):
    NATURAL_LANGUAGE = "natural_language"
    SMT_CODE = "smt_code"
    AUTO = "auto"


class TransformRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Raw user input.")
    content_type: ContentType = Field(
        default=ContentType.AUTO,
        description="Input category. Use auto to enable heuristic detection.",
    )
    trace_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Optional request id for tracing.",
    )

    @validator("content")
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content cannot be empty.")
        return normalized


class ValidationSummary(BaseModel):
    passed: bool = False
    syntax_valid: Optional[bool] = None
    solver_available: bool = False
    solver_ran: bool = False
    solver_backend: Optional[str] = None
    solver_status: Optional[str] = None
    solver_time_ms: Optional[float] = None
    solvable: Optional[bool] = None
    matches_reference_status: Optional[bool] = None
    error_message: Optional[str] = None


class EquivalenceSummary(BaseModel):
    checked: bool = False
    available: bool = False
    backend: Optional[str] = None
    equivalent: Optional[bool] = None
    structurally_identical: Optional[bool] = None
    reference_assertion_count: Optional[int] = None
    candidate_assertion_count: Optional[int] = None
    divergence_kind: Optional[str] = None
    reference_holds_under_counterexample: Optional[bool] = None
    candidate_holds_under_counterexample: Optional[bool] = None
    counterexample_model: Optional[Dict[str, str]] = None
    error_message: Optional[str] = None


class AgentTrace(BaseModel):
    verifier_report: Optional[str] = None
    reflection_report: Optional[str] = None


class OptimizationSummary(BaseModel):
    strategy: str = "mcts_corf"
    baseline_status: Optional[str] = None
    search_used: bool = False
    iterations: int = 0
    explored_states: int = 0
    safe_deletions: int = 0
    explicit_reductions: int = 0
    best_reward: Optional[float] = None
    compactness_score: Optional[float] = None
    semantic_score: Optional[float] = None
    solver_score: Optional[float] = None
    used_llm_postpass: bool = False
    termination_reason: Optional[str] = None
    best_depth: int = 0
    stagnation_rounds: int = 0
    unsat_core_available: Optional[bool] = None
    reference_unsat_core_size: Optional[int] = None
    final_unsat_core_size: Optional[int] = None
    unsat_core_sample_count: int = 0
    unsat_core_distinct_count: int = 0
    stable_unsat_core_size: Optional[int] = None
    union_unsat_core_size: Optional[int] = None
    core_guided_actions: int = 0
    protected_core_skips: int = 0
    core_release_rounds: int = 0
    core_projection_applied: bool = False
    core_projection_reductions: int = 0
    notes: List[str] = Field(default_factory=list)


class WorkflowSummary(BaseModel):
    output_attempts: int = 1
    max_attempts: int = 1
    output_repaired: bool = False
    source_attempts: int = 0
    source_repaired: bool = False
    verifier_runs: int = 0
    reflection_runs: int = 0
    repair_runs: int = 0


class TransformResponse(BaseModel):
    success: bool = True
    request_type: ContentType
    result: str
    provider: str
    message: str = "Request processed successfully."
    trace_id: str
    validation: ValidationSummary
    workflow: WorkflowSummary
    source_validation: Optional[ValidationSummary] = None
    equivalence: Optional[EquivalenceSummary] = None
    agent_trace: Optional[AgentTrace] = None
    optimization_summary: Optional[OptimizationSummary] = None
