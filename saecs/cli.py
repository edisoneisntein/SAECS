import argparse
import json
import os
import sys

from . import CognitiveEngine, MessageBus, Hypothesis, __version__
from .domains.software import CodeDomain, WebUIDomain, SoftwareDomain
from .core.adapter import DomainRegistry


_DOMAIN_MAP = {
    "software": SoftwareDomain,
    "code": CodeDomain,
    "web_ui": WebUIDomain,
}

_METRIC_KEYS = [
    "modules", "web_files", "html_files", "css_files", "js_files",
    "lines", "avg_complexity",
    "interactive_controls", "unlabeled_controls", "danger_controls",
    "confirmation_gaps", "responsive_signals", "focus_styles",
    "error_states", "loading_states",
    "accessibility_score", "ux_risk_score",
    "critical_ui_findings", "high_ui_findings", "ui_findings",
]


def _resolve_project(path: str) -> str:
    resolved = os.path.abspath(path)
    if not os.path.isdir(resolved):
        print(f"Error: '{resolved}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    return resolved


def _build_engine(project_path: str, domain_name: str, memory_path: str | None = None):
    bus = MessageBus()
    mp = memory_path or os.path.join(project_path, ".saecs")
    engine = CognitiveEngine(bus, memory_path=mp)
    domain_cls = _DOMAIN_MAP.get(domain_name)
    if domain_cls is None:
        print(f"Error: unknown domain '{domain_name}'. Available: {', '.join(_DOMAIN_MAP)}", file=sys.stderr)
        sys.exit(1)
    domain = domain_cls(bus, project_path=project_path)
    engine.auditor.register_audit_fn(domain.audit_hypothesis)
    engine.executor.register_execute_fn(domain.execute_fn)
    return engine, domain


def _print_metrics(metrics: dict, keys: list[str] | None = None) -> None:
    for key in keys or metrics:
        if key in metrics:
            print(f"  {key}: {metrics[key]}")


def _print_findings(findings: list[dict]) -> None:
    if not findings:
        print("  No findings.")
        return
    for f in findings:
        severity = f.get("severity", "unknown").upper()
        path = f.get("path", "")
        problem = f.get("problem", "")
        impact = f.get("impact", "")
        print(f"  [{severity}] {path}: {problem}")
        if impact:
            print(f"         {impact}")


def _format_json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def cmd_observe(args) -> None:
    project = _resolve_project(args.project)
    bus = MessageBus()
    domain_cls = _DOMAIN_MAP.get(args.domain)
    if domain_cls is None:
        print(f"Error: unknown domain '{args.domain}'.", file=sys.stderr)
        sys.exit(1)
    domain = domain_cls(bus, project_path=project)
    obs = domain.observe()

    if args.json:
        output = {
            "domain": obs.domain_id,
            "uncertainty": obs.uncertainty,
            "changes_detected": obs.changes_detected,
            "metrics": obs.state.metrics,
            "findings": obs.state.metadata.get("ui_findings", []),
        }
        print(_format_json(output))
        return

    print(f"Domain: {obs.domain_id}")
    print(f"Uncertainty: {obs.uncertainty:.2f}")
    print(f"Changes detected: {obs.changes_detected}")
    print()
    print("Metrics")
    _print_metrics(obs.state.metrics, _METRIC_KEYS)
    print()
    print("Findings")
    _print_findings(obs.state.metadata.get("ui_findings", []))


def cmd_cycle(args) -> None:
    project = _resolve_project(args.project)
    engine, domain = _build_engine(project, args.domain)
    results = []
    for i in range(args.cycles):
        result = engine.run_cycle(domain_fn=domain.observe)
        results.append(result)

    if args.json:
        print(_format_json(results))
        return

    for result in results:
        print(f"Cycle {result.get('cycle', '?')}")
        print(f"  Mode: {result.get('mode')}")
        print(f"  Events: {result.get('events')}")
        director = result.get("director", {})
        print(f"  Budget used: {director.get('budget_used', 0):.0f}")
        print(f"  Strategy: {director.get('strategy_selector', {}).get('current', 'none')}")
        causal = result.get("causal", {})
        print(f"  Causal nodes: {causal.get('nodes', 0)}")
        mem = result.get("memory", {})
        print(f"  Episodic memory: {mem.get('episodic', {}).get('total', 0)} episodes")
        gov = result.get("governance", {})
        print(f"  Governance mode: {gov.get('mode', 'normal')}")


def cmd_audit(args) -> None:
    project = _resolve_project(args.project)
    bus = MessageBus()
    domain_cls = _DOMAIN_MAP.get(args.domain)
    if domain_cls is None:
        print(f"Error: unknown domain '{args.domain}'.", file=sys.stderr)
        sys.exit(1)
    domain = domain_cls(bus, project_path=project)

    obs = domain.observe()
    metrics = obs.state.metrics
    findings = obs.state.metadata.get("ui_findings", [])

    if args.hypothesis_id:
        h = Hypothesis(
            id=args.hypothesis_id,
            description=args.description or "Audit-triggered hypothesis",
            predicted_effect=args.predicted_effect or "Reduce detected risk",
            evidence=[f"audit_cli:{k}={v}" for k, v in metrics.items() if v],
            confidence=0.5,
            domain_data={"domain": args.domain, "measurable": True},
        )
        if args.target_metrics:
            for pair in args.target_metrics.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    try:
                        h.target_metrics[k.strip()] = float(v.strip())
                    except ValueError:
                        pass
        report = domain.audit_hypothesis(h)
        if args.json:
            print(_format_json({
                "hypothesis_id": report.hypothesis_id,
                "falsified": report.falsified,
                "falsification_reason": report.falsification_reason,
                "tests_passed": report.tests_passed,
                "tests_failed": report.tests_failed,
                "confidence_after": report.confidence_after,
                "attack_vectors": report.attack_vectors,
            }))
            return
        print(f"Hypothesis: {report.hypothesis_id}")
        print(f"Falsified: {report.falsified}")
        if report.falsification_reason:
            print(f"Reason: {report.falsification_reason}")
        print(f"Tests passed: {report.tests_passed}")
        print(f"Tests failed: {report.tests_failed}")
        print(f"Confidence after: {report.confidence_after:.2f}")
        print(f"Attack vectors: {', '.join(report.attack_vectors) if report.attack_vectors else 'none'}")
        return

    if args.json:
        print(_format_json({"metrics": metrics, "findings": findings}))
        return

    print("SAECS Audit")
    print("=" * 60)
    print(f"Project: {project}")
    print(f"Domain: {args.domain}")
    print()
    print("Metrics")
    _print_metrics(metrics, _METRIC_KEYS)
    print()
    if findings:
        print("Findings")
        _print_findings(findings)
        print()
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")
        print(f"Summary: {critical} critical, {high} high, {len(findings)} total")
    else:
        print("Findings: No issues detected.")


def cmd_health(args) -> None:
    project = _resolve_project(args.project)
    bus = MessageBus()
    domain_cls = _DOMAIN_MAP.get(args.domain)
    if domain_cls is None:
        print(f"Error: unknown domain '{args.domain}'.", file=sys.stderr)
        sys.exit(1)
    domain = domain_cls(bus, project_path=project)
    health = domain.health()

    if args.json:
        print(_format_json({"status": health.status, "metrics": health.metrics, "issues": health.issues}))
        return

    print(f"Domain: {domain.domain}")
    print(f"Status: {health.status}")
    if health.metrics:
        print()
        print("Metrics")
        _print_metrics(health.metrics, _METRIC_KEYS)
    if health.issues:
        print()
        print("Issues")
        for issue in health.issues:
            print(f"  - {issue}")


def cmd_simulate(args) -> None:
    project = _resolve_project(args.project)
    engine, domain = _build_engine(project, args.domain)
    engine.run_cycle(domain_fn=domain.observe)

    if not args.action:
        print("Error: --action is required for simulate.", file=sys.stderr)
        sys.exit(1)

    action = {"action": args.action, "target": args.target or ""}
    if args.delta is not None:
        action["delta"] = args.delta

    sim = engine.simulate_action(action)

    if args.json:
        print(_format_json(sim))
        return

    print("Simulation Result")
    print(f"  Action: {sim['action']}")
    print(f"  Reward: {sim['reward']:.3f}")
    print(f"  Risk: {sim['risk']:.3f}")
    print(f"  Confidence: {sim['confidence']:.3f}")
    print(f"  Success probability: {sim['success_probability']:.3f}")
    if sim.get("side_effects"):
        print(f"  Side effects: {sim['side_effects']}")


def cmd_status(args) -> None:
    project = _resolve_project(args.project)
    engine, domain = _build_engine(project, args.domain)
    summary = engine.summary()

    if args.json:
        print(_format_json(summary))
        return

    print(f"SAECS v{__version__}")
    print(f"  Cycles completed: {summary['cycle_count']}")
    print(f"  Mode: {summary['mode']}")
    gov = summary.get("governance", {})
    print(f"  Governance mode: {gov.get('mode', 'normal')}")
    print(f"  Governance parameters: {len(gov.get('parameters', {}))}")
    print(f"  Circuit breakers: {len(gov.get('circuit_breakers', []))}")
    director = summary.get("director", {})
    print(f"  Budget used: {director.get('budget_used', 0)}")
    causal = summary.get("causal", {})
    print(f"  Causal nodes: {causal.get('nodes', 0)}")
    mem = summary.get("memory", {})
    print(f"  Episodic: {mem.get('episodic', {}).get('total', 0)} episodes")
    print(f"  Semantic: {mem.get('semantic', {}).get('patterns', 0)} patterns")
    print(f"  Strategic: {mem.get('strategic', {}).get('rules', 0)} rules")
    cal = summary.get("calibration", {})
    print(f"  Calibration ECE: {cal.get('ece', 0):.4f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saecs",
        description="SAECS - Sistema Autonomo de Evolucion Continua de Software",
    )
    parser.add_argument("--version", action="version", version=f"SAECS v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_obs = sub.add_parser("observe", help="Observe a project and report metrics + findings")
    p_obs.add_argument("project", help="Path to the project to observe")
    p_obs.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_obs.add_argument("--json", action="store_true", help="Output as JSON")

    p_cycle = sub.add_parser("cycle", help="Run one or more cognitive cycles")
    p_cycle.add_argument("project", help="Path to the project")
    p_cycle.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_cycle.add_argument("--cycles", type=int, default=1, help="Number of cycles to run")
    p_cycle.add_argument("--json", action="store_true", help="Output as JSON")

    p_audit = sub.add_parser("audit", help="Audit a project for UI/UX and code risks")
    p_audit.add_argument("project", help="Path to the project")
    p_audit.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_audit.add_argument("--hypothesis-id", help="Test a specific hypothesis by ID")
    p_audit.add_argument("--description", help="Hypothesis description")
    p_audit.add_argument("--predicted-effect", help="Hypothesis predicted effect")
    p_audit.add_argument("--target-metrics", help="Comma-separated key=value target metrics (e.g. ux_risk_score=0,accessibility_score=1)")
    p_audit.add_argument("--json", action="store_true", help="Output as JSON")

    p_health = sub.add_parser("health", help="Check domain health status")
    p_health.add_argument("project", help="Path to the project")
    p_health.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_health.add_argument("--json", action="store_true", help="Output as JSON")

    p_sim = sub.add_parser("simulate", help="Simulate an action and predict outcome")
    p_sim.add_argument("project", help="Path to the project")
    p_sim.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_sim.add_argument("--action", required=True, help="Action to simulate")
    p_sim.add_argument("--target", default="", help="Target variable for the action")
    p_sim.add_argument("--delta", type=float, help="Numeric delta for the action")
    p_sim.add_argument("--json", action="store_true", help="Output as JSON")

    p_status = sub.add_parser("status", help="Show engine status and memory summary")
    p_status.add_argument("project", help="Path to the project")
    p_status.add_argument("--domain", default="software", choices=list(_DOMAIN_MAP), help="Domain adapter to use")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "observe": cmd_observe,
        "cycle": cmd_cycle,
        "audit": cmd_audit,
        "health": cmd_health,
        "simulate": cmd_simulate,
        "status": cmd_status,
    }

    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 1

    try:
        fn(args)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
