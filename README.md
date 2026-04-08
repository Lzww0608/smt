# SMT Backend Service

A Python backend scaffold for a Vue frontend.

Current capabilities:

1. Accept `POST` requests from the frontend.
2. Distinguish natural language input from SMT-LIB input.
3. Use an LLM to generate SMT-LIB from natural language.
4. Use an LLM to optimize SMT-LIB.
5. Run a validation-and-repair workflow with Z3.
6. Run a semantic equivalence check for SAT optimization results.
7. Preserve UNSAT optimization results through a status-preserving safe-deletion workflow.
8. Use a multi-role LLM workflow with verifier, reflection, and repair agents.
9. Feed counterexample assignments from Z3 back into the repair loop when SAT equivalence fails.
10. Use Volcengine Ark Coding OpenAI-compatible API as the default live provider.
11. Run an MCTS-CORF-style deterministic optimizer for SMT redundancy reduction.
12. Use UNSAT core guidance, reward shaping, dynamic termination, and core projection for the second POST path.

## API

- `GET /health`
- `POST /api/v1/smt/transform`

Example response fields:

- `result`: final SMT-LIB output.
- `validation`: final Z3 validation report.
- `equivalence`: semantic equivalence report for SAT optimization requests.
- `optimization_summary`: deterministic MCTS-CORF-style search summary for SMT optimization requests.
- `workflow`: retry and repair metadata, including verifier/reflection/repair run counts.
- `agent_trace`: last verifier and reflection reports used by the workflow.
- `source_validation`: original SMT-LIB validation result for optimization requests.

## Workflow

For natural language requests:

1. Ask the generation agent to produce SMT-LIB.
2. Validate the candidate with Z3.
3. If validation fails, ask the verifier agent to diagnose the issue.
4. Ask the reflection agent to propose the smallest repair strategy.
5. Ask the repair agent to patch the SMT-LIB.
6. Retry until the candidate passes validation or `WORKFLOW_MAX_ATTEMPTS` is reached.

For SMT-LIB optimization requests:

1. Validate the source SMT-LIB first.
2. If the source is invalid, repair it through the same verifier-reflection-repair loop.
3. Run deterministic explicit-redundancy cleanup.
4. Run an MCTS-CORF-style safe-deletion search over assertions.
5. If the source is SAT, only keep deletions that preserve logical equivalence.
6. If the source is UNSAT, only keep deletions that preserve the UNSAT solver status.
7. Use UNSAT core guidance to prioritize non-core deletions during UNSAT search.
8. Apply UNSAT core projection to release whole batches of non-core assertions and move the candidate closer to a smaller unsatisfied subset.
9. Stop the search dynamically based on frontier exhaustion, stagnation, time budget, or iteration budget.
10. Optionally send the deterministic best candidate to the LLM for conservative post-optimization.
11. Validate the optimized result with Z3.
12. For SAT scripts, run semantic equivalence checking and counterexample-guided repair when needed.
13. For UNSAT scripts, enforce UNSAT preservation rather than logical equivalence.

## Provider Defaults

The project now defaults to the live Volcengine Ark Coding OpenAI-compatible endpoint.

- `LLM_PROVIDER=openai_compatible`
- `LLM_API_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3`
- `LLM_MODEL=doubao-seed-2.0-code`

The real API key is expected in local `.env`.

## Install

This project targets Python 3.7+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```powershell
.\start_backend.ps1
```

## Optimizer Settings

The SMT optimization path now exposes additional search settings.

- `OPTIMIZER_MAX_DEPTH=8`
- `OPTIMIZER_MAX_ITERATIONS=24`
- `OPTIMIZER_MAX_CHILDREN=8`
- `OPTIMIZER_EXPLORATION_WEIGHT=0.3`
- `OPTIMIZER_ENABLE_LLM_POSTPASS=true`
- `OPTIMIZER_PATIENCE=6`
- `OPTIMIZER_MIN_REWARD_GAIN=0.001`
- `OPTIMIZER_TIME_BUDGET_MS=0`
- `OPTIMIZER_ENABLE_UNSAT_CORE_GUIDANCE=true`
- `OPTIMIZER_ENABLE_UNSAT_CORE_PROJECTION=true`
- `OPTIMIZER_UNSAT_CORE_SAMPLES=3`
- `OPTIMIZER_UNSAT_CORE_SAMPLE_TIMEOUT_MS=120`
- `OPTIMIZER_UNSAT_CORE_SAMPLE_ASSERTION_LIMIT=64`

UNSAT core guidance now uses bounded multi-core sampling:
- up to `OPTIMIZER_UNSAT_CORE_SAMPLES` solver calls per state,
- deterministic sample first, then shuffled samples,
- early stop when consecutive samples converge to one identical core,
- if the assertion count is large (`OPTIMIZER_UNSAT_CORE_SAMPLE_ASSERTION_LIMIT`), it uses a single sample to bound overhead,
- each sample uses `OPTIMIZER_UNSAT_CORE_SAMPLE_TIMEOUT_MS` timeout in ms.

## Local Regression Tests

Use the built-in unittest suite to exercise the second POST path on one SAT sample and one UNSAT sample.

```powershell
python -m unittest discover -s tests -v
```

Regression fixtures are stored in:

- [tests/fixtures/sat_redundant.smt2](f:/Code/Project/smt/tests/fixtures/sat_redundant.smt2)
- [tests/fixtures/unsat_redundant.smt2](f:/Code/Project/smt/tests/fixtures/unsat_redundant.smt2)
- [tests/test_smt_optimization_regression.py](f:/Code/Project/smt/tests/test_smt_optimization_regression.py)

## Z3 Setup

Preferred option:

```powershell
pip install z3-solver
```

Alternative option:

- Install `z3.exe` manually.
- Put it on `PATH`, or set `Z3_CLI_PATH` in `.env`.

Note:

- Syntax and solver-status validation can fall back to `z3.exe`.
- SAT semantic equivalence checking, tautology detection, UNSAT core guidance, and MCTS-CORF safe-deletion search require the Python package `z3-solver`.

## Key Files

- [app/core/config.py](f:/Code/Project/smt/app/core/config.py)
- [app/services/workflow.py](f:/Code/Project/smt/app/services/workflow.py)
- [app/services/redundancy_optimizer.py](f:/Code/Project/smt/app/services/redundancy_optimizer.py)
- [app/services/equivalence.py](f:/Code/Project/smt/app/services/equivalence.py)
- [app/services/solver_validation.py](f:/Code/Project/smt/app/services/solver_validation.py)
- [app/services/prompts.py](f:/Code/Project/smt/app/services/prompts.py)
- [app/services/llm/openai_compatible_provider.py](f:/Code/Project/smt/app/services/llm/openai_compatible_provider.py)
