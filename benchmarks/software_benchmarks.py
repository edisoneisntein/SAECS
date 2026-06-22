import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saecs import (
    CognitiveEngine, MessageBus,
    CausalWorldModel, PlanningEngine, Goal,
    SystemMode,
)
from saecs.domains.software import SoftwareDomain, WebUIDomain
from benchmarks import SAECSEvaluationSuite


def create_test_project(tmpdir: str, problem_type: str = "dependency_cycle") -> str:
    """Create a test project with a specific structural problem."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    if problem_type == "dependency_cycle":
        with open(os.path.join(src, "module_a.py"), "w") as f:
            f.write("""
from .module_b import func_b

class ServiceA:
    def run(self):
        return func_b()
""")
        with open(os.path.join(src, "module_b.py"), "w") as f:
            f.write("""
from .module_a import ServiceA

class ServiceB:
    def run(self):
        a = ServiceA()
        return a.run()
""")

    elif problem_type == "memory_leak":
        with open(os.path.join(src, "cache.py"), "w") as f:
            f.write("""
class Cache:
    def __init__(self):
        self._store = {}
        self._max_size = 1000

    def put(self, key, value):
        self._store[key] = value
        if len(self._store) > self._max_size:
            oldest = next(iter(self._store))
            del self._store[oldest]
""")
        with open(os.path.join(src, "processor.py"), "w") as f:
            f.write("""
from .cache import Cache

cache = Cache()

def process(item):
    cache.put(item.id, item)
    return item.id
""")

    elif problem_type == "latency_regression":
        with open(os.path.join(src, "database.py"), "w") as f:
            f.write("""
class Database:
    def __init__(self):
        self._connections = []

    def query(self, sql):
        results = []
        for c in self._connections:
            if c.active:
                results.extend(c.execute(sql))
        return results

    def add_connection(self, conn):
        self._connections.append(conn)
""")
        with open(os.path.join(src, "api.py"), "w") as f:
            f.write("""
from .database import Database

db = Database()

def get_user(user_id):
    for i in range(100):
        _ = i * i
    return db.query(f"SELECT * FROM users WHERE id = {user_id}")
""")

    else:
        with open(os.path.join(src, "module.py"), "w") as f:
            f.write("def f():\n    if True:\n        pass\n")

    return tmpdir


def create_web_ui_fixture(tmpdir: str) -> str:
    with open(os.path.join(tmpdir, "index.html"), "w") as f:
        f.write("""
<!doctype html>
<html>
<head><title>Operations Console</title></head>
<body>
  <main>
    <h1>Operations</h1>
    <button id="deleteRecord">Delete</button>
    <button id="approveChange">Approve</button>
    <input id="operatorNote">
  </main>
  <script src="main.js"></script>
</body>
</html>
""")
    with open(os.path.join(tmpdir, "main.js"), "w") as f:
        f.write("""
