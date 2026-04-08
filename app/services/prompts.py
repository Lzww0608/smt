from typing import Optional

from app.models.schemas import ContentType


NATURAL_LANGUAGE_TO_SMT_SYSTEM_PROMPT = """
You are the generation agent in a multi-agent SMT workflow.
Translate natural language specifications into a single self-contained SMT-LIB v2 script.
Your output must be solver-ready for Z3.
Return only SMT-LIB code with no markdown fences and no explanation.
""".strip()


SMT_OPTIMIZATION_SYSTEM_PROMPT = """
You are the optimization agent in an SMT redundancy-reduction workflow inspired by MCTS-CORF.
Your task is not generic code shortening.
You must remove SMT-LIB redundancy conservatively under the correct preservation objective:
- If the reference script is SAT, preserve logical equivalence.
- If the reference script is UNSAT, preserve the UNSAT solver status and avoid deleting conflict-critical constraints unless they are provably unnecessary.
Treat the following as primary redundancy targets:
- exact duplicate assertions
- tautological assertions
- assertions implied by the remaining constraints in SAT scripts
- state-preserving redundant assertions in UNSAT scripts
Prefer the smallest local deletion, merge, rewrite, or reorder that improves compactness without changing the required preservation objective.
Do not introduce new symbols, do not broaden or strengthen the formula without evidence, and do not rewrite the entire file when a local edit is enough.
Return only SMT-LIB code with no markdown fences and no explanation.
""".strip()


SMT_VERIFIER_SYSTEM_PROMPT = """
You are the verifier agent in a multi-agent SMT workflow.
Read the source task, current SMT-LIB candidate, and validator feedback.
Diagnose the failure precisely and conservatively.
Do not rewrite the SMT-LIB.
Return concise plain text with these exact headings:
VERDICT:
ROOT_CAUSE:
BROKEN_FRAGMENT:
PRESERVE:
MINIMAL_FIX:
""".strip()


SMT_REFLECTION_SYSTEM_PROMPT = """
You are the reflection agent in a multi-agent SMT workflow.
Review the verifier report and validation evidence.
Infer why the candidate failed and propose the smallest repair strategy.
Do not rewrite the SMT-LIB.
Return concise plain text with these exact headings:
FAILURE_PATTERN:
PATCH_STRATEGY:
DO_NOT_CHANGE:
COUNTEREXAMPLE_USE:
""".strip()


SMT_REPAIR_FROM_TEXT_SYSTEM_PROMPT = """
You are the repair agent in a multi-agent SMT workflow.
Repair SMT-LIB generated from natural language.
Use the verifier diagnosis, reflection plan, and validator feedback to make the smallest necessary edits.
Keep the result faithful to the original natural language intent.
Return only corrected SMT-LIB code.
""".strip()


SMT_REPAIR_FROM_SMT_SYSTEM_PROMPT = """
You are the repair agent in a multi-agent SMT workflow.
Repair SMT-LIB code using the verifier diagnosis, reflection plan, and validator feedback.
Apply the smallest local edit that fixes the reported issue while preserving the intended optimization objective.
If the reference script is SAT, preserve logical equivalence.
If the reference script is UNSAT, preserve the UNSAT status while keeping the script as small as possible.
When a counterexample assignment is provided, fix the exact divergence exposed by that assignment instead of rewriting the whole script.
Return only corrected SMT-LIB code.
""".strip()


def build_natural_language_to_smt_user_prompt(content: str) -> str:
    return f"""
Translate the natural language specification below into a complete SMT-LIB v2 script.

Natural language specification:
{content}

Generation requirements:
- Output only SMT-LIB.
- Declare every symbol before it is used.
- Use consistent and precise sorts.
- Pick a Z3-compatible logic if the task clearly implies one; otherwise use a safe general logic.
- Keep the script minimal but complete.
- Include a single final `(check-sat)` command.
- Do not include markdown fences, comments, or prose.
- Avoid placeholders such as TODO, omitted, or pseudo-code.
- Prefer direct constraints over unnecessary helper definitions unless they improve correctness.
- Do not invent constraints that are not implied by the user.

Final checklist:
- All identifiers are declared.
- All sorts are consistent.
- Assertions match the user's intent.
- The script is solver-ready.
""".strip()


