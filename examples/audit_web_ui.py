import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saecs import CognitiveEngine, MessageBus
from saecs.domains.software import WebUIDomain


def main():
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    project_path = os.path.abspath(project_path)

    bus = MessageBus()
    engine = CognitiveEngine(bus)
    web_ui = WebUIDomain(bus, project_path=project_path)
    engine.auditor.register_audit_fn(web_ui.audit_hypothesis)

    observation = web_ui.observe()
    metrics = observation.state.metrics
    findings = observation.state.metadata.get("ui_findings", [])

    print("=" * 72)
    print("SAECS UI/UX Audit")
    print("=" * 72)
    print(f"Project: {project_path}")
    print()
    print("Metrics")
    for key in (
        "web_files",
        "html_files",
        "css_files",
        "js_files",
        "interactive_controls",
        "unlabeled_controls",
        "danger_controls",
        "confirmation_gaps",
        "responsive_signals",
        "focus_styles",
        "error_states",
        "loading_states",
        "accessibility_score",
        "ux_risk_score",
        "critical_ui_findings",
        "high_ui_findings",
    ):
        print(f"  {key}: {metrics.get(key, 0)}")

    print()
    print("Findings")
    if not findings:
        print("  No UI/UX findings detected by static audit.")
    for finding in findings:
        print(
            f"  [{finding.get('severity', 'unknown').upper()}] "
            f"{finding.get('path')}: {finding.get('problem')}"
        )
        print(f"    Impact: {finding.get('impact')}")

    print()
    cycle = engine.run_cycle(domain_fn=web_ui.observe)
    print("Cognitive Cycle")
    print(f"  cycle: {cycle['cycle']}")
    print(f"  mode: {cycle['mode']}")
    print(f"  events: {cycle['events']}")
    print(f"  memory episodes: {cycle['memory']['episodic']['total']}")


if __name__ == "__main__":
    main()
