from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime
from enum import Enum


class InterventionStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SystemMode(Enum):
    NORMAL = "normal"
    CONSERVATIVE = "conservative"
    MAINTENANCE = "maintenance"
    QUARANTINE = "quarantine"
    RECOVERY = "recovery"
    SHUTDOWN = "shutdown"


class DecisionStrategyType(Enum):
    EXPECTED_UTILITY = "expected_utility"
    REGRET_MINIMIZATION = "regret_minimization"
    THOMPSON_SAMPLING = "thompson_sampling"
    MCTS = "mcts"
    ACTIVE_INFERENCE = "active_inference"


@dataclass
class DomainState:
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> DomainState:
        return DomainState(
            metrics=dict(self.metrics), metadata=dict(self.metadata)
        )


@dataclass
class Observation:
    domain_id: str
    state: DomainState = field(default_factory=DomainState)
    uncertainty: float = 0.0
    changes_detected: bool = False
    components: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Hypothesis:
    id: str
    description: str
    predicted_effect: str
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    target_metrics: dict[str, float] = field(default_factory=dict)
    falsifiers: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    evidence_quality: float = 0.0
    expected_delta: dict[str, float] = field(default_factory=dict)
    falsified: bool = False
    falsification_reason: str | None = None
    domain_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentResult:
    hypothesis_id: str
    success: bool
    metrics_before: dict[str, float] = field(default_factory=dict)
    metrics_after: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    evidence_collected: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class AuditReport:
    hypothesis_id: str
    falsified: bool
    falsification_reason: str | None = None
    tests_passed: int = 0
    tests_failed: int = 0
    confidence_after: float = 0.0
    attack_vectors: list[str] = field(default_factory=list)


@dataclass
class UtilityTerm:
    name: str
    weight: float = 1.0
    value: float = 0.0
    sign: int = 1
    learnable: bool = True
    min_weight: float = 0.0
    max_weight: float = 5.0

    def compute(self, observation: Observation, **kwargs) -> float:
        return self.weight * self.value


@dataclass
class ExpectedUtility:
    terms: dict[str, UtilityTerm] = field(default_factory=dict)
    confidence: float = 1.0

    @classmethod
    def default(cls) -> ExpectedUtility:
        return cls(terms={
            "benefit": UtilityTerm("benefit", weight=1.0, sign=1),
            "cost": UtilityTerm("cost", weight=1.0, sign=-1),
            "risk": UtilityTerm("risk", weight=1.0, sign=-1),
            "opportunity_cost": UtilityTerm("opportunity_cost", weight=1.0, sign=-1),
            "cognitive_cost": UtilityTerm("cognitive_cost", weight=1.0, sign=-1),
            "value_of_information": UtilityTerm("value_of_information", weight=1.0, sign=1),
            "learning_value": UtilityTerm("learning_value", weight=1.0, sign=1),
        })

    @property
    def total(self) -> float:
        raw = sum(t.sign * t.weight * t.value for t in self.terms.values())
        return raw * self.confidence

    def summary(self) -> dict[str, float]:
        result = {}
        for name, term in self.terms.items():
            result[name] = round(term.value, 3)
            result[f"{name}_weight"] = round(term.weight, 3)
        result["confidence"] = round(self.confidence, 3)
        result["total"] = round(self.total, 3)
        return result


@dataclass
class Decision:
    action: str
    hypothesis_id: str | None = None
    utility: ExpectedUtility | None = None
    reasoning: list[str] = field(default_factory=list)
    approved: bool = False
    strategy: str | None = None


@dataclass
class CausalNode:
    name: str
    value: float = 0.0
    uncertainty: float = 1.0
    is_observable: bool = True
    is_intervenible: bool = False
    is_target: bool = False

    def snapshot(self) -> CausalNode:
        return CausalNode(
            name=self.name,
            value=self.value,
            uncertainty=self.uncertainty,
            is_observable=self.is_observable,
            is_intervenible=self.is_intervenible,
            is_target=self.is_target,
        )


@dataclass
class CausalEdge:
    source: str
    target: str
    strength: float = 0.5
    uncertainty: float = 0.5
    learned_from: str = "prior"
    samples: int = 0


@dataclass
class CausalGraph:
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    edges: list[CausalEdge] = field(default_factory=list)

    def add_node(self, name: str, **kwargs) -> CausalNode:
        if name not in self.nodes:
            self.nodes[name] = CausalNode(name=name, **kwargs)
        return self.nodes[name]

    def add_edge(self, source: str, target: str, **kwargs) -> CausalEdge:
        edge = CausalEdge(source=source, target=target, **kwargs)
        self.edges.append(edge)
        return edge

    def get_children(self, node: str) -> list[CausalEdge]:
        return [e for e in self.edges if e.source == node]

    def get_parents(self, node: str) -> list[CausalEdge]:
        return [e for e in self.edges if e.target == node]

    def compute_impact(self, source: str, target: str) -> float:
        impact = 0.0
        for edge in self.edges:
            if edge.source == source:
                if edge.target == target:
                    impact += edge.strength
                else:
                    impact += edge.strength * self.compute_impact(edge.target, target) * 0.5
        return impact


@dataclass
class Goal:
    id: str
    description: str
    goal_type: str = "improve_attribute"
    target_metrics: dict[str, float] = field(default_factory=dict)
    priority: float = 0.5
    deadline: datetime | None = None
    parent_goal: str | None = None
    completed: bool = False


@dataclass
class PlannedStep:
    id: str
    action: str
    target: str
    expected_utility: float = 0.0
    estimated_cost: float = 0.0
    estimated_risk: float = 0.0
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None


@dataclass
class Plan:
    id: str
    goal: Goal
    objective_function: str = ""
    horizon: int = 10
    status: str = "active"
    steps: list[PlannedStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Modification:
    target: str
    component: str
    parameter: str
    current_value: Any = None
    proposed_value: Any = None
    rationale: str = ""
    level: int = 1
    status: str = "pending"
    id: str = ""
    old_state: Any = None


@dataclass
class PerformanceSnapshot:
    cycle: int
    falsification_rate: float = 0.0
    success_rate: float = 0.0
    avg_utility: float = 0.0
    budget_utilization: float = 0.0
    hypotheses_generated: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DomainSchema:
    entities: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    signals: dict = field(default_factory=dict)
    actions: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)


@dataclass
class DomainHealth:
    status: str = "healthy"
    metrics: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
