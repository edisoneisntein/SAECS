from .bus import MessageBus, Event, EventType, EventPriority
from .types import Hypothesis


class Executor:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._domain_execute_fn = None
        self._restore_points: list[dict] = []
        bus.subscribe(EventType.EXECUTION_REQUESTED, self._on_execute)

    def register_execute_fn(self, fn) -> None:
        self._domain_execute_fn = fn

    def _on_execute(self, event: Event) -> None:
        h_data = event.data.get("hypothesis", {})
        hypothesis = Hypothesis(
            id=h_data.get("id", ""),
            description=h_data.get("description", ""),
            predicted_effect=h_data.get("predicted_effect", ""),
            confidence=h_data.get("confidence", 0.0),
            domain_data=h_data.get("domain_data", {}),
        )

        restore_point = {
            "hypothesis_id": hypothesis.id,
            "description": hypothesis.description,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        self._restore_points.append(restore_point)

        self.bus.publish(
            Event(
                type=EventType.RESTORE_POINT_CREATED,
                source="executor",
                data=restore_point,
                correlation_id=event.correlation_id,
                domain=event.domain,
            )
        )

        success = self.execute(hypothesis, domain_fn=self._domain_execute_fn)

        if success:
            self.bus.publish(
                Event(
                    type=EventType.EXECUTION_SUCCESS,
                    source="executor",
                    data={
                        "hypothesis_id": hypothesis.id,
                        "description": hypothesis.description,
                        "restore_point": restore_point,
                    },
                    priority=EventPriority.HIGH,
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )
        else:
            self.bus.publish(
                Event(
                    type=EventType.EXECUTION_FAILED,
                    source="executor",
                    data={
                        "hypothesis_id": hypothesis.id,
                        "error": "Domain execution failed",
                        "restore_point": restore_point,
                    },
                    priority=EventPriority.CRITICAL,
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )
            self.rollback(hypothesis.id)

    def execute(self, hypothesis: Hypothesis, domain_fn=None) -> bool:
        if domain_fn:
            return domain_fn(hypothesis)
        return True

    def rollback(self, hypothesis_id: str) -> bool:
        restore_points = [
            rp for rp in self._restore_points
            if rp["hypothesis_id"] == hypothesis_id
        ]
        if restore_points:
            rp = restore_points[-1]
            self.bus.publish(
                Event(
                    type=EventType.ROLLBACK_EXECUTED,
                    source="executor",
                    data={
                        "hypothesis_id": hypothesis_id,
                        "restore_point": rp,
                        "reason": "Execution failed, rolling back",
                    },
                    priority=EventPriority.CRITICAL,
                )
            )
            return True
        return False

    def summary(self) -> dict:
        return {
            "restore_points_created": len(self._restore_points),
            "has_execute_fn": self._domain_execute_fn is not None,
        }
