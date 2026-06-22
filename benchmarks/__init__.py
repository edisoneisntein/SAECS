from __future__ import annotations
import os
import sys
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class BenchmarkResult:
    name: str
    domain: str
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BenchmarkProblem:
    name: str
    domain: str
    description: str
    ground_truth: dict[str, Any]
    expected_metrics: dict[str, float]
    acceptable_solutions: list[str]
    known_bad_solutions: list[str]
    setup_fn: Callable | None = None
    teardown_fn: Callable | None = None


class SAECSEvaluationSuite:
    def __init__(self, results_dir: str = "benchmarks/results"):
        self.results_dir = results_dir
        self.results: list[BenchmarkResult] = []
        os.makedirs(results_dir, exist_ok=True)

    def register_problem(self, problem: BenchmarkProblem) -> None:
        pass

    def run_benchmark(
        self,
        name: str,
        domain: str,
        run_fn: Callable[[], dict],
        expected_metrics: dict[str, float] | None = None,
        ground_truth: dict | None = None,
    ) -> BenchmarkResult:
        start = time.time()
        steps_log = []
        error = None
        passed = False
        metrics = {}

        try:
            result = run_fn()
            metrics = result.get("metrics", result)
            steps_log = result.get("steps", [])
            if expected_metrics:
                passed = all(
                    metrics.get(k, 0) >= v
                    for k, v in expected_metrics.items()
                )
            else:
                passed = result.get("success", False)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            traceback.print_exc()

        duration = (time.time() - start) * 1000

        br = BenchmarkResult(
            name=name,
            domain=domain,
            passed=passed,
            metrics=metrics,
            steps=steps_log,
            error=error,
            duration_ms=round(duration, 1),
        )
        self.results.append(br)
        self._save_result(br)
        return br

    def run_benchmark_suite(self, benchmarks: list[tuple]) -> dict:
        results = {}
        for name, domain, run_fn, expected in benchmarks:
            br = self.run_benchmark(name, domain, run_fn, expected)
            results[name] = {
                "passed": br.passed,
                "metrics": br.metrics,
                "duration_ms": br.duration_ms,
                "error": br.error,
            }
        summary = self.summarize(results)
        return {"results": results, "summary": summary}

    def summarize(self, results: dict) -> dict:
        total = len(results)
        passed = sum(1 for r in results.values() if r["passed"])
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": f"{passed / max(total, 1) * 100:.0f}%",
            "avg_duration_ms": round(
                sum(r["duration_ms"] for r in results.values()) / max(total, 1), 1
            ),
        }

    def _save_result(self, result: BenchmarkResult) -> None:
        path = os.path.join(
            self.results_dir,
            f"{result.domain}_{result.name}_{int(time.time())}.json",
        )
        with open(path, "w") as f:
            json.dump({
                "name": result.name,
                "domain": result.domain,
                "passed": result.passed,
                "metrics": result.metrics,
                "steps": result.steps,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "timestamp": result.timestamp,
            }, f, indent=2)

    def print_report(self) -> None:
        print("=" * 72)
        print("SAECS Evaluation Suite - Report")
        print("=" * 72)
        print()
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.domain}/{r.name}")
            print(f"         Metrics: {r.metrics}")
            print(f"         Duration: {r.duration_ms}ms")
            if r.error:
                print(f"         Error: {r.error}")
            print()
        summary = self.summarize({
            r.name: {"passed": r.passed, "duration_ms": r.duration_ms}
            for r in self.results
        })
        print("-" * 72)
        print(f"  Total: {summary['total']}  |  "
              f"Passed: {summary['passed']}  |  "
              f"Failed: {summary['failed']}  |  "
              f"Pass rate: {summary['pass_rate']}  |  "
              f"Avg: {summary['avg_duration_ms']}ms")
        print("=" * 72)


class BenchmarkBuilder:
    @staticmethod
    def detect_bottleneck(
        engine,
        software_domain,
        project_path: str,
    ) -> dict:
        steps = []
        engine.cycle_count = 0

        t0 = time.time()
        engine.run_cycle(domain_fn=lambda: software_domain.observe())
        steps.append({"step": "observe", "result": "observation_complete"})

        history = engine.bus.get_history(limit=50)
        decision_events = [
            e for e in history
            if e.type.value in ("decision_made", "inaction_decided")
        ]

        steps.append({
            "step": "decide",
            "result": decision_events[-1].data if decision_events else "no_decision",
        })

        causal_summary = engine.causal.summary()
        steps.append({
            "step": "causal_analysis",
            "result": causal_summary,
        })

        utility_params = engine.utility.parameters
        strategy_perf = engine.director.selector.summary()

        duration_ms = (time.time() - t0) * 1000

        return {
            "success": True,
            "metrics": {
                "causal_nodes": causal_summary.get("nodes", 0),
                "causal_edges": causal_summary.get("edges", 0),
                "decisions_made": len(decision_events),
                "budget_used": engine.director.cognitive_spent,
            },
            "steps": steps,
            "duration_ms": round(duration_ms, 1),
        }
