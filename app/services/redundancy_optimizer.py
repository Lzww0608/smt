import math
import random
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from app.core.config import Settings
from app.models.schemas import OptimizationSummary, ValidationSummary
from app.services.solver_validation import Z3Validator


@dataclass
class ScriptMetrics:
    token_count: int
    assertion_count: int
    nesting_depth: int
    normalized_text: str


@dataclass
class UnsatCoreInfo:
    available: bool
    core_positions: Set[int] = field(default_factory=set)
    core_command_indices: Set[int] = field(default_factory=set)
    core_size: int = 0
    total_assertions: int = 0
    stable_positions: Set[int] = field(default_factory=set)
    stable_command_indices: Set[int] = field(default_factory=set)
    stable_core_size: int = 0
    union_positions: Set[int] = field(default_factory=set)
    union_command_indices: Set[int] = field(default_factory=set)
    union_core_size: int = 0
    sample_count: int = 0
    distinct_core_count: int = 0
    hit_counts: Dict[int, int] = field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def density(self) -> float:
        if self.total_assertions <= 0:
            return 1.0
        return float(self.core_size) / float(self.total_assertions)

    @property
    def stable_density(self) -> float:
        if self.total_assertions <= 0:
            return 1.0
        return float(self.stable_core_size) / float(self.total_assertions)

    @property
    def union_density(self) -> float:
        if self.total_assertions <= 0:
            return 1.0
        return float(self.union_core_size) / float(self.total_assertions)


@dataclass
class OptimizationState:
    script: str
    validation: ValidationSummary
    metrics: ScriptMetrics
    reward: float
    compactness_score: float
    semantic_score: float
    solver_score: float
    unsat_core_info: Optional[UnsatCoreInfo] = None


@dataclass
class SearchNode:
    state: OptimizationState
    depth: int
    parent: Optional["SearchNode"] = None
    children: List["SearchNode"] = field(default_factory=list)
    pending_children: Optional[List[OptimizationState]] = None
    visits: int = 0
    value_sum: float = 0.0


@dataclass
class SearchStatistics:
    iterations_run: int = 0
    explored_states: int = 1
    safe_deletions: int = 0
    explicit_reductions: int = 0
    best_depth: int = 0
    stagnation_rounds: int = 0
    core_guided_actions: int = 0
    protected_core_skips: int = 0
    core_release_rounds: int = 0
    core_projection_applied: bool = False
    core_projection_reductions: int = 0
    termination_reason: str = "max_iterations_reached"
    unsat_core_available: Optional[bool] = None
    reference_unsat_core_size: Optional[int] = None
    final_unsat_core_size: Optional[int] = None
    unsat_core_sample_count: int = 0
    unsat_core_distinct_count: int = 0
    stable_unsat_core_size: Optional[int] = None
    union_unsat_core_size: Optional[int] = None


@dataclass
class OptimizationRunResult:
    candidate: str
    summary: OptimizationSummary
    llm_context: str


@dataclass
class ParsedScript:
    commands: List[str]
    assertion_indices: List[int]
    check_sat_indices: List[int]

    @classmethod
    def parse(cls, smt_code: str) -> "ParsedScript":
        commands = _split_top_level_commands(smt_code)
        assertion_indices = []  # type: List[int]
        check_sat_indices = []  # type: List[int]

        for index, command in enumerate(commands):
            normalized = _normalize_command(command)
            if normalized.startswith("(assert ") or normalized == "(assert)":
                assertion_indices.append(index)
            elif normalized == "(check-sat)":
                check_sat_indices.append(index)

        return cls(
            commands=commands,
            assertion_indices=assertion_indices,
            check_sat_indices=check_sat_indices,
        )

    def remove_command_indices(self, removed_indices: Set[int]) -> str:
        remaining = []  # type: List[str]
        for index, command in enumerate(self.commands):
            if index in removed_indices:
                continue
            remaining.append(command)
        return _join_commands(remaining)


