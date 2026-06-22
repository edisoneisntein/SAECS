from .bus import MessageBus, Event, EventType, EventPriority
from .types import Hypothesis, ExperimentResult


class Experimenter:
    """Domain-agnostic experiment runner. Delegates execution to domain adapter."""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._domain_experiment_fn = None
        bus.subscribe(EventType.EXPERIMENT_REQUESTED, self._on_experiment)

    def register_experiment_fn(self, fn) -> None:
        self._domain_experiment_fn = fn

    def _on_experiment(self, event: Event) -> None:
        h_data = event.data.get("hypothesis", {})
        hypothesis = Hypothesis(
            id=h_data.get("id", ""),
            description=h_data.get("description", ""),
            predicted_effect=h_data.get("predicted_effect", ""),
            confidence=h_data.get("confidence", 0.0),
            domain_data=h_data.get("domain_data", {}),
        )

        result = self.run(hypothesis, domain_fn=self._domain_experiment_fn)

        event_type = (
            EventType.EXPERIMENT_COMPLETE if result.success
            else EventType.EXPERIMENT_FAILED
        )
        self.bus.publish(
            Event(
                type=event_type,
                source="experimenter",
                data={
                    "hypothesis_id": hypothesis.id,
                    "success": result.success,
                    "metrics_before": result.metrics_before,
                    "metrics_after": result.metrics_after,
                    "errors": result.errors,
                    "evidence_collected": result.evidence_collected,
                },
                priority=EventPriority.HIGH,
                correlation_id=event.correlation_id,
                domain=event.domain,
            )
        )

    def run(
        self,
        hypothesis: Hypothesis,
        domain_fn=None,
    ) -> ExperimentResult:
        if domain_fn:
            return domain_fn(hypothesis)

        errors = []
        evidence = [f"Experiment for: {hypothesis.description}"]
        success = len(errors) == 0

        return ExperimentResult(
            hypothesis_id=hypothesis.id,
            success=success,
            metrics_before={},
            metrics_after={},
            errors=errors,
            evidence_collected=evidence,
        )
