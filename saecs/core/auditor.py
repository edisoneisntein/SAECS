from .bus import MessageBus, Event, EventType, EventPriority
from .types import Hypothesis, AuditReport


class Auditor:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._domain_audit_fn = None
        self.audit_depth: float = 1.0
        bus.subscribe(EventType.AUDIT_REQUESTED, self._on_audit)
        bus.subscribe(EventType.PARAMETER_ADJUSTED, self._on_parameter_adjusted)

    def register_audit_fn(self, fn) -> None:
        self._domain_audit_fn = fn

    def _on_audit(self, event: Event) -> None:
        h_data = event.data.get("hypothesis", {})
        hypothesis = Hypothesis(
            id=h_data.get("id", ""),
            description=h_data.get("description", ""),
            predicted_effect=h_data.get("predicted_effect", ""),
            confidence=h_data.get("confidence", 0.0),
            evidence=h_data.get("evidence", []),
            domain_data=h_data.get("domain_data", {}),
        )

        report = self.audit(hypothesis, domain_fn=self._domain_audit_fn)

        event_type = (
            EventType.HYPOTHESIS_FALSIFIED if report.falsified
            else EventType.HYPOTHESIS_CONFIRMED
        )
        self.bus.publish(
            Event(
                type=event_type,
                source="auditor",
                data={
                    "hypothesis_id": hypothesis.id,
                    "falsified": report.falsified,
                    "falsification_reason": report.falsification_reason,
                    "tests_passed": report.tests_passed,
                    "tests_failed": report.tests_failed,
                    "confidence_after": report.confidence_after,
                    "attack_vectors": report.attack_vectors,
                    "hypothesis": h_data,
                },
                priority=EventPriority.HIGH,
                correlation_id=event.correlation_id,
                domain=event.domain,
            )
        )

    def audit(self, hypothesis: Hypothesis, domain_fn=None) -> AuditReport:
        if domain_fn:
            return domain_fn(hypothesis)

        tests_passed = 0
        tests_failed = 0
        attack_vectors = []
        depth = int(self.audit_depth * 3)

        if not hypothesis.evidence:
            tests_failed += 1
            attack_vectors.append("no_evidence")
        else:
            tests_passed += 1

        if hypothesis.confidence > 0.95:
            tests_failed += 1
            attack_vectors.append("inflated_confidence")
        else:
            tests_passed += 1

        if len(hypothesis.description) < 5:
            tests_failed += 1
            attack_vectors.append("vague_description")
        else:
            tests_passed += 1

        if hypothesis.domain_data.get("measurable") and not hypothesis.target_metrics:
            tests_failed += 1
            attack_vectors.append("missing_target_metrics")
        elif hypothesis.target_metrics:
            tests_passed += 1

        if hypothesis.target_metrics and not hypothesis.falsifiers:
            tests_failed += 1
            attack_vectors.append("missing_falsifiers")
        elif hypothesis.falsifiers:
            tests_passed += 1

        if hypothesis.evidence_quality and hypothesis.evidence_quality < 0.25:
            tests_failed += 1
            attack_vectors.append("low_evidence_quality")
        elif hypothesis.evidence_quality:
            tests_passed += 1

        if depth >= 2:
            if hypothesis.domain_data.get("alternative"):
                tests_failed += 1
                attack_vectors.append("alternative_hypothesis")
            else:
                tests_passed += 1

        if depth >= 3:
            if hypothesis.predicted_effect == hypothesis.description:
                tests_failed += 1
                attack_vectors.append("circular_effect")
            else:
                tests_passed += 1

        falsified = tests_failed > 0
        confidence_after = (
            0.0 if falsified
            else min(hypothesis.confidence * (1 + tests_passed * 0.05), 1.0)
        )

        return AuditReport(
            hypothesis_id=hypothesis.id,
            falsified=falsified,
            falsification_reason=(
                f"Failed {tests_failed} tests: {', '.join(attack_vectors)}"
                if falsified else None
            ),
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            confidence_after=round(confidence_after, 2),
            attack_vectors=attack_vectors,
        )

    def _on_parameter_adjusted(self, event: Event) -> None:
        data = event.data
        if data.get("parameter") == "audit_depth":
            self.audit_depth = data.get("new_value", 1.0)

    def summary(self) -> dict:
        return {"audit_depth": self.audit_depth}