class MCTSCORFOptimizer:
    COMPACTNESS_WEIGHTS = (0.35, 0.45, 0.20)
    REWARD_WEIGHTS = (0.20, 0.40, 0.40)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._validator = Z3Validator(settings)

    def optimize(
        self,
        source_script: str,
        reference_validation: ValidationSummary,
    ) -> OptimizationRunResult:
        baseline_status = (reference_validation.solver_status or "").lower()
        notes = []  # type: List[str]
        validation_cache = {}  # type: Dict[str, ValidationSummary]
        validation_cache[source_script] = reference_validation.copy(deep=True)

        if baseline_status not in {"sat", "unsat"}:
            notes.append(
                "The deterministic optimizer only runs when the reference solver status is sat or unsat."
            )
            summary = OptimizationSummary(
                baseline_status=reference_validation.solver_status,
                search_used=False,
                termination_reason="unsupported_reference_status",
                notes=notes,
            )
            return OptimizationRunResult(
                candidate=source_script,
                summary=summary,
                llm_context=self._build_llm_context(summary),
            )

        reference_metrics = self._collect_metrics(source_script)
        working_script, explicit_reductions, cleanup_notes = self._cleanup_explicit_redundancy(
            source_script,
            baseline_status,
            validation_cache,
        )
        notes.extend(cleanup_notes)

        working_validation = self._validate_cached(working_script, validation_cache)
        if not self._preserves_required_status(working_validation, baseline_status):
            working_script = source_script
            working_validation = reference_validation.copy(deep=True)
            explicit_reductions = 0
            notes.append(
                "Explicit cleanup was reverted because it changed solver behavior or produced invalid SMT-LIB."
            )

        unsat_core_cache = {}  # type: Dict[str, UnsatCoreInfo]
        root_state = self._evaluate_state(
            working_script,
            working_validation,
            baseline_status,
            reference_metrics,
            reference_validation,
            unsat_core_cache,
        )
        best_state = root_state

        search_stats = SearchStatistics(explicit_reductions=explicit_reductions)
        if baseline_status == "unsat":
            search_stats.unsat_core_available = (
                root_state.unsat_core_info.available if root_state.unsat_core_info else False
            )
            if root_state.unsat_core_info and root_state.unsat_core_info.available:
                search_stats.reference_unsat_core_size = root_state.unsat_core_info.core_size
                search_stats.final_unsat_core_size = root_state.unsat_core_info.core_size
                search_stats.unsat_core_sample_count = root_state.unsat_core_info.sample_count
                search_stats.unsat_core_distinct_count = root_state.unsat_core_info.distinct_core_count
                search_stats.stable_unsat_core_size = root_state.unsat_core_info.stable_core_size
                search_stats.union_unsat_core_size = root_state.unsat_core_info.union_core_size
                projected_root_state, projection_rounds, projection_reductions = self._tighten_unsat_state_with_projection(
                    root_state,
                    reference_metrics,
                    reference_validation,
                    validation_cache,
                    unsat_core_cache,
                )
                if projection_rounds:
                    root_state = projected_root_state
                    best_state = projected_root_state
                    search_stats.core_projection_applied = True
                    search_stats.core_projection_reductions += projection_reductions
                    if projected_root_state.unsat_core_info is not None:
                        search_stats.final_unsat_core_size = projected_root_state.unsat_core_info.core_size
                        search_stats.unsat_core_sample_count = projected_root_state.unsat_core_info.sample_count
                        search_stats.unsat_core_distinct_count = projected_root_state.unsat_core_info.distinct_core_count
                        search_stats.stable_unsat_core_size = projected_root_state.unsat_core_info.stable_core_size
                        search_stats.union_unsat_core_size = projected_root_state.unsat_core_info.union_core_size
                    notes.append(
                        "Applied {} UNSAT core projection round(s) before search, releasing {} non-core assertion(s).".format(
                            projection_rounds,
                            projection_reductions,
                        )
                    )
            elif root_state.unsat_core_info and root_state.unsat_core_info.error_message:
                notes.append(root_state.unsat_core_info.error_message)

        if not _python_z3_available():
            notes.append(
                "Python package `z3-solver` is unavailable, so only explicit reductions were applied."
            )
            summary = self._build_summary(
                baseline_status=baseline_status,
                search_used=False,
                state=best_state,
                search_stats=search_stats,
                used_llm_postpass=False,
                notes=notes,
            )
            return OptimizationRunResult(
                candidate=best_state.script,
                summary=summary,
                llm_context=self._build_llm_context(summary),
            )

        root = SearchNode(state=root_state, depth=0)
        seen_scripts = set([root_state.script])  # type: Set[str]
        started_at = time.perf_counter()

        while search_stats.iterations_run < self._settings.optimizer_max_iterations:
            if self._should_stop_for_time_budget(started_at):
                search_stats.termination_reason = "time_budget_reached"
                break

            if not self._has_expandable_frontier(root):
                search_stats.termination_reason = "frontier_exhausted"
                break

            search_stats.iterations_run += 1
            selected = self._select_node(
                root,
                baseline_status,
                reference_metrics,
                reference_validation,
                validation_cache,
                unsat_core_cache,
                seen_scripts,
                search_stats,
            )
            expanded, generated_count = self._expand_node(
                selected,
                baseline_status,
                reference_metrics,
                reference_validation,
                validation_cache,
                unsat_core_cache,
                seen_scripts,
                search_stats,
            )
            search_stats.safe_deletions += generated_count

            target = expanded or selected
            if expanded is not None:
                search_stats.explored_states += 1

            self._backpropagate(target, target.state.reward)
            if self._accept_as_new_best(target.state, best_state):
                best_state = target.state
                search_stats.best_depth = target.depth
                search_stats.stagnation_rounds = 0
                if baseline_status == "unsat" and best_state.unsat_core_info is not None:
                    search_stats.final_unsat_core_size = best_state.unsat_core_info.core_size
                    search_stats.unsat_core_sample_count = best_state.unsat_core_info.sample_count
                    search_stats.unsat_core_distinct_count = best_state.unsat_core_info.distinct_core_count
                    search_stats.stable_unsat_core_size = best_state.unsat_core_info.stable_core_size
                    search_stats.union_unsat_core_size = best_state.unsat_core_info.union_core_size
            else:
                search_stats.stagnation_rounds += 1

            if best_state.metrics.assertion_count == 0:
                search_stats.termination_reason = "empty_assertion_set"
                break

            if search_stats.stagnation_rounds >= self._settings.optimizer_patience:
                search_stats.termination_reason = "stagnation_limit"
                break
        else:
            search_stats.termination_reason = "max_iterations_reached"

        if baseline_status == "unsat":
            tightened_state, projection_rounds, projection_reductions = self._tighten_unsat_state_with_projection(
                best_state,
                reference_metrics,
                reference_validation,
                validation_cache,
                unsat_core_cache,
            )
            if projection_rounds:
                best_state = tightened_state
                search_stats.core_projection_applied = True
                search_stats.core_projection_reductions += projection_reductions
                if tightened_state.unsat_core_info is not None:
                    search_stats.final_unsat_core_size = tightened_state.unsat_core_info.core_size
                    search_stats.unsat_core_sample_count = tightened_state.unsat_core_info.sample_count
                    search_stats.unsat_core_distinct_count = tightened_state.unsat_core_info.distinct_core_count
                    search_stats.stable_unsat_core_size = tightened_state.unsat_core_info.stable_core_size
                    search_stats.union_unsat_core_size = tightened_state.unsat_core_info.union_core_size
                notes.append(
                    "Applied {} UNSAT core projection round(s) after search, releasing {} additional non-core assertion(s).".format(
                        projection_rounds,
                        projection_reductions,
                    )
                )

        notes.append(self._describe_termination(search_stats.termination_reason))
        summary = self._build_summary(
            baseline_status=baseline_status,
            search_used=True,
            state=best_state,
            search_stats=search_stats,
            used_llm_postpass=self._settings.optimizer_enable_llm_postpass,
            notes=notes,
        )
        return OptimizationRunResult(
            candidate=best_state.script,
            summary=summary,
            llm_context=self._build_llm_context(summary),
        )

    def _cleanup_explicit_redundancy(
        self,
        source_script: str,
        baseline_status: str,
        validation_cache: Dict[str, ValidationSummary],
    ) -> Tuple[str, int, List[str]]:
        parsed = ParsedScript.parse(source_script)
        notes = []  # type: List[str]
        removed_indices = set()  # type: Set[int]
        duplicate_assertions = 0
        extra_check_sat = 0

        seen_assertions = set()  # type: Set[str]
        for assertion_index in parsed.assertion_indices:
            normalized = _normalize_command(parsed.commands[assertion_index])
            if normalized in seen_assertions:
                removed_indices.add(assertion_index)
                duplicate_assertions += 1
                continue
            seen_assertions.add(normalized)

        if len(parsed.check_sat_indices) > 1:
            for duplicate_index in parsed.check_sat_indices[:-1]:
                removed_indices.add(duplicate_index)
                extra_check_sat += 1

        candidate = parsed.remove_command_indices(removed_indices)
        tautology_count = 0

        if _python_z3_available():
            candidate, tautology_count = self._remove_tautological_assertions(candidate)

        if duplicate_assertions:
            notes.append(
                "Removed {} exact duplicate assertion(s) during explicit redundancy cleanup.".format(
                    duplicate_assertions
                )
            )
        if extra_check_sat:
            notes.append(
                "Removed {} extra `(check-sat)` command(s) to keep a single final solver command.".format(
                    extra_check_sat
                )
            )
        if tautology_count:
            notes.append(
                "Removed {} tautological assertion(s) detected by Z3.".format(tautology_count)
            )

        if not candidate.strip():
            candidate = source_script

        validation_cache.setdefault(candidate, self._validator.validate(candidate))
        if not self._preserves_required_status(validation_cache[candidate], baseline_status):
            return source_script, 0, []

        explicit_reductions = duplicate_assertions + extra_check_sat + tautology_count
        return candidate, explicit_reductions, notes

    def _remove_tautological_assertions(self, smt_code: str) -> Tuple[str, int]:
        try:
            import z3  # type: ignore
        except ImportError:
            return smt_code, 0

        parsed = ParsedScript.parse(smt_code)
        if not parsed.assertion_indices:
            return smt_code, 0

        try:
            solver = z3.Solver()
            solver.from_string(smt_code)
            assertions = list(solver.assertions())
        except z3.Z3Exception:
            return smt_code, 0

        removed_indices = set()  # type: Set[int]
        for assertion_position, expression in enumerate(assertions):
            if assertion_position >= len(parsed.assertion_indices):
                break
            tautology_solver = z3.Solver()
            tautology_solver.add(z3.Not(expression))
            if str(tautology_solver.check()) == "unsat":
                removed_indices.add(parsed.assertion_indices[assertion_position])

        if not removed_indices:
            return smt_code, 0

        return parsed.remove_command_indices(removed_indices), len(removed_indices)

    def _select_node(
        self,
        root: SearchNode,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
        seen_scripts: Set[str],
        search_stats: SearchStatistics,
    ) -> SearchNode:
        current = root
        while current.depth < self._settings.optimizer_max_depth:
            pending_children, _ = self._ensure_children_generated(
                current,
                baseline_status,
                reference_metrics,
                reference_validation,
                validation_cache,
                unsat_core_cache,
                seen_scripts,
                search_stats,
            )
            if pending_children:
                return current
            if not current.children:
                return current
            current = max(
                current.children,
                key=lambda child: self._ucb_score(current, child),
            )
        return current

    def _expand_node(
        self,
        node: SearchNode,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
        seen_scripts: Set[str],
        search_stats: SearchStatistics,
    ) -> Tuple[Optional[SearchNode], int]:
        pending_children, generated_count = self._ensure_children_generated(
            node,
            baseline_status,
            reference_metrics,
            reference_validation,
            validation_cache,
            unsat_core_cache,
            seen_scripts,
            search_stats,
        )
        if not pending_children:
            return None, generated_count

        child_state = pending_children.pop(0)
        child_node = SearchNode(
            state=child_state,
            depth=node.depth + 1,
            parent=node,
        )
        node.children.append(child_node)
        return child_node, generated_count

    def _ensure_children_generated(
        self,
        node: SearchNode,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
        seen_scripts: Set[str],
        search_stats: SearchStatistics,
    ) -> Tuple[List[OptimizationState], int]:
        if node.pending_children is not None:
            return node.pending_children, 0

        child_states = self._generate_child_states(
            node.state.script,
            baseline_status,
            reference_metrics,
            reference_validation,
            validation_cache,
            unsat_core_cache,
            seen_scripts,
            search_stats,
        )
        node.pending_children = child_states
        return node.pending_children, len(child_states)

    def _generate_child_states(
        self,
        current_script: str,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
        seen_scripts: Set[str],
        search_stats: SearchStatistics,
    ) -> List[OptimizationState]:
        parsed = ParsedScript.parse(current_script)
        if not parsed.assertion_indices:
            return []

        sat_context = self._load_sat_context(current_script) if baseline_status == "sat" else None
        unsat_core_info = None  # type: Optional[UnsatCoreInfo]
        ordered_positions = list(range(len(parsed.assertion_indices)))
        stable_positions_set = set()  # type: Set[int]
        union_positions_set = set()  # type: Set[int]

        if baseline_status == "unsat":
            unsat_core_info = self._get_unsat_core_info(current_script, unsat_core_cache)
            if (
                self._settings.optimizer_enable_unsat_core_guidance
                and unsat_core_info is not None
                and unsat_core_info.available
            ):
                stable_positions_set = set(unsat_core_info.stable_positions)
                union_positions_set = set(unsat_core_info.union_positions)
                outer_positions = [
                    position
                    for position in ordered_positions
                    if position not in union_positions_set
                ]
                soft_positions = [
                    position
                    for position in ordered_positions
                    if position in union_positions_set and position not in stable_positions_set
                ]
                stable_positions = [
                    position
                    for position in ordered_positions
                    if position in stable_positions_set
                ]

                if outer_positions:
                    ordered_positions = self._sort_unsat_positions_by_hit_count(
                        outer_positions,
                        unsat_core_info,
                        prefer_rare=True,
                    )
                    search_stats.protected_core_skips += len(soft_positions) + len(stable_positions)
                elif soft_positions:
                    ordered_positions = self._sort_unsat_positions_by_hit_count(
                        soft_positions,
                        unsat_core_info,
                        prefer_rare=True,
                    )
                    search_stats.protected_core_skips += len(stable_positions)
                    search_stats.core_release_rounds += 1
                else:
                    ordered_positions = self._sort_unsat_positions_by_hit_count(
                        stable_positions,
                        unsat_core_info,
                        prefer_rare=False,
                    )

        child_states = []  # type: List[OptimizationState]
        for assertion_position in ordered_positions:
            command_index = parsed.assertion_indices[assertion_position]
            candidate_script = parsed.remove_command_indices(set([command_index]))
            if not candidate_script.strip():
                continue
            if candidate_script in seen_scripts:
                continue

            if baseline_status == "sat":
                if sat_context is None or not self._is_sat_safe_deletion(
                    sat_context,
                    assertion_position,
                ):
                    continue

            candidate_validation = self._validate_cached(candidate_script, validation_cache)
            if not self._preserves_required_status(candidate_validation, baseline_status):
                continue

            child_state = self._evaluate_state(
                candidate_script,
                candidate_validation,
                baseline_status,
                reference_metrics,
                reference_validation,
                unsat_core_cache,
            )
            if (
                baseline_status == "unsat"
                and unsat_core_info is not None
                and unsat_core_info.available
                and assertion_position not in stable_positions_set
            ):
                search_stats.core_guided_actions += 1

            child_states.append(child_state)
            seen_scripts.add(candidate_script)

        child_states.sort(
            key=lambda state: (
                state.reward,
                state.compactness_score,
                -state.metrics.token_count,
            ),
            reverse=True,
        )
        return child_states[: self._settings.optimizer_max_children]

    def _load_sat_context(self, smt_code: str):
        try:
            import z3  # type: ignore
        except ImportError:
            return None

        try:
            solver = z3.Solver()
            solver.from_string(smt_code)
            assertions = list(solver.assertions())
        except z3.Z3Exception:
            return None

        return z3, assertions

    def _is_sat_safe_deletion(self, sat_context, removed_position: int) -> bool:
        z3, assertions = sat_context
        if removed_position >= len(assertions):
            return False

        implication_solver = z3.Solver()
        for index, assertion in enumerate(assertions):
            if index == removed_position:
                continue
            implication_solver.add(assertion)
        implication_solver.add(z3.Not(assertions[removed_position]))
        return str(implication_solver.check()) == "unsat"

    def _get_unsat_core_info(
        self,
        smt_code: str,
        cache: Dict[str, UnsatCoreInfo],
    ) -> UnsatCoreInfo:
        cached = cache.get(smt_code)
        if cached is not None:
            return cached

        parsed = ParsedScript.parse(smt_code)
        if not parsed.assertion_indices:
            info = UnsatCoreInfo(
                available=False,
                core_size=0,
                total_assertions=0,
                error_message="UNSAT core guidance is unavailable because the script has no assertions.",
            )
            cache[smt_code] = info
            return info

        try:
            import z3  # type: ignore
        except ImportError:
            info = UnsatCoreInfo(
                available=False,
                core_size=0,
                total_assertions=len(parsed.assertion_indices),
                error_message="Python package `z3-solver` is required for UNSAT core guidance.",
            )
            cache[smt_code] = info
            return info

        base_commands, named_assertions = self._build_unsat_core_program(parsed)
        sample_count_target = self._compute_unsat_core_sample_budget(len(parsed.assertion_indices))
        sampled_cores = []  # type: List[Set[int]]
        distinct_signatures = set()  # type: Set[Tuple[int, ...]]
        sample_timeout_ms = self._settings.optimizer_unsat_core_sample_timeout_ms

        for sample_index in range(sample_count_target):
            ordered_positions = self._build_unsat_core_sampling_order(
                len(parsed.assertion_indices),
                sample_index,
            )
            sample_positions = self._run_unsat_core_sample(
                z3,
                base_commands,
                named_assertions,
                ordered_positions,
                sample_index,
                sample_timeout_ms,
            )
            if sample_positions is None:
                continue

            sampled_cores.append(sample_positions)
            signature = tuple(sorted(sample_positions))
            distinct_signatures.add(signature)

            if sample_index >= 1 and len(distinct_signatures) == 1:
                break

        if not sampled_cores:
            info = UnsatCoreInfo(
                available=False,
                core_size=0,
                total_assertions=len(parsed.assertion_indices),
                error_message="Failed to compute UNSAT core guidance from sampled solver runs.",
            )
            cache[smt_code] = info
            return info

        representative_positions = min(
            sampled_cores,
            key=lambda core: (len(core), tuple(sorted(core))),
        )
        stable_positions = set(sampled_cores[0])
        union_positions = set(sampled_cores[0])
        hit_counts = {}  # type: Dict[int, int]

        for core_positions in sampled_cores:
            stable_positions &= core_positions
            union_positions |= core_positions
            for position in core_positions:
                hit_counts[position] = hit_counts.get(position, 0) + 1

        representative_command_indices = set(
            parsed.assertion_indices[position]
            for position in representative_positions
            if position < len(parsed.assertion_indices)
        )
        stable_command_indices = set(
            parsed.assertion_indices[position]
            for position in stable_positions
            if position < len(parsed.assertion_indices)
        )
        union_command_indices = set(
            parsed.assertion_indices[position]
            for position in union_positions
            if position < len(parsed.assertion_indices)
        )

        info = UnsatCoreInfo(
            available=True,
            core_positions=set(representative_positions),
            core_command_indices=representative_command_indices,
            core_size=len(representative_positions),
            total_assertions=len(parsed.assertion_indices),
            stable_positions=stable_positions,
            stable_command_indices=stable_command_indices,
            stable_core_size=len(stable_positions),
            union_positions=union_positions,
            union_command_indices=union_command_indices,
            union_core_size=len(union_positions),
            sample_count=len(sampled_cores),
            distinct_core_count=len(distinct_signatures),
            hit_counts=hit_counts,
            error_message=None,
        )
        cache[smt_code] = info
        return info

    def _build_unsat_core_program(
        self,
        parsed: ParsedScript,
    ) -> Tuple[List[str], Dict[int, str]]:
        assertion_position_by_command = {}  # type: Dict[int, int]
        for position, command_index in enumerate(parsed.assertion_indices):
            assertion_position_by_command[command_index] = position

        base_commands = []  # type: List[str]
        named_assertions = {}  # type: Dict[int, str]
        for index, command in enumerate(parsed.commands):
            normalized = _normalize_command(command)
            if index in assertion_position_by_command:
                position = assertion_position_by_command[index]
                named_assertions[position] = _name_assert_command(
                    command,
                    "corf_a{}".format(position),
                )
                continue
            if _is_query_command(normalized):
                continue
            base_commands.append(command.strip())

        return base_commands, named_assertions

    def _compute_unsat_core_sample_budget(self, assertion_count: int) -> int:
        if assertion_count <= 0:
            return 0
        timeout_ms = self._settings.optimizer_unsat_core_sample_timeout_ms
        if timeout_ms <= 0:
            return 1
        if assertion_count > self._settings.optimizer_unsat_core_sample_assertion_limit:
            return 1
        if assertion_count <= 16:
            return 1
        if assertion_count <= 32:
            return min(2, self._settings.optimizer_unsat_core_samples)
        return max(1, self._settings.optimizer_unsat_core_samples)

    def _build_unsat_core_sampling_order(
        self,
        assertion_count: int,
        sample_index: int,
    ) -> List[int]:
        ordered_positions = list(range(assertion_count))
        if sample_index == 0:
            return ordered_positions
        rng = random.Random(assertion_count * 7919 + sample_index * 104729)
        rng.shuffle(ordered_positions)
        return ordered_positions

    def _run_unsat_core_sample(
        self,
        z3_module,
        base_commands: List[str],
        named_assertions: Dict[int, str],
        ordered_positions: List[int],
        sample_index: int,
        timeout_ms: int,
    ) -> Optional[Set[int]]:
        commands = list(base_commands)
        for position in ordered_positions:
            if position in named_assertions:
                commands.append(named_assertions[position])

        try:
            solver = z3_module.Solver()
            solver.set(unsat_core=True)
            solver.set(random_seed=sample_index + 1)
            if timeout_ms > 0:
                solver.set(timeout=timeout_ms)
            solver.from_string(_join_commands(commands))
            result = str(solver.check())
        except z3_module.Z3Exception:
            return None

        if result != "unsat":
            return None

        core_positions = set()  # type: Set[int]
        for item in solver.unsat_core():
            name = str(item)
            if not name.startswith("corf_a"):
                continue
            suffix = name[len("corf_a") :]
            if not suffix.isdigit():
                continue
            core_positions.add(int(suffix))

        return core_positions

    def _sort_unsat_positions_by_hit_count(
        self,
        positions: List[int],
        unsat_core_info: UnsatCoreInfo,
        prefer_rare: bool,
    ) -> List[int]:
        return sorted(
            positions,
            key=lambda position: (
                unsat_core_info.hit_counts.get(position, 0)
                if prefer_rare
                else -unsat_core_info.hit_counts.get(position, 0),
                position,
            ),
        )

    def _project_unsat_state_to_core(
        self,
        state: OptimizationState,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
    ) -> Tuple[Optional[OptimizationState], int]:
        if not self._settings.optimizer_enable_unsat_core_projection:
            return None, 0
        if state.unsat_core_info is None or not state.unsat_core_info.available:
            return None, 0
        if state.unsat_core_info.core_size <= 0:
            return None, 0
        if state.unsat_core_info.core_size >= state.metrics.assertion_count:
            return None, 0

        projected_script = self._project_script_to_unsat_core(
            state.script,
            state.unsat_core_info,
        )
        if projected_script.strip() == state.script.strip():
            return None, 0

        projected_validation = self._validate_cached(projected_script, validation_cache)
        if not self._preserves_required_status(projected_validation, "unsat"):
            return None, 0

        projected_state = self._evaluate_state(
            projected_script,
            projected_validation,
            "unsat",
            reference_metrics,
            reference_validation,
            unsat_core_cache,
        )
        projection_reductions = max(
            0,
            state.metrics.assertion_count - projected_state.metrics.assertion_count,
        )
        if projection_reductions <= 0:
            return None, 0
        return projected_state, projection_reductions

    def _tighten_unsat_state_with_projection(
        self,
        state: OptimizationState,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        validation_cache: Dict[str, ValidationSummary],
        unsat_core_cache: Dict[str, UnsatCoreInfo],
    ) -> Tuple[OptimizationState, int, int]:
        current_state = state
        projection_rounds = 0
        projection_reductions = 0

        while True:
            projected_state, reduction_count = self._project_unsat_state_to_core(
                current_state,
                reference_metrics,
                reference_validation,
                validation_cache,
                unsat_core_cache,
            )
            if projected_state is None:
                break
            if not self._is_structurally_smaller(projected_state, current_state):
                break
            current_state = projected_state
            projection_rounds += 1
            projection_reductions += reduction_count

        return current_state, projection_rounds, projection_reductions

    def _project_script_to_unsat_core(
        self,
        smt_code: str,
        unsat_core_info: UnsatCoreInfo,
    ) -> str:
        parsed = ParsedScript.parse(smt_code)
        removed_indices = set()  # type: Set[int]
        for command_index in parsed.assertion_indices:
            if command_index not in unsat_core_info.core_command_indices:
                removed_indices.add(command_index)
        return parsed.remove_command_indices(removed_indices)

    def _evaluate_state(
        self,
        script: str,
        validation: ValidationSummary,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        unsat_core_cache: Dict[str, UnsatCoreInfo],
    ) -> OptimizationState:
        metrics = self._collect_metrics(script)
        unsat_core_info = None  # type: Optional[UnsatCoreInfo]
        if baseline_status == "unsat":
            unsat_core_info = self._get_unsat_core_info(script, unsat_core_cache)

        compactness_score = self._compactness_score(reference_metrics, metrics)
        semantic_score = self._semantic_score(
            baseline_status,
            reference_metrics,
            metrics,
            reference_validation,
            validation,
            unsat_core_info,
        )
        solver_score = self._solver_score(
            baseline_status,
            reference_validation,
            validation,
            unsat_core_info,
        )

        reward = (
            self.REWARD_WEIGHTS[0] * compactness_score
            + self.REWARD_WEIGHTS[1] * semantic_score
            + self.REWARD_WEIGHTS[2] * solver_score
        )

        return OptimizationState(
            script=script,
            validation=validation.copy(deep=True),
            metrics=metrics,
            reward=reward,
            compactness_score=compactness_score,
            semantic_score=semantic_score,
            solver_score=solver_score,
            unsat_core_info=unsat_core_info,
        )

    def _collect_metrics(self, script: str) -> ScriptMetrics:
        parsed = ParsedScript.parse(script)
        normalized = _normalize_text(script)
        return ScriptMetrics(
            token_count=_count_tokens(normalized),
            assertion_count=len(parsed.assertion_indices),
            nesting_depth=_nesting_depth(script),
            normalized_text=normalized,
        )

    def _compactness_score(
        self,
        reference_metrics: ScriptMetrics,
        current_metrics: ScriptMetrics,
    ) -> float:
        token_gain = _ratio_gain(
            reference_metrics.token_count,
            current_metrics.token_count,
        )
        assertion_gain = _ratio_gain(
            reference_metrics.assertion_count,
            current_metrics.assertion_count,
        )
        depth_gain = _ratio_gain(
            reference_metrics.nesting_depth,
            current_metrics.nesting_depth,
        )
        return (
            self.COMPACTNESS_WEIGHTS[0] * token_gain
            + self.COMPACTNESS_WEIGHTS[1] * assertion_gain
            + self.COMPACTNESS_WEIGHTS[2] * depth_gain
        )

    def _semantic_score(
        self,
        baseline_status: str,
        reference_metrics: ScriptMetrics,
        current_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        current_validation: ValidationSummary,
        unsat_core_info: Optional[UnsatCoreInfo],
    ) -> float:
        if not self._same_solver_status(reference_validation, current_validation):
            return 0.0
        if not current_validation.passed:
            return 0.0

        similarity = SequenceMatcher(
            None,
            reference_metrics.normalized_text,
            current_metrics.normalized_text,
        ).ratio()

        if baseline_status != "unsat":
            return min(1.0, 0.75 + 0.25 * similarity)

        if unsat_core_info is not None and unsat_core_info.available:
            representative_focus = 1.0 - unsat_core_info.density
            stable_focus = 1.0 - unsat_core_info.stable_density
            union_focus = 1.0 - unsat_core_info.union_density
            return min(
                1.0,
                0.30
                + 0.20 * similarity
                + 0.25 * representative_focus
                + 0.15 * stable_focus
                + 0.10 * union_focus,
            )

        return min(1.0, 0.70 + 0.30 * similarity)

    def _solver_score(
        self,
        baseline_status: str,
        reference_validation: ValidationSummary,
        current_validation: ValidationSummary,
        unsat_core_info: Optional[UnsatCoreInfo],
    ) -> float:
        if not self._same_solver_status(reference_validation, current_validation):
            return 0.0
        if not current_validation.passed:
            return 0.0

        if (
            reference_validation.solver_time_ms is None
            or current_validation.solver_time_ms is None
            or reference_validation.solver_time_ms <= 0
        ):
            base_score = 1.0
        else:
            improvement = (
                reference_validation.solver_time_ms - current_validation.solver_time_ms
            ) / reference_validation.solver_time_ms
            base_score = max(0.0, min(1.0, 0.80 + 0.20 * improvement))

        if baseline_status == "unsat" and unsat_core_info is not None and unsat_core_info.available:
            base_score = min(1.0, base_score + 0.05 * (1.0 - unsat_core_info.union_density))

        return base_score

    def _validate_cached(
        self,
        script: str,
        validation_cache: Dict[str, ValidationSummary],
    ) -> ValidationSummary:
        cached = validation_cache.get(script)
        if cached is not None:
            return cached.copy(deep=True)
        result = self._validator.validate(script)
        validation_cache[script] = result.copy(deep=True)
        return result

    def _preserves_required_status(
        self,
        validation: ValidationSummary,
        baseline_status: str,
    ) -> bool:
        if not validation.passed:
            return False
        return (validation.solver_status or "").lower() == baseline_status

    def _same_solver_status(
        self,
        reference_validation: ValidationSummary,
        current_validation: ValidationSummary,
    ) -> bool:
        reference_status = (reference_validation.solver_status or "").lower()
        current_status = (current_validation.solver_status or "").lower()
        return bool(reference_status) and reference_status == current_status

    def _backpropagate(self, node: SearchNode, reward: float) -> None:
        current = node
        while current is not None:
            current.visits += 1
            current.value_sum += reward
            current = current.parent

    def _ucb_score(self, parent: SearchNode, child: SearchNode) -> float:
        if child.visits == 0:
            return float("inf")
        average_value = child.value_sum / child.visits
        exploration = self._settings.optimizer_exploration_weight * math.sqrt(
            math.log(max(parent.visits, 1) + 1.0) / child.visits
        )
        return average_value + exploration

    def _accept_as_new_best(
        self,
        candidate: OptimizationState,
        incumbent: OptimizationState,
    ) -> bool:
        if not self._is_better_state(candidate, incumbent):
            return False

        reward_gain = candidate.reward - incumbent.reward
        structural_gain = (
            candidate.metrics.assertion_count < incumbent.metrics.assertion_count
            or candidate.metrics.token_count < incumbent.metrics.token_count
        )
        mus_gain = self._unsat_core_size(candidate) < self._unsat_core_size(incumbent)
        return reward_gain >= self._settings.optimizer_min_reward_gain or structural_gain or mus_gain

    def _is_better_state(
        self,
        candidate: OptimizationState,
        incumbent: OptimizationState,
    ) -> bool:
        if candidate.reward > incumbent.reward:
            return True
        if candidate.reward < incumbent.reward:
            return False
        if candidate.metrics.assertion_count < incumbent.metrics.assertion_count:
            return True
        if candidate.metrics.assertion_count > incumbent.metrics.assertion_count:
            return False
        if self._unsat_core_size(candidate) < self._unsat_core_size(incumbent):
            return True
        if self._unsat_core_size(candidate) > self._unsat_core_size(incumbent):
            return False
        return candidate.metrics.token_count < incumbent.metrics.token_count

    def _unsat_core_size(self, state: OptimizationState) -> int:
        if state.unsat_core_info is None or not state.unsat_core_info.available:
            return state.metrics.assertion_count
        return state.unsat_core_info.core_size

    def _is_structurally_smaller(
        self,
        candidate: OptimizationState,
        incumbent: OptimizationState,
    ) -> bool:
        if candidate.metrics.assertion_count < incumbent.metrics.assertion_count:
            return True
        if candidate.metrics.assertion_count > incumbent.metrics.assertion_count:
            return False
        return candidate.metrics.token_count < incumbent.metrics.token_count

    def _should_stop_for_time_budget(self, started_at: float) -> bool:
        if self._settings.optimizer_time_budget_ms <= 0:
            return False
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return elapsed_ms >= self._settings.optimizer_time_budget_ms

    def _has_expandable_frontier(self, node: SearchNode) -> bool:
        if node.depth < self._settings.optimizer_max_depth:
            if node.pending_children is None:
                return True
            if node.pending_children:
                return True
        for child in node.children:
            if self._has_expandable_frontier(child):
                return True
        return False

    def _build_summary(
        self,
        baseline_status: str,
        search_used: bool,
        state: OptimizationState,
        search_stats: SearchStatistics,
        used_llm_postpass: bool,
        notes: List[str],
    ) -> OptimizationSummary:
        return OptimizationSummary(
            strategy="mcts_corf",
            baseline_status=baseline_status,
            search_used=search_used,
            iterations=search_stats.iterations_run,
            explored_states=search_stats.explored_states,
            safe_deletions=search_stats.safe_deletions,
            explicit_reductions=search_stats.explicit_reductions,
            best_reward=round(state.reward, 4),
            compactness_score=round(state.compactness_score, 4),
            semantic_score=round(state.semantic_score, 4),
            solver_score=round(state.solver_score, 4),
            used_llm_postpass=used_llm_postpass,
            termination_reason=search_stats.termination_reason,
            best_depth=search_stats.best_depth,
            stagnation_rounds=search_stats.stagnation_rounds,
            unsat_core_available=search_stats.unsat_core_available,
            reference_unsat_core_size=search_stats.reference_unsat_core_size,
            final_unsat_core_size=search_stats.final_unsat_core_size,
            unsat_core_sample_count=search_stats.unsat_core_sample_count,
            unsat_core_distinct_count=search_stats.unsat_core_distinct_count,
            stable_unsat_core_size=search_stats.stable_unsat_core_size,
            union_unsat_core_size=search_stats.union_unsat_core_size,
            core_guided_actions=search_stats.core_guided_actions,
            protected_core_skips=search_stats.protected_core_skips,
            core_release_rounds=search_stats.core_release_rounds,
            core_projection_applied=search_stats.core_projection_applied,
            core_projection_reductions=search_stats.core_projection_reductions,
            notes=notes,
        )

    def _build_llm_context(self, summary: OptimizationSummary) -> str:
        lines = [
            "Deterministic optimization strategy: MCTS-CORF-style safe deletion search.",
            "Baseline solver status: {}.".format(summary.baseline_status or "unknown"),
            "Search used: {}.".format("yes" if summary.search_used else "no"),
            "Search iterations: {}.".format(summary.iterations),
            "Explored states: {}.".format(summary.explored_states),
            "Accepted safe deletions: {}.".format(summary.safe_deletions),
            "Explicit reductions already applied: {}.".format(summary.explicit_reductions),
            "Termination reason: {}.".format(summary.termination_reason or "unknown"),
        ]

        if summary.baseline_status == "sat":
            lines.append(
                "Preservation objective: keep logical equivalence while removing redundant assertions."
            )
        elif summary.baseline_status == "unsat":
            lines.append(
                "Preservation objective: keep the script UNSAT while shrinking it toward a smaller unsatisfied subset."
            )
            lines.append(
                "UNSAT core guidance available: {}.".format(
                    "yes" if summary.unsat_core_available else "no"
                )
            )
            if summary.reference_unsat_core_size is not None:
                lines.append(
                    "Reference UNSAT core size: {}.".format(summary.reference_unsat_core_size)
                )
            if summary.final_unsat_core_size is not None:
                lines.append(
                    "Best-state UNSAT core size: {}.".format(summary.final_unsat_core_size)
                )
            lines.append(
                "UNSAT core samples: {} total, {} distinct.".format(
                    summary.unsat_core_sample_count,
                    summary.unsat_core_distinct_count,
                )
            )
            if summary.stable_unsat_core_size is not None:
                lines.append(
                    "Stable-core intersection size: {}.".format(summary.stable_unsat_core_size)
                )
            if summary.union_unsat_core_size is not None:
                lines.append(
                    "Sampled-core union size: {}.".format(summary.union_unsat_core_size)
                )
            lines.append(
                "Core-guided safe deletions accepted: {}.".format(summary.core_guided_actions)
            )
            lines.append(
                "Protected core skips: {}.".format(summary.protected_core_skips)
            )
            lines.append(
                "Core release rounds: {}.".format(summary.core_release_rounds)
            )
            if summary.core_projection_applied:
                lines.append(
                    "UNSAT core projection released {} assertion(s) before or after search.".format(
                        summary.core_projection_reductions
                    )
                )

        if summary.best_reward is not None:
            lines.append("Best search reward: {:.4f}.".format(summary.best_reward))
        if summary.notes:
            lines.append("Deterministic notes:")
            for note in summary.notes:
                lines.append("- {}".format(note))

        lines.append(
            "Do not reintroduce constraints that deterministic analysis already removed as redundant unless validation evidence shows they are required."
        )
        lines.append(
            "Prefer local merge, rewrite, or reorder steps only when they preserve the stated objective."
        )
        return "\n".join(lines)

    def _describe_termination(self, termination_reason: str) -> str:
        mapping = {
            "time_budget_reached": "Search stopped because the configured optimizer time budget was exhausted.",
            "frontier_exhausted": "Search stopped because no additional safe deletion frontier remained.",
            "empty_assertion_set": "Search stopped because the current best candidate no longer contains assertions.",
            "stagnation_limit": "Search stopped because the best candidate did not improve within the configured patience window.",
            "max_iterations_reached": "Search stopped because the configured optimizer iteration budget was reached.",
            "unsupported_reference_status": "Search was skipped because the reference status was neither sat nor unsat.",
        }
        return mapping.get(termination_reason, "Search stopped for an unspecified reason.")


