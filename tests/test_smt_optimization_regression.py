import asyncio
import os
import re
import unittest

IMPORT_ERROR = None


try:
    from app.core.config import Settings
    from app.models.schemas import ContentType, TransformRequest
    from app.services.smt_service import SMTService
except Exception as exc:  # pragma: no cover
    IMPORT_ERROR = exc
    Settings = None
    ContentType = None
    TransformRequest = None
    SMTService = None


def _has_z3():
    try:
        import z3  # type: ignore
    except ImportError:
        return False
    return True


def _read_fixture(name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "fixtures", name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _assert_count(script):
    return len(re.findall(r"\(assert\b", script))


DEPENDENCY_READY = IMPORT_ERROR is None and _has_z3()
SKIP_REASON = (
    "runtime dependencies unavailable: {}".format(IMPORT_ERROR)
    if IMPORT_ERROR is not None
    else "z3-solver is not installed"
)


@unittest.skipUnless(DEPENDENCY_READY, SKIP_REASON)
class SMTOptimizationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            llm_provider="mock",
            llm_api_key="",
            optimizer_enable_llm_postpass=False,
            optimizer_max_iterations=12,
            optimizer_patience=4,
            optimizer_max_depth=6,
        )
        self.service = SMTService(settings=self.settings)

    def _run(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def test_sat_optimization_regression(self):
        source_script = _read_fixture("sat_redundant.smt2")
        response = self._run(
            self.service.transform(
                TransformRequest(
                    content=source_script,
                    content_type=ContentType.SMT_CODE,
                )
            )
        )

        self.assertTrue(response.success)
        self.assertEqual(response.source_validation.solver_status, "sat")
        self.assertEqual(response.validation.solver_status, "sat")
        self.assertIsNotNone(response.equivalence)
        self.assertTrue(response.equivalence.equivalent)
        self.assertIsNotNone(response.optimization_summary)
        self.assertTrue(response.optimization_summary.search_used)
        self.assertGreater(_assert_count(source_script), _assert_count(response.result))
        self.assertIn(
            response.optimization_summary.termination_reason,
            {
                "frontier_exhausted",
                "stagnation_limit",
                "max_iterations_reached",
                "time_budget_reached",
            },
        )

    def test_unsat_optimization_regression(self):
        source_script = _read_fixture("unsat_redundant.smt2")
        response = self._run(
            self.service.transform(
                TransformRequest(
                    content=source_script,
                    content_type=ContentType.SMT_CODE,
                )
            )
        )

        self.assertTrue(response.success)
        self.assertEqual(response.source_validation.solver_status, "unsat")
        self.assertEqual(response.validation.solver_status, "unsat")
        self.assertIsNone(response.equivalence)
        self.assertIsNotNone(response.optimization_summary)
        self.assertTrue(response.optimization_summary.search_used)
        self.assertTrue(response.optimization_summary.unsat_core_available)
        self.assertIsNotNone(response.optimization_summary.reference_unsat_core_size)
        self.assertIsNotNone(response.optimization_summary.final_unsat_core_size)
        self.assertGreaterEqual(response.optimization_summary.unsat_core_sample_count, 1)
        self.assertGreaterEqual(response.optimization_summary.unsat_core_distinct_count, 1)
        self.assertIsNotNone(response.optimization_summary.stable_unsat_core_size)
        self.assertIsNotNone(response.optimization_summary.union_unsat_core_size)
        self.assertGreaterEqual(
            response.optimization_summary.union_unsat_core_size,
            response.optimization_summary.stable_unsat_core_size,
        )
        self.assertGreater(_assert_count(source_script), _assert_count(response.result))
        self.assertGreaterEqual(response.optimization_summary.core_guided_actions, 1)
        self.assertTrue(response.optimization_summary.core_projection_applied)
        self.assertGreaterEqual(response.optimization_summary.core_projection_reductions, 1)
        self.assertGreaterEqual(response.optimization_summary.protected_core_skips, 1)


if __name__ == "__main__":
    unittest.main()
