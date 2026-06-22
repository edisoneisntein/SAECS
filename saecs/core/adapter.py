from __future__ import annotations
from typing import Any, Callable
from .types import DomainSchema, DomainHealth, DomainState, Observation


class DomainAdapter:
    """Protocolo formal para adaptadores de dominio (SAECS-011)."""

    domain: str = "generic"
    version: str = "1.0"
    schema: DomainSchema = DomainSchema()

    def observe(self, query: dict | None = None) -> Observation:
        raise NotImplementedError

    def intervene(self, action: dict) -> dict:
        raise NotImplementedError

    def simulate(self, experiment: dict) -> dict:
        raise NotImplementedError

    def validate(self, action: dict) -> dict:
        return {"safe": True, "risks": [], "requires_human_approval": False}

    def health(self) -> DomainHealth:
        return DomainHealth(status="healthy")

    def benefit_fn(self, obs: Observation) -> float:
        return max(1.0 - obs.uncertainty, 0.0)

    def cost_fn(self, obs: Observation) -> float:
        return obs.uncertainty * 0.5

    def risk_fn(self, obs: Observation) -> float:
        return obs.uncertainty * 0.3

    def uncertainty_fn(self, obs: Observation) -> float:
        return obs.uncertainty

    def execute_fn(self, hypothesis: Any) -> bool:
        return True

    def experiment_fn(self, hypothesis: Any) -> Any:
        from .types import ExperimentResult
        return ExperimentResult(
            hypothesis_id=hypothesis.id if hasattr(hypothesis, 'id') else "",
            success=True,
        )


class DomainRegistry:
    _adapters: dict[str, DomainAdapter] = {}

    @classmethod
    def register(cls, adapter: DomainAdapter) -> None:
        cls._adapters[adapter.domain] = adapter

    @classmethod
    def get(cls, domain: str) -> DomainAdapter | None:
        return cls._adapters.get(domain)

    @classmethod
    def all(cls) -> list[DomainAdapter]:
        return list(cls._adapters.values())

    @classmethod
    def discover(cls, path: str) -> list[str]:
        discovered = []
        for adapter in cls._adapters.values():
            discovered.append(adapter.domain)
        return discovered