def _python_z3_available() -> bool:
    try:
        import z3  # type: ignore
    except ImportError:
        return False
    return True


def _split_top_level_commands(smt_code: str) -> List[str]:
    commands = []  # type: List[str]
    buffer = []  # type: List[str]
    depth = 0
    in_string = False
    escape = False
    in_comment = False

    for character in smt_code:
        if in_comment:
            if character == "\n":
                in_comment = False
                if depth > 0:
                    buffer.append(" ")
            continue

        if in_string:
            buffer.append(character)
            if escape:
                escape = False
            elif character == "\\":
                escape = True
            elif character == '"':
                in_string = False
            continue

        if character == ";":
            in_comment = True
            continue

        if character == '"':
            in_string = True
            buffer.append(character)
            continue

        if character == "(":
            depth += 1
            buffer.append(character)
            continue

        if character == ")":
            depth = max(0, depth - 1)
            buffer.append(character)
            if depth == 0:
                command = "".join(buffer).strip()
                if command:
                    commands.append(command)
                buffer = []
            continue

        if depth == 0:
            if character.isspace():
                if buffer:
                    command = "".join(buffer).strip()
                    if command:
                        commands.append(command)
                    buffer = []
                continue
            buffer.append(character)
        else:
            buffer.append(character)

    trailing = "".join(buffer).strip()
    if trailing:
        commands.append(trailing)
    return commands


