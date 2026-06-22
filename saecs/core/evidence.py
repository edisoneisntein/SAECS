from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass
class EvidenceItem:
    id: str
    claim: str
    source: str
    kind: str = "observation"
    strength: float = 0.5
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def weight(self) -> float:
        return max(0.0, min(self.strength, 1.0)) * max(0.0, min(self.confidence, 1.0))


@dataclass
class EvidenceGraph:
    items: dict[str, EvidenceItem] = field(default_factory=dict)
    supports: dict[str, list[str]] = field(default_factory=dict)
    contradicts: dict[str, list[str]] = field(default_factory=dict)

    def add(
        self,
        claim: str,
        source: str,
        kind: str = "observation",
        strength: float = 0.5,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        item = EvidenceItem(
            id=str(uuid.uuid4())[:8],
            claim=claim,
            source=source,
            kind=kind,
            strength=strength,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.items[item.id] = item
        return item

    def link_support(self, evidence_id: str, hypothesis_id: str) -> None:
        self.supports.setdefault(hypothesis_id, []).append(evidence_id)

    def link_contradiction(self, evidence_id: str, hypothesis_id: str) -> None:
        self.contradicts.setdefault(hypothesis_id, []).append(evidence_id)

    def quality_for(self, hypothesis_id: str) -> float:
        support = sum(self.items[eid].weight() for eid in self.supports.get(hypothesis_id, []) if eid in self.items)
        contradiction = sum(
            self.items[eid].weight()
            for eid in self.contradicts.get(hypothesis_id, [])
            if eid in self.items
        )
        raw = support - contradiction
        return round(max(0.0, min(raw, 1.0)), 3)

    def summary(self) -> dict[str, Any]:
        return {
            "items": len(self.items),
            "support_links": sum(len(v) for v in self.supports.values()),
            "contradiction_links": sum(len(v) for v in self.contradicts.values()),
        }
