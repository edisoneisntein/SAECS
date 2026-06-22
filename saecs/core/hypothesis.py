from .bus import MessageBus, Event, EventType, EventPriority
from .types import Hypothesis


class HypothesisGenerator:
    """Domain-agnostic hypothesis generator."""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        bus.subscribe(EventType.INVESTIGATION_COMPLETE, self._on_investigation)

    def _on_investigation(self, event: Event) -> None:
        data = event.data
        domain = event.domain or "unknown"
        root_cause = data.get("root_cause", "unknown")
        evidence = data.get("evidence", [])

        hypotheses = self.generate(
            problem=data.get("problem", root_cause),
            root_cause=root_cause,
            domain=domain,
            evidence=evidence,
            context=data,
        )

        self.bus.publish(
            Event(
                type=EventType.HYPOTHESES_GENERATED,
                source="hypothesis_generator",
                data={
                    "hypotheses": [
                        {"id": h.id, "description": h.description,
                         "confidence": h.confidence, "falsified": h.falsified,
                         "target_metrics": h.target_metrics,
                         "falsifiers": h.falsifiers,
                         "scope": h.scope,
                         "evidence_quality": h.evidence_quality,
                         "domain_data": h.domain_data}
                        for h in hypotheses
                    ],
                    "count": len(hypotheses),
                    "problem": data.get("problem"),
                },
                priority=EventPriority.NORMAL,
                correlation_id=event.correlation_id,
                domain=domain,
            )
        )

    def generate(
        self,
        problem: str,
        root_cause: str,
        domain: str = "generic",
        evidence: list[str] | None = None,
        context: dict | None = None,
    ) -> list[Hypothesis]:
        import uuid
        context = context or {}
        metrics = context.get("metrics", {}) or {}
        ui_findings = context.get("ui_findings", []) or []
        scope = sorted({
            f.get("path")
            for f in ui_findings
            if isinstance(f, dict) and f.get("path")
        })[:8]
        target_metrics = self._target_metrics(metrics)
        falsifiers = self._falsifiers(target_metrics, root_cause, problem)
        evidence_quality = self._evidence_quality(evidence or [], metrics, ui_findings)
        h = Hypothesis(
            id=str(uuid.uuid4())[:8],
            description=f"Resolve: {problem}",
            predicted_effect=f"Address {root_cause}",
            confidence=0.7,
            evidence=evidence or [],
            target_metrics=target_metrics,
            falsifiers=falsifiers,
            scope=scope,
            evidence_quality=evidence_quality,
            expected_delta=self._expected_delta(target_metrics),
            domain_data={
                "domain": domain,
                "problem": problem,
                "root_cause": root_cause,
                "measurable": bool(target_metrics),
            },
        )
        alt = Hypothesis(
            id=str(uuid.uuid4())[:8],
            description=f"Alternative: mitigate effects of {problem}",
            predicted_effect=f"Partial mitigation of {root_cause}",
            confidence=0.4,
            evidence=evidence[:1] if evidence else [],
            target_metrics=target_metrics,
            falsifiers=falsifiers[:2],
            scope=scope[:3],
            evidence_quality=round(evidence_quality * 0.5, 3),
            expected_delta=self._expected_delta(target_metrics, factor=0.5),
            domain_data={"domain": domain, "alternative": True},
        )
        return [h, alt]

    def _target_metrics(self, metrics: dict) -> dict[str, float]:
        targets = {}
        if "ux_risk_score" in metrics:
            targets["ux_risk_score"] = 0.0
        if "confirmation_gaps" in metrics:
            targets["confirmation_gaps"] = 0.0
        if "accessibility_score" in metrics:
            targets["accessibility_score"] = 0.9
        if "avg_complexity" in metrics and metrics.get("avg_complexity", 0) > 10:
            targets["avg_complexity"] = 8.0
        return targets

    def _falsifiers(
        self, target_metrics: dict[str, float], root_cause: str, problem: str
    ) -> list[str]:
        falsifiers = []
        for metric, target in target_metrics.items():
            falsifiers.append(f"{metric} does not move toward {target}")
        falsifiers.append(f"Alternative cause explains problem: {root_cause}")
        falsifiers.append(f"Problem remains observable after intervention: {problem}")
        return falsifiers

    def _evidence_quality(
        self, evidence: list[str], metrics: dict, findings: list[dict]
    ) -> float:
        score = 0.0
        if evidence:
            score += min(len(evidence) * 0.15, 0.45)
        if metrics:
            score += 0.25
        if findings:
            score += min(len(findings) * 0.05, 0.25)
        return round(min(score, 1.0), 3)

    def _expected_delta(
        self, target_metrics: dict[str, float], factor: float = 1.0
    ) -> dict[str, float]:
        delta = {}
        for metric, target in target_metrics.items():
            if metric.endswith("_score") and target > 0:
                delta[metric] = round(0.1 * factor, 3)
            else:
                delta[metric] = round(-1.0 * factor, 3)
        return delta
