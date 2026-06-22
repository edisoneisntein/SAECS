from ..core.bus import MessageBus, Event, EventType


class StrategicMemory:
    """How to think better. Meta-cognitive knowledge about the
    investigation process itself (domain-agnostic)."""

    def __init__(self, bus: MessageBus, storage_path: str = ".saecs/strategic"):
        self._bus = bus
        self._path = storage_path
        self._strategies: dict[str, dict] = {}
        self._meta_rules: list[dict] = []
        self._load()
        bus.subscribe(EventType.BUDGET_EXCEEDED, self._on_budget)
        bus.subscribe(EventType.GOVERNANCE_REVIEW, self._on_governance)
        bus.subscribe(EventType.PARAMETER_ADJUSTED, self._on_adjustment)

    def _load(self) -> None:
        import json, os
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    d = json.load(f)
                    self._strategies = d.get("strategies", {})
                    self._meta_rules = d.get("meta_rules", [])
            except (json.JSONDecodeError, FileNotFoundError):
                self._strategies = {}
                self._meta_rules = []

    def _save(self) -> None:
        import json, os
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({
                "strategies": self._strategies,
                "meta_rules": self._meta_rules[-200:],
            }, f, indent=2, default=str)

    def _on_budget(self, event: Event) -> None:
        self._meta_rules.append({
            "type": "budget_lesson",
            "observation": event.data.get("observation", "Budget exceeded"),
            "cost": event.data.get("cost", 0),
            "domain": event.domain,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
        self._save()

    def _on_governance(self, event: Event) -> None:
        for obs in event.data.get("observations", []):
            self._meta_rules.append({
                "type": "governance_observation",
                "observation": obs,
                "domain": event.domain,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            })
        self._save()

    def _on_adjustment(self, event: Event) -> None:
        self._meta_rules.append({
            "type": "parameter_adjustment",
            "parameter": event.data.get("parameter"),
            "old_value": event.data.get("old_value"),
            "new_value": event.data.get("new_value"),
            "reason": event.data.get("reason"),
            "domain": event.domain,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
        self._save()

    def learn_strategy(
        self, name: str, description: str,
        effectiveness: float = 0.5, domain: str = "generic",
    ) -> None:
        import datetime
        s = self._strategies.get(name, {})
        s.update({
            "description": description,
            "effectiveness": effectiveness,
            "domain": domain,
            "times_used": s.get("times_used", 0) + 1,
            "last_used": datetime.datetime.now().isoformat(),
        })
        self._strategies[name] = s
        self._save()

    def recommend(self, domain: str = "generic") -> dict | None:
        candidates = [
            s for n, s in self._strategies.items()
            if s.get("domain") == domain and s["effectiveness"] > 0.5
        ]
        if not candidates:
            candidates = [
                s for s in self._strategies.values()
                if s["effectiveness"] > 0.5
            ]
        return max(candidates, key=lambda s: s["effectiveness"]) if candidates else None

    def summary(self) -> dict:
        return {
            "strategies": len(self._strategies),
            "meta_rules": len(self._meta_rules),
            "best": max(
                self._strategies.items(),
                key=lambda s: s[1]["effectiveness"], default=(None, None),
            ),
        }