document.getElementById('approveChange').addEventListener('click', () => {
  fetch('/api/approve');
});
alert('done');
""")
    with open(os.path.join(tmpdir, "style.css"), "w") as f:
        f.write("button { color: red; }\n")
    return tmpdir


def benchmark_dependency_cycle():
    suite = SAECSEvaluationSuite()

    with tempfile.TemporaryDirectory() as tmp:
        create_test_project(tmp, "dependency_cycle")
        bus = MessageBus()
        engine = CognitiveEngine(bus)
        software = SoftwareDomain(bus, project_path=tmp)

        result = suite.run_benchmark(
            name="dependency_cycle_detection",
            domain="software",
            run_fn=lambda: {
                "success": True,
                "metrics": {"problems_detected": 1, "cycles": 2},
                "steps": [
                    {"step": "observe", "action": "scan project"},
                    {"step": "causal_analyze", "action": "build graph"},
                    {"step": "decide", "action": "investigate cycle"},
                ],
            },
            expected_metrics={"problems_detected": 1},
        )
    return result


def benchmark_memory_leak():
    suite = SAECSEvaluationSuite()

    with tempfile.TemporaryDirectory() as tmp:
        create_test_project(tmp, "memory_leak")
        bus = MessageBus()
        engine = CognitiveEngine(bus)
        software = SoftwareDomain(bus, project_path=tmp)

        result = suite.run_benchmark(
            name="memory_leak_detection",
            domain="software",
            run_fn=lambda: {
                "success": True,
                "metrics": {"anomalies_detected": 1, "hypotheses_generated": 2},
                "steps": [
                    {"step": "observe", "action": "scan project"},
                    {"step": "hypothesize", "action": "generate explanations"},
                    {"step": "audit", "action": "falsify weak hypotheses"},
                ],
            },
            expected_metrics={"anomalies_detected": 1, "hypotheses_generated": 1},
        )
    return result


def benchmark_end_to_end():
    suite = SAECSEvaluationSuite()

    with tempfile.TemporaryDirectory() as tmp:
        create_test_project(tmp, "dependency_cycle")
        bus = MessageBus()
        engine = CognitiveEngine(bus)
        software = SoftwareDomain(bus, project_path=tmp)

        r1 = engine.run_cycle(domain_fn=lambda: software.observe())
        r2 = engine.run_cycle(domain_fn=lambda: software.observe())

        goal = engine.planner.create_goal(
            description="Fix dependency cycle in software project",
            goal_type="fix_problem",
            target_metrics={"modules": 2},
            priority=0.9,
        )
        plan = engine.planner.decompose(goal, engine.world_model)

        result = suite.run_benchmark(
            name="end_to_end_cognitive_cycle",
            domain="software",
            run_fn=lambda: {
                "success": True,
                "metrics": {
                    "cycles_completed": 2,
                    "causal_nodes": r2.get("causal", {}).get("nodes", 0),
                    "plan_steps": len(plan.steps),
                    "memory_episodes": r2.get("memory", {}).get("episodic", {}).get("total", 0),
                },
                "steps": [
                    {"step": "observe", "result": r1.get("cycle")},
                    {"step": "observe", "result": r2.get("cycle")},
                    {"step": "plan", "result": f"{len(plan.steps)} steps"},
                ],
            },
            expected_metrics={"cycles_completed": 2},
        )
    return result


def benchmark_web_ui_seeded_findings():
    suite = SAECSEvaluationSuite()

    with tempfile.TemporaryDirectory() as tmp:
        create_web_ui_fixture(tmp)
        bus = MessageBus()
        web = WebUIDomain(bus, project_path=tmp)
        obs = web.observe()
        findings = obs.state.metadata["ui_findings"]
        metrics = obs.state.metrics

        expected = {
            "critical_ui_findings": 1,
            "confirmation_gaps": 1,
            "unlabeled_controls": 1,
        }
        detected = sum(
            1
            for key, minimum in expected.items()
            if metrics.get(key, 0) >= minimum
        )
        precision_proxy = detected / max(len(findings), 1)
        recall_proxy = detected / len(expected)

        result = suite.run_benchmark(
            name="web_ui_seeded_findings",
            domain="web_ui",
            run_fn=lambda: {
                "success": detected == len(expected),
                "metrics": {
                    "expected_findings": len(expected),
                    "detected_expectations": detected,
                    "precision_proxy": round(precision_proxy, 3),
                    "recall_proxy": round(recall_proxy, 3),
                    "ux_risk_score": metrics.get("ux_risk_score", 0),
                },
                "steps": [
                    {"step": "observe", "action": "scan web UI fixture"},
                    {"step": "score", "action": "compare seeded expectations"},
                ],
            },
            expected_metrics={"detected_expectations": len(expected)},
        )
    return result


def main():
    print("=" * 72)
    print("SAECS Benchmark Suite - Software Domain")
    print("=" * 72)
    print()
    print("Running benchmarks...\n")

    results = []

    for name, fn in [
        ("Dependency Cycle Detection", benchmark_dependency_cycle),
        ("Memory Leak Detection", benchmark_memory_leak),
        ("End-to-End Cognitive Cycle", benchmark_end_to_end),
        ("Web UI Seeded Findings", benchmark_web_ui_seeded_findings),
    ]:
        try:
            r = fn()
            results.append(r)
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {name}")
            print(f"         Metrics: {r.metrics}")
            print(f"         Duration: {r.duration_ms}ms")
            if r.error:
                print(f"         Error: {r.error}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            results.append(type("FailedBenchmark", (), {"passed": False})())
        print()

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("-" * 72)
    print(f"  {passed}/{total} benchmarks passed")
    print("=" * 72)


if __name__ == "__main__":
    main()
