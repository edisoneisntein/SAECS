from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime
from enum import Enum


class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventType(Enum):
    # Core cognitive cycle (domain-agnostic)
    CYCLE_START = "cycle_start"
    CYCLE_COMPLETE = "cycle_complete"

    OBSERVATION_READY = "observation_ready"
    UNCERTAINTY_EVALUATED = "uncertainty_evaluated"

    UTILITY_CALCULATED = "utility_calculated"
    DECISION_MADE = "decision_made"
    INTERVENTION_CANCELLED = "intervention_cancelled"
    INACTION_DECIDED = "inaction_decided"

    INVESTIGATION_REQUESTED = "investigation_requested"
    INVESTIGATION_COMPLETE = "investigation_complete"

    HYPOTHESES_GENERATED = "hypotheses_generated"
    HYPOTHESIS_SELECTED = "hypothesis_selected"

    EXPERIMENT_REQUESTED = "experiment_requested"
    EXPERIMENT_COMPLETE = "experiment_complete"
    EXPERIMENT_FAILED = "experiment_failed"

    AUDIT_REQUESTED = "audit_requested"
    AUDIT_COMPLETE = "audit_complete"
    HYPOTHESIS_FALSIFIED = "hypothesis_falsified"
    HYPOTHESIS_CONFIRMED = "hypothesis_confirmed"

    EXECUTION_REQUESTED = "execution_requested"
    EXECUTION_SUCCESS = "execution_success"
    EXECUTION_FAILED = "execution_failed"
    RESTORE_POINT_CREATED = "restore_point_created"
    ROLLBACK_EXECUTED = "rollback_executed"

    # Memory events
    MEMORY_STORED = "memory_stored"
    PATTERN_FOUND = "pattern_found"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Governance events (meta-cognitive)
    GOVERNANCE_REVIEW = "governance_review"
    STRATEGY_UPDATED = "strategy_updated"
    PARAMETER_ADJUSTED = "parameter_adjusted"
    ARCHITECTURE_PROPOSAL = "architecture_proposal"


@dataclass
class Event:
    type: EventType
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: str | None = None
    domain: str | None = None

    def reply(self, event_type: EventType, data: dict | None = None) -> Event:
        return Event(
            type=event_type,
            source=self.source,
            data=data or {},
            correlation_id=self.correlation_id,
            domain=self.domain,
        )


Handler = Callable[[Event], None]


class MessageBus:
    def __init__(self):
        self._subscribers: dict[EventType, list[Handler]] = {}
        self._history: list[Event] = []
        self._max_history = 2000

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_many(
        self, event_types: list[EventType], handler: Handler
    ) -> None:
        for et in event_types:
            self.subscribe(et, handler)

    def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                self.publish(
                    Event(
                        type=EventType.CYCLE_COMPLETE,
                        source="bus",
                        data={
                            "error": str(e),
                            "handler": str(handler),
                            "original_event": event.type.value,
                        },
                        priority=EventPriority.CRITICAL,
                        domain=event.domain,
                    )
                )

    def get_history(
        self,
        event_type: EventType | None = None,
        source: str | None = None,
        domain: str | None = None,
        limit: int = 50,
    ) -> list[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        if source:
            events = [e for e in events if e.source == source]
        if domain:
            events = [e for e in events if e.domain == domain]
        return events[-limit:]

    def clear(self) -> None:
        self._history.clear()
