from __future__ import annotations

from saecs.core.bus import MessageBus, Event, EventType
from saecs.core.types import (
    Observation, DomainState, Hypothesis, AuditReport,
    DomainSchema, DomainHealth,
)
from saecs.core.adapter import DomainAdapter
from .scanner import scan_project


SOFTWARE_SCHEMA = DomainSchema(
    entities={
        "repository": {
            "fields": ["name", "language", "test_framework"],
            "observables": ["test_coverage", "build_status", "lint_errors"],
            "intervenibles": ["create_pr", "run_tests", "refactor"],
        }
    },
    metrics={
        "modules": {"type": "scalar", "range": [0, 100000]},
        "avg_complexity": {"type": "scalar", "range": [0, 1000]},
        "web_files": {"type": "scalar", "range": [0, 100000]},
        "ux_risk_score": {"type": "scalar", "range": [0, 1]},
        "accessibility_score": {"type": "scalar", "range": [0, 1]},
        "confirmation_gaps": {"type": "scalar", "range": [0, 100000]},
    },
    signals={
        "code_pushed": "Nuevo commit",
        "build_failed": "Build roto",
        "ui_risk_detected": "Riesgo de experiencia detectado",
    },
)


class _ProjectDomainBase(DomainAdapter):
    domain = "software"
    version = "2.1"
    schema = SOFTWARE_SCHEMA
    include_code = True
    include_web = True
    source = "software_domain"

    def __init__(self, bus: MessageBus, project_path: str = "."):
        self.bus = bus
        self.project_path = project_path

    def observe(self, query: dict | None = None) -> Observation:
        components, metrics, uncertainty, changes = scan_project(
            self.project_path,
            include_code=self.include_code,
            include_web=self.include_web,
        )
        findings = [c for c in components if c.get("kind") == "ui_finding"]
        state = DomainState(
            metrics=metrics,
            metadata={
                "components": components,
                "findings": findings,
                "ui_findings": findings,
                "project_path": self.project_path,
                "adapter": self.domain,
            },
        )
        obs = Observation(
            domain_id=self.domain,
            state=state,
            uncertainty=uncertainty,
            changes_detected=changes,
            components=components,
        )
        self.bus.publish(
            Event(
                type=EventType.OBSERVATION_READY,
                source=self.source,
                data={
                    "uncertainty": uncertainty,
                    "changes_detected": changes,
                    "components": components,
                    "findings": findings,
                    "ui_findings": findings,
                    "metrics": metrics,
                    "problem": self._problem_statement(metrics, findings, changes),
                    "evidence": self._evidence(metrics, findings),
                },
                domain=self.domain,
            )
        )
        return obs

    def audit_hypothesis(self, hypothesis: Hypothesis) -> AuditReport:
        components, metrics, _, _ = scan_project(
            self.project_path,
            include_code=self.include_code,
            include_web=self.include_web,
        )
        findings = [c for c in components if c.get("kind") == "ui_finding"]
        tests_passed = 0
        tests_failed = 0
        attack_vectors = []

        if not hypothesis.evidence and not findings:
            tests_failed += 1
            attack_vectors.append("no_project_evidence")
        else:
            tests_passed += 1

        if hypothesis.domain_data.get("domain") in ("web_ui", "software"):
            if self.include_web and metrics.get("web_files", 0) == 0:
                tests_failed += 1
                attack_vectors.append("no_web_surface_detected")
            else:
                tests_passed += 1

        if metrics.get("confirmation_gaps", 0) and "confirm" not in " ".join(hypothesis.falsifiers).lower():
            tests_failed += 1
            attack_vectors.append("confirmation_risk_not_falsifiable")
        else:
            tests_passed += 1

        if metrics.get("accessibility_score", 1.0) < 0.7 and "accessibility_score" not in hypothesis.target_metrics:
            tests_failed += 1
            attack_vectors.append("accessibility_risk_not_measured")
        else:
            tests_passed += 1

        if metrics.get("responsive_signals", 0) == 0 and not any("responsive" in f.lower() for f in hypothesis.falsifiers):
            tests_failed += 1
            attack_vectors.append("responsive_risk_not_falsifiable")
        else:
            tests_passed += 1

        falsified = tests_failed > 0
        confidence_after = 0.0 if falsified else min(hypothesis.confidence + 0.1, 1.0)
        return AuditReport(
            hypothesis_id=hypothesis.id,
            falsified=falsified,
            falsification_reason=(
                f"Failed {tests_failed} domain audit tests: {', '.join(attack_vectors)}"
                if falsified else None
            ),
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            confidence_after=round(confidence_after, 2),
            attack_vectors=attack_vectors,
        )

    def intervene(self, action: dict) -> dict:
        action_type = action.get("action", "unknown")
        target = action.get("target", "")
        return {
            "success": True,
            "action": action_type,
            "target": target,
            "outcome": f"Executed {action_type} on {target}",
        }

    def simulate(self, experiment: dict) -> dict:
        return {
            "success": True,
            "predicted_outcome": "Simulation completed",
            "confidence": 0.8,
        }

    def validate(self, action: dict) -> dict:
        action_type = action.get("action", "")
        if action_type in {"delete", "remove", "disable", "execute"}:
            return {
                "safe": False,
                "risks": [{"description": "High-impact operations require human approval", "probability": 1.0}],
                "requires_human_approval": True,
            }
        return {"safe": True, "risks": [], "requires_human_approval": False}

    def health(self) -> DomainHealth:
        metrics = self.observe().state.metrics
        status = "healthy"
        if metrics.get("critical_ui_findings", 0) > 0:
            status = "critical"
        elif metrics.get("ux_risk_score", 0) >= 0.5 or metrics.get("avg_complexity", 0) > 10:
            status = "degraded"
        return DomainHealth(status=status, metrics=metrics)

    def benefit_fn(self, obs: Observation) -> float:
        if self.include_web and obs.state.metrics.get("accessibility_score") is not None:
            return obs.state.metrics.get("accessibility_score", 0.0)
        complexity = obs.state.metrics.get("avg_complexity", 0.0)
        return max(1.0 - min(complexity / 20.0, 1.0), 0.0)

    def cost_fn(self, obs: Observation) -> float:
        complexity = obs.state.metrics.get("avg_complexity", 5)
        findings = obs.state.metrics.get("ui_findings", 0)
        return min((complexity / 20.0) + (findings * 0.03), 1.0)

    def risk_fn(self, obs: Observation) -> float:
        return min(obs.uncertainty * 0.4 + obs.state.metrics.get("ux_risk_score", 0), 1.0)

    def execute_fn(self, hypothesis: Hypothesis) -> bool:
        return True

    def _problem_statement(self, metrics: dict, findings: list[dict], changes: bool) -> str:
        if metrics.get("critical_ui_findings", 0):
            return "Critical operational interaction issues detected"
        if metrics.get("ux_risk_score", 0) >= 0.5:
            return "Elevated user-experience risk detected"
        if findings:
            return "User-experience improvement opportunities detected"
        if metrics.get("avg_complexity", 0) > 10:
            return "Elevated code complexity detected"
        return "Project changes detected" if changes else "Routine observation"

    def _evidence(self, metrics: dict, findings: list[dict]) -> list[str]:
        keys = [
            "modules",
            "avg_complexity",
            "web_files",
            "ux_risk_score",
            "accessibility_score",
            "confirmation_gaps",
        ]
        evidence = [f"{key}={metrics.get(key, 0)}" for key in keys if key in metrics]
        evidence.extend(
            f"{f.get('severity')}: {f.get('path')} - {f.get('problem')}"
            for f in findings[:5]
        )
        return evidence


class CodeDomain(_ProjectDomainBase):
    domain = "code"
    source = "code_domain"
    include_code = True
    include_web = False


class WebUIDomain(_ProjectDomainBase):
    domain = "web_ui"
    source = "web_ui_domain"
    include_code = False
    include_web = True


class SoftwareDomain(_ProjectDomainBase):
    """Backward-compatible aggregate domain for mixed software projects."""

    domain = "software"
    source = "software_domain"
    include_code = True
    include_web = True