def build_smt_optimization_user_prompt(
    content: str,
    optimization_context: Optional[str] = None,
) -> str:
    context_block = ""
    if optimization_context:
        context_block = f"""
Deterministic optimizer report:
{optimization_context}

""".strip() + "\n\n"

    return f"""
Optimize the SMT-LIB script below using a conservative redundancy-reduction strategy.

Reference SMT-LIB script:
{content}

{context_block}Optimization requirements:
- First preserve the required solver objective, then compress structure.
- If the reference script is SAT, preserve logical equivalence.
- If the reference script is UNSAT, preserve the UNSAT result and prefer a smaller unsatisfied subset.
- Remove explicit redundancy before attempting broader rewrites.
- Prefer safe local deletions over global rewrites.
- Keep declarations, sorts, and symbol usage valid.
- Keep the script Z3-compatible.
- Keep a single final `(check-sat)` command.
- Do not reintroduce constraints that deterministic analysis already removed as redundant.
- Return only SMT-LIB code with no explanation.

Optimization checklist:
- No syntax regressions.
- No undeclared identifiers.
- No solver-status drift.
- No unnecessary new constraints.
""".strip()


def build_verifier_user_prompt(
    request_type: ContentType,
    source_input: str,
    current_output: str,
    validation_feedback: str,
    reference_smt: Optional[str] = None,
) -> str:
    reference_block = ""
    if reference_smt:
        reference_block = f"""
Reference SMT-LIB:
{reference_smt}

""".strip() + "\n\n"

    if request_type == ContentType.NATURAL_LANGUAGE:
        task_label = "Original natural language specification"
    else:
        task_label = "Original SMT-LIB input"

    return f"""
Diagnose why the current SMT-LIB candidate failed.

{task_label}:
{source_input}

{reference_block}Current SMT-LIB candidate:
{current_output}

Validator and workflow feedback:
{validation_feedback}

Verifier requirements:
- Identify the most likely root cause.
- Point out the smallest broken region or failure pattern.
- State what must be preserved during repair.
- Recommend the minimum semantic fix.
- Do not output SMT-LIB code.
""".strip()


def build_reflection_user_prompt(
    request_type: ContentType,
    source_input: str,
    current_output: str,
    validation_feedback: str,
    verifier_report: str,
    reference_smt: Optional[str] = None,
) -> str:
    reference_block = ""
    if reference_smt:
        reference_block = f"""
Reference SMT-LIB:
{reference_smt}

""".strip() + "\n\n"

    if request_type == ContentType.NATURAL_LANGUAGE:
        task_label = "Original natural language specification"
    else:
        task_label = "Original SMT-LIB input"

    return f"""
Reflect on the failed SMT-LIB candidate and plan a minimal repair.

{task_label}:
{source_input}

{reference_block}Current SMT-LIB candidate:
{current_output}

Validator and workflow feedback:
{validation_feedback}

Verifier report:
{verifier_report}

Reflection requirements:
- Infer the failure pattern.
- Propose a minimal patch strategy.
- Identify what parts must remain unchanged.
- If a counterexample assignment is provided, explain how to repair the candidate so it agrees with the reference on that assignment.
- Do not output SMT-LIB code.
""".strip()


def get_repair_system_prompt(request_type: ContentType) -> str:
    if request_type == ContentType.NATURAL_LANGUAGE:
        return SMT_REPAIR_FROM_TEXT_SYSTEM_PROMPT
    return SMT_REPAIR_FROM_SMT_SYSTEM_PROMPT


def build_repair_user_prompt(
    request_type: ContentType,
    source_input: str,
    current_output: str,
    validation_feedback: str,
    reference_smt: Optional[str] = None,
) -> str:
    if request_type == ContentType.NATURAL_LANGUAGE:
        return f"""
The current SMT-LIB output failed validation.
Repair it with the smallest necessary edits.

Original natural language specification:
{source_input}

Current SMT-LIB output:
{current_output}

Verifier, reflection, and validator feedback:
{validation_feedback}

Repair requirements:
- Keep the original intent of the natural language.
- Fix syntax, undeclared symbols, sort errors, malformed assertions, or solver issues.
- Apply the minimum repair consistent with the feedback.
- Return only corrected SMT-LIB code.
- Do not include markdown fences or explanations.
""".strip()

    reference_block = ""
    if reference_smt:
        reference_block = f"""
Reference SMT-LIB whose preservation objective must be respected:
{reference_smt}

""".strip() + "\n\n"

    return f"""
The current SMT-LIB output failed validation, changed solver behavior, or violated the required preservation objective.
Repair it with the smallest local edits.

Original SMT-LIB input:
{source_input}

{reference_block}Current SMT-LIB output:
{current_output}

Verifier, reflection, and validator feedback:
{validation_feedback}

Repair requirements:
- Preserve the intended semantics of the optimization task.
- If the reference script is SAT, preserve logical equivalence.
- If the reference script is UNSAT, preserve the UNSAT status while keeping the script compact.
- If a counterexample assignment is provided, make sure the repaired script agrees with the required preservation objective on that assignment.
- Prefer the narrowest patch that resolves the diagnosed issue.
- Fix syntax, declarations, sorts, malformed commands, solver-status regressions, or SAT-equivalence failures.
- Return only corrected SMT-LIB code.
- Do not include markdown fences or explanations.
""".strip()
