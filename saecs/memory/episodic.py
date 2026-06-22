from ..core.bus import MessageBus, Event, EventType


class EpisodicMemory:
    """What happened. Domain-agnostic event log."""

    def __init__(self, bus: MessageBus, storage_path: str = ".saecs/episodic"):
        self._bus = bus
        self._path = storage_path
        self._episodes: list[dict] = []
        self._load()
        bus.subscribe_many(
            [EventType.CYCLE_COMPLETE, EventType.AUDIT_COMPLETE,
             EventType.EXECUTION_SUCCESS, EventType.EXECUTION_FAILED,
             EventType.HYPOTHESIS_FALSIFIED, EventType.EXPERIMENT_FAILED],
            self._on_event,
        )

    def _load(self) -> None:
        import json, os
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._episodes = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._episodes = []

    def _save(self) -> None:
        import json, os
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._episodes[-500:], f, indent=2, default=str)

    def _on_event(self, event: Event) -> None:
        self.store(
            event_type=event.type.value,
            description=str(event.data.get("description", event.type.value)),
            outcome=(
                "success" if event.type in (
                    EventType.EXECUTION_SUCCESS, EventType.HYPOTHESIS_CONFIRMED)
                else "failed" if event.type in (
                    EventType.EXECUTION_FAILED, EventType.HYPOTHESIS_FALSIFIED)
                else "completed"
            ),
            domain=event.domain,
            metadata=event.data,
        )

    def store(
        self, event_type: str, description: str, outcome: str,
        domain: str | None = None, metadata: dict | None = None,
    ) -> None:
        import datetime
        self._episodes.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": event_type,
            "description": description,
            "outcome": outcome,
            "domain": domain or "generic",
            "metadata": metadata or {},
        })
        self._save()

    def query(
        self, event_type: str | None = None,
        outcome: str | None = None,
        domain: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        results = list(self._episodes)
        if event_type:
            results = [e for e in results if e["event_type"] == event_type]
        if outcome:
            results = [e for e in results if e["outcome"] == outcome]
        if domain:
            results = [e for e in results if e.get("domain") == domain]
        return results[-limit:]

    @property
    def count(self) -> int:
        return len(self._episodes)

    def summary(self) -> dict:
        outcomes: dict[str, int] = {}
        types: dict[str, int] = {}
        for e in self._episodes:
            outcomes[e["outcome"]] = outcomes.get(e["outcome"], 0) + 1
            types[e["event_type"]] = types.get(e["event_type"], 0) + 1
        return {"total": self.count, "outcomes": outcomes, "event_types": types}
