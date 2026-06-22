from ..core.bus import MessageBus, Event, EventType


class SemanticMemory:
    """What was learned. Domain-agnostic pattern repository."""

    def __init__(self, bus: MessageBus, storage_path: str = ".saecs/semantic"):
        self._bus = bus
        self._path = storage_path
        self._knowledge: dict[str, list[dict]] = {}
        self._load()
        bus.subscribe(EventType.PATTERN_FOUND, self._on_pattern)

    def _load(self) -> None:
        import json, os
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._knowledge = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._knowledge = {}

    def _save(self) -> None:
        import json, os
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._knowledge, f, indent=2, default=str)

    def _on_pattern(self, event: Event) -> None:
        self.learn(
            topic=event.data.get("topic", "pattern"),
            rule=event.data.get("rule", ""),
            evidence=event.data.get("evidence", ""),
            confidence=event.data.get("confidence", 0.5),
            domain=event.domain,
        )

    def learn(
        self, topic: str, rule: str, evidence: str = "",
        confidence: float = 1.0, domain: str | None = None,
    ) -> None:
        import datetime
        key = f"{domain}:{topic}" if domain else topic
        if key not in self._knowledge:
            self._knowledge[key] = []

        existing = [r for r in self._knowledge[key] if r["rule"] == rule]
        if existing:
            existing[0]["confidence"] = max(existing[0]["confidence"], confidence)
            existing[0]["evidence"] = evidence
            existing[0]["updated_at"] = datetime.datetime.now().isoformat()
        else:
            self._knowledge[key].append({
                "rule": rule, "evidence": evidence,
                "confidence": confidence,
                "domain": domain,
                "created_at": datetime.datetime.now().isoformat(),
            })
        self._save()

    def recall(self, topic: str, domain: str | None = None) -> list[dict]:
        if domain:
            return self._knowledge.get(f"{domain}:{topic}", [])
        results = []
        for key, rules in self._knowledge.items():
            if topic in key:
                results.extend(rules)
        return results

    def generalize(self, episodes: list[dict]) -> int:
        patterns: dict[str, list[str]] = {}
        for ep in episodes:
            desc = ep.get("description", "")
            outcome = ep.get("outcome", "")
            key = desc[:60]
            if key not in patterns:
                patterns[key] = []
            patterns[key].append(outcome)

        count = 0
        for pattern, outcomes in patterns.items():
            if len(outcomes) >= 2:
                rate = outcomes.count("success") / len(outcomes)
                self.learn(
                    topic="pattern",
                    rule=f"{pattern} -> success {rate:.0%}",
                    evidence=f"Based on {len(outcomes)} episodes",
                    confidence=rate,
                )
                count += 1
        return count

    def summary(self) -> dict:
        total = sum(len(v) for v in self._knowledge.values())
        avg_conf = (
            sum(r["confidence"] for rules in self._knowledge.values() for r in rules)
            / max(total, 1)
        )
        return {"topics": len(self._knowledge), "rules": total, "avg_confidence": round(avg_conf, 2)}
