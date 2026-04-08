from typing import List, Optional, Set

from app.models.schemas import ContentType
from app.services.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock"

    async def natural_language_to_smt(self, content: str) -> str:
        return (
            "(set-logic ALL)\n"
            f"; source: {content}\n"
            "(check-sat)"
        )

    async def optimize_smt(
        self,
        content: str,
        optimization_context: Optional[str] = None,
    ) -> str:
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        deduplicated = []  # type: List[str]
        seen = set()  # type: Set[str]

        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            deduplicated.append(line)

        optimized = "\n".join(deduplicated)
        if optimization_context and "unsat" in optimization_context.lower():
            optimized = optimized.replace("(check-sat)\n(check-sat)", "(check-sat)")
        if "(check-sat)" not in optimized:
            optimized = f"{optimized}\n(check-sat)" if optimized else "(check-sat)"
        return optimized

    async def diagnose_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        root_cause = "validation failure reported by deterministic checks"
        broken_fragment = "unknown"
        preserve = "preserve the original semantics and all valid declarations"
        minimal_fix = "apply a narrow correction around the reported failing constraint"

        lowered = validation_feedback.lower()
        if "too strong" in lowered:
            root_cause = "candidate became stronger than the reference"
            minimal_fix = "restore the missing satisfying cases exposed by the counterexample"
        elif "too weak" in lowered:
            root_cause = "candidate became weaker than the reference"
            minimal_fix = "restore the missing restriction exposed by the counterexample"
        elif "syntax" in lowered or "parser" in lowered:
            root_cause = "syntax or malformed SMT-LIB structure"
            minimal_fix = "repair the malformed syntax without changing nearby valid constraints"
        elif "unsat" in lowered and "preserved" in lowered:
            root_cause = "the candidate no longer preserves the required unsat status"
            minimal_fix = "restore the conflict-relevant constraint that was removed too aggressively"

        if "check-sat" in current_output:
            broken_fragment = "one or more assertions before the final check-sat"

        return "\n".join(
            [
                "VERDICT: failed",
                "ROOT_CAUSE: {}".format(root_cause),
                "BROKEN_FRAGMENT: {}".format(broken_fragment),
                "PRESERVE: {}".format(preserve),
                "MINIMAL_FIX: {}".format(minimal_fix),
            ]
        )

    async def reflect_on_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        verifier_report: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        lowered = validation_feedback.lower()
        failure_pattern = "local SMT inconsistency or malformed constraint"
        patch_strategy = "edit the smallest failing assertion or declaration only"
        counterexample_use = "use the counterexample assignment to test the repaired candidate"

        if "candidate became stronger" in verifier_report.lower() or "too strong" in lowered:
            failure_pattern = "the optimized candidate over-constrained the formula"
            patch_strategy = "weaken only the offending constraint so the counterexample is accepted when the reference accepts it"
        elif "candidate became weaker" in verifier_report.lower() or "too weak" in lowered:
            failure_pattern = "the optimized candidate lost a necessary restriction"
            patch_strategy = "restore the missing restriction so the counterexample is rejected when the reference rejects it"
        elif "syntax" in lowered or "parser" in lowered:
            failure_pattern = "syntax-level corruption"
            patch_strategy = "repair the malformed tokens or parentheses without changing valid semantics"
        elif "unsat" in lowered and "preserved" in lowered:
            failure_pattern = "the optimization removed a conflict-critical constraint"
            patch_strategy = "reintroduce only the smallest constraint fragment needed to recover unsat"

        do_not_change = "do not rewrite unrelated declarations or already-valid assertions"

        return "\n".join(
            [
                "FAILURE_PATTERN: {}".format(failure_pattern),
                "PATCH_STRATEGY: {}".format(patch_strategy),
                "DO_NOT_CHANGE: {}".format(do_not_change),
                "COUNTEREXAMPLE_USE: {}".format(counterexample_use),
            ]
        )

    async def repair_smt(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        candidate = _strip_markdown_fences(current_output).strip()
        if not candidate:
            candidate = "(check-sat)"

        lines = [line.rstrip() for line in candidate.splitlines() if line.strip()]
        deduplicated = []  # type: List[str]
        seen = set()  # type: Set[str]
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            deduplicated.append(line)

        candidate = "\n".join(deduplicated)

        if request_type == ContentType.NATURAL_LANGUAGE and "(set-logic" not in candidate:
            candidate = f"(set-logic ALL)\n{candidate}"

        if "(check-sat)" not in candidate:
            candidate = f"{candidate}\n(check-sat)"

        balance = candidate.count("(") - candidate.count(")")
        if balance > 0:
            candidate = f"{candidate}{')' * balance}"

        return candidate.strip()


def _strip_markdown_fences(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