def _join_commands(commands: List[str]) -> str:
    return "\n".join(command.strip() for command in commands if command.strip()).strip()


def _normalize_command(command: str) -> str:
    without_comments = []  # type: List[str]
    for raw_line in command.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if line:
            without_comments.append(line)
    normalized = " ".join(without_comments)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_text(content: str) -> str:
    normalized_lines = []  # type: List[str]
    for raw_line in content.splitlines():
        line = raw_line.split(";", 1)[0]
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _count_tokens(normalized_text: str) -> int:
    if not normalized_text:
        return 0
    return len(re.findall(r"\(|\)|[^\s()]+", normalized_text))


def _nesting_depth(content: str) -> int:
    depth = 0
    max_depth = 0
    in_string = False
    escape = False
    in_comment = False

    for character in content:
        if in_comment:
            if character == "\n":
                in_comment = False
            continue

        if in_string:
            if escape:
                escape = False
            elif character == "\\":
                escape = True
            elif character == '"':
                in_string = False
            continue

        if character == ";":
            in_comment = True
            continue
        if character == '"':
            in_string = True
            continue
        if character == "(":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif character == ")":
            depth = max(0, depth - 1)

    return max_depth


def _ratio_gain(reference_value: int, current_value: int) -> float:
    if reference_value <= 0:
        return 0.0
    return max(0.0, float(reference_value - current_value) / float(reference_value))


def _name_assert_command(command: str, name: str) -> str:
    stripped = command.strip()
    match = re.match(r"^\(\s*assert\b", stripped, flags=re.IGNORECASE)
    if match is None:
        return stripped
    inner = stripped[match.end() :].strip()
    if inner.endswith(")"):
        inner = inner[:-1].rstrip()
    return "(assert (! {} :named {}))".format(inner, name)


def _is_query_command(normalized_command: str) -> bool:
    return normalized_command in {
        "(check-sat)",
        "(get-model)",
        "(get-unsat-core)",
        "(get-proof)",
        "(get-assignment)",
        "(exit)",
    }



