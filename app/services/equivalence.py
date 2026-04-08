import re
from typing import Any, Dict, List, Optional

from app.models.schemas import EquivalenceSummary


class SMTEquivalenceChecker:
    def check(self, reference_smt: str, candidate_smt: str) -> EquivalenceSummary:
        normalized_reference = _normalize_smt_text(reference_smt)
        normalized_candidate = _normalize_smt_text(candidate_smt)
        structurally_identical = normalized_reference == normalized_candidate

        if structurally_identical:
            return EquivalenceSummary(
                checked=True,
                available=True,
                backend="normalized-text",
                equivalent=True,
                structurally_identical=True,
                error_message=None,
            )

        try:
            import z3  # type: ignore
        except ImportError:
            return EquivalenceSummary(
                checked=False,
                available=False,
                backend=None,
                equivalent=None,
                structurally_identical=False,
                error_message=(
                    "Python package `z3-solver` is required for semantic equivalence checking."
                ),
            )

        try:
            reference_solver = z3.Solver()
            reference_solver.from_string(reference_smt)
            candidate_solver = z3.Solver()
            candidate_solver.from_string(candidate_smt)

            reference_assertions = list(reference_solver.assertions())
            candidate_assertions = list(candidate_solver.assertions())

            reference_formula = _build_formula(z3, reference_assertions)
            candidate_formula = _build_formula(z3, candidate_assertions)

            equivalence_solver = z3.Solver()
            equivalence_solver.add(z3.Xor(reference_formula, candidate_formula))
            result = equivalence_solver.check()
        except z3.Z3Exception as exc:
            return EquivalenceSummary(
                checked=False,
                available=True,
                backend="python-z3",
                equivalent=None,
                structurally_identical=False,
                error_message="Failed to run semantic equivalence check: {}".format(exc),
            )

        status = str(result)
        if status == "unsat":
            return EquivalenceSummary(
                checked=True,
                available=True,
                backend="python-z3",
                equivalent=True,
                structurally_identical=False,
                reference_assertion_count=len(reference_assertions),
                candidate_assertion_count=len(candidate_assertions),
                error_message=None,
            )

        if status == "sat":
            model = equivalence_solver.model()
            reference_holds = _z3_bool_to_python(
                z3,
                model.eval(reference_formula, model_completion=True),
            )
            candidate_holds = _z3_bool_to_python(
                z3,
                model.eval(candidate_formula, model_completion=True),
            )
            divergence_kind = _infer_divergence_kind(reference_holds, candidate_holds)
            counterexample_model = _serialize_model(model)

            return EquivalenceSummary(
                checked=True,
                available=True,
                backend="python-z3",
                equivalent=False,
                structurally_identical=False,
                reference_assertion_count=len(reference_assertions),
                candidate_assertion_count=len(candidate_assertions),
                divergence_kind=divergence_kind,
                reference_holds_under_counterexample=reference_holds,
                candidate_holds_under_counterexample=candidate_holds,
                counterexample_model=counterexample_model,
                error_message=_build_counterexample_error(
                    reference_holds,
                    candidate_holds,
                    counterexample_model,
                ),
            )

        return EquivalenceSummary(
            checked=True,
            available=True,
            backend="python-z3",
            equivalent=None,
            structurally_identical=False,
            reference_assertion_count=len(reference_assertions),
            candidate_assertion_count=len(candidate_assertions),
            error_message="Z3 returned `unknown` during semantic equivalence checking.",
        )


def _build_formula(z3_module: Any, assertions: List[Any]) -> Any:
    if not assertions:
        return z3_module.BoolVal(True)
    if len(assertions) == 1:
        return assertions[0]
    return z3_module.And(*assertions)


def _normalize_smt_text(content: str) -> str:
    normalized_lines = []  # type: List[str]
    for raw_line in content.splitlines():
        line = raw_line.split(";", 1)[0]
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _z3_bool_to_python(z3_module: Any, value: Any) -> Optional[bool]:
    if z3_module.is_true(value):
        return True
    if z3_module.is_false(value):
        return False
    return None


def _infer_divergence_kind(
    reference_holds: Optional[bool],
    candidate_holds: Optional[bool],
) -> Optional[str]:
    if reference_holds is True and candidate_holds is False:
        return "candidate_stronger_than_reference"
    if reference_holds is False and candidate_holds is True:
        return "candidate_weaker_than_reference"
    return None


def _serialize_model(model: Any) -> Dict[str, str]:
    serialized = {}  # type: Dict[str, str]
    declarations = sorted(model.decls(), key=lambda decl: str(decl.name()))
    for declaration in declarations:
        serialized[str(declaration.name())] = str(model[declaration])
    return serialized


def _build_counterexample_error(
    reference_holds: Optional[bool],
    candidate_holds: Optional[bool],
    counterexample_model: Dict[str, str],
) -> str:
    assignment_preview = _format_counterexample_model(counterexample_model)

    if reference_holds is True and candidate_holds is False:
        return (
            "The optimized SMT-LIB is not logically equivalent to the reference constraints. "
            "Under the counterexample model, the reference constraints hold but the candidate constraints do not, "
            "so the candidate is too strong. Counterexample: {}".format(assignment_preview)
        )

    if reference_holds is False and candidate_holds is True:
        return (
            "The optimized SMT-LIB is not logically equivalent to the reference constraints. "
            "Under the counterexample model, the candidate constraints hold but the reference constraints do not, "
            "so the candidate is too weak. Counterexample: {}".format(assignment_preview)
        )

    return (
        "The optimized SMT-LIB is not logically equivalent to the reference constraints. "
        "Z3 found a counterexample model where the two formulas evaluate differently. Counterexample: {}"
    ).format(assignment_preview)


def _format_counterexample_model(counterexample_model: Dict[str, str]) -> str:
    if not counterexample_model:
        return "<empty model>"
    parts = []  # type: List[str]
    for name in sorted(counterexample_model):
        parts.append("{} = {}".format(name, counterexample_model[name]))
    return ", ".join(parts)
