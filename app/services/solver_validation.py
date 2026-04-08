import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from app.core.config import Settings
from app.models.schemas import ValidationSummary


class Z3Validator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def validate(self, smt_code: str) -> ValidationSummary:
        python_result = self._validate_with_python_api(smt_code)
        if python_result is not None:
            return self._finalize(python_result)

        cli_result = self._validate_with_cli(smt_code)
        if cli_result is not None:
            return self._finalize(cli_result)

        return ValidationSummary(
            passed=False,
            syntax_valid=None,
            solver_available=False,
            solver_ran=False,
            solver_backend=None,
            solver_status=None,
            solver_time_ms=None,
            solvable=None,
            error_message=(
                "Z3 is not available. Install `z3-solver` or place `z3.exe` on PATH, "
                "or set Z3_CLI_PATH to the solver location."
            ),
        )

    def _validate_with_python_api(self, smt_code: str) -> Optional[ValidationSummary]:
        try:
            import z3  # type: ignore
        except ImportError:
            return None

        try:
            solver = z3.Solver()
            solver.from_string(smt_code)
            started_at = time.perf_counter()
            solver_status = str(solver.check())
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        except z3.Z3Exception as exc:
            return ValidationSummary(
                passed=False,
                syntax_valid=False,
                solver_available=True,
                solver_ran=False,
                solver_backend="python-z3",
                solver_status=None,
                solver_time_ms=None,
                solvable=None,
                error_message=str(exc).strip() or "Z3 rejected the SMT-LIB input.",
            )

        return ValidationSummary(
            passed=False,
            syntax_valid=True,
            solver_available=True,
            solver_ran=True,
            solver_backend="python-z3",
            solver_status=solver_status,
            solver_time_ms=round(elapsed_ms, 3),
            solvable=solver_status in {"sat", "unsat"},
            error_message=None,
        )

    def _validate_with_cli(self, smt_code: str) -> Optional[ValidationSummary]:
        cli_path = self._resolve_cli_path()
        if cli_path is None:
            return None

        temp_path = None  # type: Optional[Path]
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".smt2",
                delete=False,
            ) as handle:
                handle.write(smt_code)
                temp_path = Path(handle.name)

            started_at = time.perf_counter()
            completed = subprocess.run(
                [cli_path, "-smt2", str(temp_path)],
                capture_output=True,
                text=True,
                timeout=self._settings.z3_timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return ValidationSummary(
                passed=False,
                syntax_valid=True,
                solver_available=True,
                solver_ran=False,
                solver_backend="z3-cli",
                solver_status=None,
                solver_time_ms=None,
                solvable=None,
                error_message="Z3 CLI validation timed out.",
            )
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        solver_status = _extract_solver_status(stdout)

        if completed.returncode != 0:
            return ValidationSummary(
                passed=False,
                syntax_valid=False,
                solver_available=True,
                solver_ran=False,
                solver_backend="z3-cli",
                solver_status=solver_status,
                solver_time_ms=round(elapsed_ms, 3),
                solvable=solver_status in {"sat", "unsat"} if solver_status else None,
                error_message=stderr or stdout or "Z3 CLI returned a non-zero exit code.",
            )

        if solver_status is None:
            return ValidationSummary(
                passed=False,
                syntax_valid=True,
                solver_available=True,
                solver_ran=True,
                solver_backend="z3-cli",
                solver_status=None,
                solver_time_ms=round(elapsed_ms, 3),
                solvable=None,
                error_message=stderr or "No solver status was found in Z3 output.",
            )

        return ValidationSummary(
            passed=False,
            syntax_valid=True,
            solver_available=True,
            solver_ran=True,
            solver_backend="z3-cli",
            solver_status=solver_status,
            solver_time_ms=round(elapsed_ms, 3),
            solvable=solver_status in {"sat", "unsat"},
            error_message=None,
        )

    def _resolve_cli_path(self) -> Optional[str]:
        configured = (self._settings.z3_cli_path or "").strip()
        if not configured:
            return None

        if Path(configured).exists():
            return configured

        return shutil.which(configured)

    def _finalize(self, result: ValidationSummary) -> ValidationSummary:
        if not result.solver_available:
            return result

        if result.syntax_valid is False:
            return result

        if not result.solver_ran:
            return result

        if result.solver_status in {"sat", "unsat"}:
            result.passed = True
            return result

        if result.solver_status == "unknown" and self._settings.workflow_accept_unknown:
            result.passed = True
            return result

        if not result.error_message:
            result.error_message = (
                "Z3 returned solver status `{}` which is not accepted by the workflow.".format(
                    result.solver_status
                )
            )

        return result


def _extract_solver_status(output: str) -> Optional[str]:
    for line in output.splitlines():
        normalized = line.strip().lower()
        if normalized in {"sat", "unsat", "unknown"}:
            return normalized
    return None
