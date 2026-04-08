import asyncio
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.core.config import Settings
from app.models.schemas import (
    AgentTrace,
    ContentType,
    EquivalenceSummary,
    OptimizationSummary,
    ValidationSummary,
    WorkflowSummary,
)
from app.services.equivalence import SMTEquivalenceChecker
from app.services.llm.base import LLMProvider
from app.services.redundancy_optimizer import MCTSCORFOptimizer
from app.services.solver_validation import Z3Validator


@dataclass
class CandidateState:
    candidate: str
    validation: ValidationSummary
    attempts: int
    repaired: bool
    equivalence: Optional[EquivalenceSummary] = None
    agent_trace: Optional[AgentTrace] = None
    verifier_runs: int = 0
    reflection_runs: int = 0
    repair_runs: int = 0


@dataclass
class WorkflowExecutionResult:
    success: bool
    result: str
    validation: ValidationSummary
    workflow: WorkflowSummary
    message: str
    source_validation: Optional[ValidationSummary] = None
    equivalence: Optional[EquivalenceSummary] = None
    agent_trace: Optional[AgentTrace] = None
    optimization_summary: Optional[OptimizationSummary] = None


class SMTWorkflowService:
    def __init__(self, settings: Settings, provider: LLMProvider) -> None:
        self._settings = settings
        self._provider = provider
        self._validator = Z3Validator(settings)
        self._equivalence_checker = SMTEquivalenceChecker()
        self._optimizer = MCTSCORFOptimizer(settings)

    async def generate_from_text(self, content: str) -> WorkflowExecutionResult:
        initial_candidate = await self._provider.natural_language_to_smt(content)
        output_state = await self._repair_loop(
            request_type=ContentType.NATURAL_LANGUAGE,
            source_input=content,
            initial_candidate=initial_candidate,
        )

        if not output_state.validation.solver_available:
            return self._build_environment_failure_result(
                candidate_state=output_state,
                source_attempts=0,
                source_repaired=False,
                source_validation=None,
                message=output_state.validation.error_message
                or "Z3 is unavailable so the workflow cannot validate SMT-LIB output.",
            )

        success = output_state.validation.passed
        message = (
            "Generated SMT-LIB passed Z3 validation."
            if success
            else self._build_failed_message(
                prefix="Generated SMT-LIB did not pass validation",
                attempts=output_state.attempts,
                validation=output_state.validation,
                equivalence=None,
            )
        )

        return WorkflowExecutionResult(
            success=success,
            result=output_state.candidate,
            validation=output_state.validation,
            workflow=WorkflowSummary(
                output_attempts=output_state.attempts,
                max_attempts=self._settings.workflow_max_attempts,
                output_repaired=output_state.repaired,
                source_attempts=0,
                source_repaired=False,
                verifier_runs=output_state.verifier_runs,
                reflection_runs=output_state.reflection_runs,
                repair_runs=output_state.repair_runs,
            ),
            message=message,
            equivalence=None,
            agent_trace=output_state.agent_trace,
            optimization_summary=None,
        )

    async def optimize_smt(self, content: str) -> WorkflowExecutionResult:
        source_state = await self._repair_loop(
            request_type=ContentType.SMT_CODE,
            source_input=content,
            initial_candidate=content,
        )

        if not source_state.validation.solver_available:
            return self._build_environment_failure_result(
                candidate_state=source_state,
                source_attempts=source_state.attempts,
                source_repaired=source_state.repaired,
                source_validation=source_state.validation,
                message=source_state.validation.error_message
                or "Z3 is unavailable so the workflow cannot validate input SMT-LIB.",
            )

        if not source_state.validation.passed:
            return WorkflowExecutionResult(
                success=False,
                result=source_state.candidate,
                validation=source_state.validation,
                workflow=WorkflowSummary(
                    output_attempts=0,
                    max_attempts=self._settings.workflow_max_attempts,
                    output_repaired=False,
                    source_attempts=source_state.attempts,
                    source_repaired=source_state.repaired,
                    verifier_runs=source_state.verifier_runs,
                    reflection_runs=source_state.reflection_runs,
                    repair_runs=source_state.repair_runs,
                ),
                message=self._build_failed_message(
                    prefix="Input SMT-LIB could not be repaired into a valid solver-ready script",
                    attempts=source_state.attempts,
                    validation=source_state.validation,
                    equivalence=None,
                ),
                source_validation=source_state.validation,
                equivalence=None,
                agent_trace=source_state.agent_trace,
                optimization_summary=None,
            )

        optimization_run = await self._run_blocking(
            self._optimizer.optimize,
            source_state.candidate,
            source_state.validation,
        )
        optimized_candidate = optimization_run.candidate

        if self._settings.optimizer_enable_llm_postpass:
            optimized_candidate = await self._provider.optimize_smt(
                optimized_candidate,
                optimization_run.llm_context,
            )

        baseline_status = (source_state.validation.solver_status or "").lower()
        reference_smt = source_state.candidate if baseline_status == "sat" else None

        output_state = await self._repair_loop(
            request_type=ContentType.SMT_CODE,
            source_input=source_state.candidate,
            initial_candidate=optimized_candidate,
            reference_smt=reference_smt,
            reference_validation=source_state.validation,
        )

        if not output_state.validation.solver_available:
            return self._build_environment_failure_result(
                candidate_state=output_state,
                source_attempts=source_state.attempts,
                source_repaired=source_state.repaired,
                source_validation=source_state.validation,
                message=output_state.validation.error_message
                or "Z3 is unavailable so the workflow cannot validate optimized SMT-LIB.",
                extra_runs=self._sum_runs(source_state, output_state),
                agent_trace=self._pick_agent_trace(source_state, output_state),
                optimization_summary=optimization_run.summary,
            )

        if output_state.equivalence and not output_state.equivalence.available:
            return self._build_environment_failure_result(
                candidate_state=output_state,
                source_attempts=source_state.attempts,
                source_repaired=source_state.repaired,
                source_validation=source_state.validation,
                message=output_state.equivalence.error_message
                or "Semantic equivalence checking is unavailable.",
                extra_runs=self._sum_runs(source_state, output_state),
                agent_trace=self._pick_agent_trace(source_state, output_state),
                optimization_summary=optimization_run.summary,
            )

        success = self._is_candidate_accepted(output_state.validation, output_state.equivalence)
        message = self._build_optimization_message(
            baseline_status,
            success,
            output_state,
        )

        verifier_runs, reflection_runs, repair_runs = self._sum_runs(source_state, output_state)

        return WorkflowExecutionResult(
            success=success,
            result=output_state.candidate,
            validation=output_state.validation,
            workflow=WorkflowSummary(
                output_attempts=output_state.attempts,
                max_attempts=self._settings.workflow_max_attempts,
                output_repaired=output_state.repaired,
                source_attempts=source_state.attempts,
                source_repaired=source_state.repaired,
                verifier_runs=verifier_runs,
                reflection_runs=reflection_runs,
                repair_runs=repair_runs,
            ),
            message=message,
            source_validation=source_state.validation,
            equivalence=output_state.equivalence,
            agent_trace=self._pick_agent_trace(source_state, output_state),
            optimization_summary=optimization_run.summary,
        )

    async def _repair_loop(
        self,
        request_type: ContentType,
        source_input: str,
        initial_candidate: str,
        reference_smt: Optional[str] = None,
        reference_validation: Optional[ValidationSummary] = None,
    ) -> CandidateState:
        candidate = initial_candidate.strip()
        attempts = 1
        validation = await self._validate_candidate(candidate)
        validation = self._decorate_validation(validation, reference_validation)
        equivalence = await self._maybe_check_equivalence(
            reference_smt,
            reference_validation,
            validation,
            candidate,
        )

        agent_trace = None  # type: Optional[AgentTrace]
        verifier_runs = 0
        reflection_runs = 0
        repair_runs = 0

        while attempts < self._settings.workflow_max_attempts:
            if not self._needs_repair(validation, equivalence):
                break

            if reference_smt and equivalence and not equivalence.available:
                break

            raw_feedback = self._build_validator_feedback(
                validation,
                reference_validation,
                equivalence,
            )
            verifier_report = await self._provider.diagnose_smt_issue(
                request_type,
                source_input,
                candidate,
                raw_feedback,
                reference_smt,
            )
            verifier_runs += 1

            reflection_report = await self._provider.reflect_on_smt_issue(
                request_type,
                source_input,
                candidate,
                raw_feedback,
                verifier_report,
                reference_smt,
            )
            reflection_runs += 1

            agent_trace = AgentTrace(
                verifier_report=verifier_report,
                reflection_report=reflection_report,
            )

            repair_feedback = self._build_repair_feedback(
                validation,
                reference_validation,
                equivalence,
                verifier_report,
                reflection_report,
            )
            candidate = await self._provider.repair_smt(
                request_type,
                source_input,
                candidate,
                repair_feedback,
                reference_smt,
            )
            repair_runs += 1

            attempts += 1
            validation = await self._validate_candidate(candidate)
            validation = self._decorate_validation(validation, reference_validation)
            equivalence = await self._maybe_check_equivalence(
                reference_smt,
                reference_validation,
                validation,
                candidate,
            )

        return CandidateState(
            candidate=candidate,
            validation=validation,
            attempts=attempts,
            repaired=attempts > 1,
            equivalence=equivalence,
            agent_trace=agent_trace,
            verifier_runs=verifier_runs,
            reflection_runs=reflection_runs,
            repair_runs=repair_runs,
        )

    async def _validate_candidate(self, candidate: str) -> ValidationSummary:
        return await self._run_blocking(self._validator.validate, candidate)

    async def _maybe_check_equivalence(
        self,
        reference_smt: Optional[str],
        reference_validation: Optional[ValidationSummary],
        validation: ValidationSummary,
        candidate: str,
    ) -> Optional[EquivalenceSummary]:
        if not reference_smt:
            return None
        if not reference_validation:
            return None
        if (reference_validation.solver_status or "").lower() != "sat":
            return None
        if not validation.passed:
            return None
        return await self._run_blocking(
            self._equivalence_checker.check,
            reference_smt,
            candidate,
        )

    async def _run_blocking(self, func: Callable, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args)

    def _is_candidate_accepted(
        self,
        validation: ValidationSummary,
        equivalence: Optional[EquivalenceSummary],
    ) -> bool:
        if not validation.passed:
            return False
        if equivalence is None:
            return True
        if not equivalence.available:
            return False
        return equivalence.equivalent is True

    def _needs_repair(
        self,
        validation: ValidationSummary,
        equivalence: Optional[EquivalenceSummary],
    ) -> bool:
        if not validation.solver_available:
            return False
        if not validation.passed:
            return True
        if equivalence is None:
            return False
        if not equivalence.available:
            return False
        return equivalence.equivalent is not True

    def _decorate_validation(
        self,
        validation: ValidationSummary,
        reference_validation: Optional[ValidationSummary],
    ) -> ValidationSummary:
        if not reference_validation:
            return validation

        if not reference_validation.solver_status or not validation.solver_status:
            return validation

        same_status = reference_validation.solver_status == validation.solver_status
        validation.matches_reference_status = same_status

        if not same_status:
            validation.passed = False
            mismatch_message = (
                "Reference solver status is "
                "`{}` but current solver status is `{}`.".format(
                    reference_validation.solver_status,
                    validation.solver_status,
                )
            )
            if validation.error_message:
                validation.error_message = "{} {}".format(validation.error_message, mismatch_message)
            else:
                validation.error_message = mismatch_message

        return validation

    def _build_validator_feedback(
        self,
        validation: ValidationSummary,
        reference_validation: Optional[ValidationSummary],
        equivalence: Optional[EquivalenceSummary],
    ) -> str:
        feedback_parts = []  # type: List[str]

        if validation.syntax_valid is False and validation.error_message:
            feedback_parts.append("Syntax or parser issue: {}".format(validation.error_message))
        elif validation.error_message:
            feedback_parts.append(validation.error_message)

        if validation.solver_status:
            feedback_parts.append("Current solver status: {}.".format(validation.solver_status))

        if reference_validation and reference_validation.solver_status:
            feedback_parts.append(
                "Reference solver status that must be preserved: {}.".format(
                    reference_validation.solver_status
                )
            )
            if reference_validation.solver_status == "unsat":
                feedback_parts.append(
                    "Required preservation objective: keep the script unsat while making it smaller."
                )
            elif reference_validation.solver_status == "sat":
                feedback_parts.append(
                    "Required preservation objective: keep the optimized script logically equivalent to the reference script."
                )

        if equivalence is not None:
            if equivalence.equivalent is False and equivalence.error_message:
                feedback_parts.append("Equivalence failure: {}".format(equivalence.error_message))
            elif equivalence.equivalent is None and equivalence.error_message:
                feedback_parts.append("Equivalence check issue: {}".format(equivalence.error_message))
            feedback_parts.extend(self._build_counterexample_feedback(equivalence))

        return "\n".join(feedback_parts)

    def _build_repair_feedback(
        self,
        validation: ValidationSummary,
        reference_validation: Optional[ValidationSummary],
        equivalence: Optional[EquivalenceSummary],
        verifier_report: str,
        reflection_report: str,
    ) -> str:
        feedback_parts = []  # type: List[str]
        validator_feedback = self._build_validator_feedback(
            validation,
            reference_validation,
            equivalence,
        )
        if validator_feedback:
            feedback_parts.append("Validator feedback:")
            feedback_parts.append(validator_feedback)

        feedback_parts.append("Verifier agent report:")
        feedback_parts.append(verifier_report)
        feedback_parts.append("Reflection agent report:")
        feedback_parts.append(reflection_report)
        feedback_parts.append(
            "Apply only the smallest local edit needed to satisfy the required preservation objective."
        )
        feedback_parts.append("Return only corrected SMT-LIB code.")
        return "\n".join(feedback_parts)

    def _build_counterexample_feedback(
        self,
        equivalence: EquivalenceSummary,
    ) -> List[str]:
        feedback_parts = []  # type: List[str]

        if equivalence.divergence_kind == "candidate_stronger_than_reference":
            feedback_parts.append(
                "Counterexample interpretation: the candidate rejects a model that the reference allows, so the candidate is too strong."
            )
        elif equivalence.divergence_kind == "candidate_weaker_than_reference":
            feedback_parts.append(
                "Counterexample interpretation: the candidate allows a model that the reference rejects, so the candidate is too weak."
            )

        if equivalence.reference_holds_under_counterexample is not None:
            feedback_parts.append(
                "Reference formula under counterexample: {}.".format(
                    _bool_to_text(equivalence.reference_holds_under_counterexample)
                )
            )

        if equivalence.candidate_holds_under_counterexample is not None:
            feedback_parts.append(
                "Candidate formula under counterexample: {}.".format(
                    _bool_to_text(equivalence.candidate_holds_under_counterexample)
                )
            )

        if equivalence.counterexample_model is not None:
            if equivalence.counterexample_model:
                feedback_parts.append("Counterexample assignments from Z3:")
                for name in sorted(equivalence.counterexample_model):
                    feedback_parts.append(
                        "- {} = {}".format(name, equivalence.counterexample_model[name])
                    )
            else:
                feedback_parts.append("Counterexample assignments from Z3: <empty model>.")

        return feedback_parts

    def _build_environment_failure_result(
        self,
        candidate_state: CandidateState,
        source_attempts: int,
        source_repaired: bool,
        source_validation: Optional[ValidationSummary],
        message: str,
        extra_runs: Optional[Tuple[int, int, int]] = None,
        agent_trace: Optional[AgentTrace] = None,
        optimization_summary: Optional[OptimizationSummary] = None,
    ) -> WorkflowExecutionResult:
        if extra_runs is None:
            verifier_runs = candidate_state.verifier_runs
            reflection_runs = candidate_state.reflection_runs
            repair_runs = candidate_state.repair_runs
        else:
            verifier_runs, reflection_runs, repair_runs = extra_runs

        return WorkflowExecutionResult(
            success=False,
            result=candidate_state.candidate,
            validation=candidate_state.validation,
            workflow=WorkflowSummary(
                output_attempts=candidate_state.attempts,
                max_attempts=self._settings.workflow_max_attempts,
                output_repaired=candidate_state.repaired,
                source_attempts=source_attempts,
                source_repaired=source_repaired,
                verifier_runs=verifier_runs,
                reflection_runs=reflection_runs,
                repair_runs=repair_runs,
            ),
            message=message,
            source_validation=source_validation,
            equivalence=candidate_state.equivalence,
            agent_trace=agent_trace or candidate_state.agent_trace,
            optimization_summary=optimization_summary,
        )

    def _build_failed_message(
        self,
        prefix: str,
        attempts: int,
        validation: ValidationSummary,
        equivalence: Optional[EquivalenceSummary],
    ) -> str:
        suffix_parts = []  # type: List[str]
        if validation.error_message:
            suffix_parts.append(validation.error_message)
        if equivalence and equivalence.error_message:
            suffix_parts.append(equivalence.error_message)
        suffix = " ".join(suffix_parts) or "No additional validation details were reported."
        return "{} after {} attempt(s). {}".format(prefix, attempts, suffix)

    def _build_optimization_message(
        self,
        baseline_status: str,
        success: bool,
        output_state: CandidateState,
    ) -> str:
        if success:
            if baseline_status == "sat":
                return (
                    "Optimized SMT-LIB passed Z3 validation and preserved SAT semantics through equivalence checking."
                )
            if baseline_status == "unsat":
                return (
                    "Optimized SMT-LIB passed Z3 validation and preserved the UNSAT solver status while reducing redundancy."
                )
            return "Optimized SMT-LIB passed validation."

        if baseline_status == "sat":
            return self._build_failed_message(
                prefix="Optimized SMT-LIB did not preserve SAT-equivalence or validation requirements",
                attempts=output_state.attempts,
                validation=output_state.validation,
                equivalence=output_state.equivalence,
            )
        if baseline_status == "unsat":
            return self._build_failed_message(
                prefix="Optimized SMT-LIB did not preserve the required UNSAT status or validation requirements",
                attempts=output_state.attempts,
                validation=output_state.validation,
                equivalence=None,
            )
        return self._build_failed_message(
            prefix="Optimized SMT-LIB did not pass validation",
            attempts=output_state.attempts,
            validation=output_state.validation,
            equivalence=output_state.equivalence,
        )

    def _sum_runs(
        self,
        source_state: CandidateState,
        output_state: CandidateState,
    ) -> Tuple[int, int, int]:
        return (
            source_state.verifier_runs + output_state.verifier_runs,
            source_state.reflection_runs + output_state.reflection_runs,
            source_state.repair_runs + output_state.repair_runs,
        )

    def _pick_agent_trace(
        self,
        source_state: CandidateState,
        output_state: CandidateState,
    ) -> Optional[AgentTrace]:
        if output_state.agent_trace is not None:
            return output_state.agent_trace
        return source_state.agent_trace


def _bool_to_text(value: bool) -> str:
    return "true" if value else "false"
