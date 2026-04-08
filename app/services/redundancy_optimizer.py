import math
import re
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
class OptimizationState:
    script: str
    validation: ValidationSummary
    metrics: ScriptMetrics
    reward: float
    compactness_score: float
    semantic_score: float
    solver_score: float


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

        root_state = self._evaluate_state(
            working_script,
            working_validation,
            reference_metrics,
            reference_validation,
        )
        best_state = root_state

        if not _python_z3_available():
            notes.append(
                "Python package `z3-solver` is unavailable, so only explicit reductions were applied."
            )
            summary = self._build_summary(
                baseline_status=baseline_status,
                search_used=False,
                iterations=0,
                explored_states=1,
                safe_deletions=0,
                explicit_reductions=explicit_reductions,
                state=best_state,
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
        explored_states = 1
        safe_deletions = 0
        iterations_run = 0

        for _ in range(self._settings.optimizer_max_iterations):
            iterations_run += 1
            selected = self._select_node(
                root,
                reference_metrics,
                reference_validation,
                baseline_status,
                validation_cache,
                seen_scripts,
            )
            expanded, generated_count = self._expand_node(
                selected,
                reference_metrics,
                reference_validation,
                baseline_status,
                validation_cache,
                seen_scripts,
            )
            safe_deletions += generated_count

            target = expanded or selected
            if expanded is not None:
                explored_states += 1

            self._backpropagate(target, target.state.reward)
            if self._is_better_state(target.state, best_state):
                best_state = target.state

            if best_state.metrics.assertion_count == 0:
                break

        summary = self._build_summary(
            baseline_status=baseline_status,
            search_used=True,
            iterations=iterations_run,
            explored_states=explored_states,
            safe_deletions=safe_deletions,
            explicit_reductions=explicit_reductions,
            state=best_state,
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
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        baseline_status: str,
        validation_cache: Dict[str, ValidationSummary],
        seen_scripts: Set[str],
    ) -> SearchNode:
        current = root
        while current.depth < self._settings.optimizer_max_depth:
            pending_children, _ = self._ensure_children_generated(
                current,
                reference_metrics,
                reference_validation,
                baseline_status,
                validation_cache,
                seen_scripts,
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
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        baseline_status: str,
        validation_cache: Dict[str, ValidationSummary],
        seen_scripts: Set[str],
    ) -> Tuple[Optional[SearchNode], int]:
        pending_children, generated_count = self._ensure_children_generated(
            node,
            reference_metrics,
            reference_validation,
            baseline_status,
            validation_cache,
            seen_scripts,
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
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        baseline_status: str,
        validation_cache: Dict[str, ValidationSummary],
        seen_scripts: Set[str],
    ) -> Tuple[List[OptimizationState], int]:
        if node.pending_children is not None:
            return node.pending_children, 0

        child_states = self._generate_child_states(
            node.state.script,
            reference_metrics,
            reference_validation,
            baseline_status,
            validation_cache,
            seen_scripts,
        )
        node.pending_children = child_states
        return node.pending_children, len(child_states)

    def _generate_child_states(
        self,
        current_script: str,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        baseline_status: str,
        validation_cache: Dict[str, ValidationSummary],
        seen_scripts: Set[str],
    ) -> List[OptimizationState]:
        parsed = ParsedScript.parse(current_script)
        if not parsed.assertion_indices:
            return []

        child_states = []  # type: List[OptimizationState]
        sat_context = self._load_sat_context(current_script) if baseline_status == "sat" else None

        for assertion_position, command_index in enumerate(parsed.assertion_indices):
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
                reference_metrics,
                reference_validation,
            )
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

    def _evaluate_state(
        self,
        script: str,
        validation: ValidationSummary,
        reference_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
    ) -> OptimizationState:
        metrics = self._collect_metrics(script)
        compactness_score = self._compactness_score(reference_metrics, metrics)
        semantic_score = self._semantic_score(
            reference_metrics,
            metrics,
            reference_validation,
            validation,
        )
        solver_score = self._solver_score(reference_validation, validation)

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
        reference_metrics: ScriptMetrics,
        current_metrics: ScriptMetrics,
        reference_validation: ValidationSummary,
        current_validation: ValidationSummary,
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
        return min(1.0, 0.8 + 0.2 * similarity)

    def _solver_score(
        self,
        reference_validation: ValidationSummary,
        current_validation: ValidationSummary,
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
            return 1.0

        improvement = (
            reference_validation.solver_time_ms - current_validation.solver_time_ms
        ) / reference_validation.solver_time_ms
        return max(0.0, min(1.0, 0.8 + 0.2 * improvement))

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
        return reference_status and reference_status == current_status

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
        return candidate.metrics.token_count < incumbent.metrics.token_count

    def _build_summary(
        self,
        baseline_status: str,
        search_used: bool,
        iterations: int,
        explored_states: int,
        safe_deletions: int,
        explicit_reductions: int,
        state: OptimizationState,
        used_llm_postpass: bool,
        notes: List[str],
    ) -> OptimizationSummary:
        return OptimizationSummary(
            strategy="mcts_corf",
            baseline_status=baseline_status,
            search_used=search_used,
            iterations=iterations,
            explored_states=explored_states,
            safe_deletions=safe_deletions,
            explicit_reductions=explicit_reductions,
            best_reward=round(state.reward, 4),
            compactness_score=round(state.compactness_score, 4),
            semantic_score=round(state.semantic_score, 4),
            solver_score=round(state.solver_score, 4),
            used_llm_postpass=used_llm_postpass,
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
        ]

        if summary.baseline_status == "sat":
            lines.append(
                "Preservation objective: keep logical equivalence while removing redundant assertions."
            )
        elif summary.baseline_status == "unsat":
            lines.append(
                "Preservation objective: keep the script UNSAT while shrinking it toward a smaller unsatisfied subset."
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
