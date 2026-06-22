from __future__ import annotations
import math
from .bus import MessageBus, Event, EventType, EventPriority
from .types import Observation, Hypothesis, ExpectedUtility, UtilityTerm, PerformanceSnapshot


class UtilityEstimator:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.utility = ExpectedUtility.default()
        self._performance_history: list[PerformanceSnapshot] = []

        bus.subscribe(EventType.UNCERTAINTY_EVALUATED, self._on_uncertainty)

    @property
    def parameters(self) -> dict[str, float]:
        return {
            term.name: term.weight
            for term in self.utility.terms.values()
        }

    def estimate(
        self,
        observation: Observation,
        domain_benefit_fn=None,
        domain_cost_fn=None,
        domain_risk_fn=None,
    ) -> ExpectedUtility:
        benefit = self._estimate_benefit(observation, domain_benefit_fn)
        cost = self._estimate_cost(observation, domain_cost_fn)
        risk = self._estimate_risk(observation, domain_risk_fn)
        opportunity_cost = self._estimate_opportunity(observation)
        cognitive_cost = self._estimate_cognitive(observation)
        voi = self._value_of_information(observation)
        learning = self._learning_value(observation)

        self.utility.terms["benefit"].value = benefit
        self.utility.terms["cost"].value = cost
        self.utility.terms["risk"].value = risk
        self.utility.terms["opportunity_cost"].value = opportunity_cost
        self.utility.terms["cognitive_cost"].value = cognitive_cost
        self.utility.terms["value_of_information"].value = voi
        self.utility.terms["learning_value"].value = learning
        self.utility.confidence = 1.0 - observation.uncertainty

        self.bus.publish(
            Event(
                type=EventType.UTILITY_CALCULATED,
                source="utility_estimator",
                data=self.utility.summary(),
                priority=EventPriority.NORMAL,
                domain=observation.domain_id,
            )
        )
        return self.utility

    def evolve(self, snapshot: PerformanceSnapshot) -> list[str]:
        self._performance_history.append(snapshot)
        changes = []

        if len(self._performance_history) < 3:
            return changes

        recent = self._performance_history[-3:]
        avg_utility = sum(s.avg_utility for s in recent) / len(recent)

        if snapshot.falsification_rate > 0.7:
            self.utility.terms["value_of_information"].weight *= 1.1
            self.utility.terms["value_of_information"].weight = min(
                self.utility.terms["value_of_information"].weight,
                self.utility.terms["value_of_information"].max_weight
            )
            changes.append("Increased VOI weight due to high falsification")

        if snapshot.success_rate < 0.2 and len(self._performance_history) >= 3:
            self.utility.terms["risk"].weight *= 1.2
            self.utility.terms["risk"].weight = min(
                self.utility.terms["risk"].weight,
                self.utility.terms["risk"].max_weight
            )
            changes.append("Increased risk weight due to low success rate")

        if snapshot.success_rate > 0.8:
            self.utility.terms["risk"].weight = max(
                self.utility.terms["risk"].weight * 0.95,
                self.utility.terms["risk"].min_weight
            )
            changes.append("Reduced risk weight due to high success rate")

        if snapshot.budget_utilization > 0.9:
            self.utility.terms["cognitive_cost"].weight *= 1.15
            self.utility.terms["cognitive_cost"].weight = min(
                self.utility.terms["cognitive_cost"].weight,
                self.utility.terms["cognitive_cost"].max_weight
            )
            changes.append("Increased cognitive cost weight due to budget pressure")

        if snapshot.budget_utilization < 0.3:
            self.utility.terms["cognitive_cost"].weight = max(
                self.utility.terms["cognitive_cost"].weight * 0.95,
                self.utility.terms["cognitive_cost"].min_weight
            )
            changes.append("Reduced cognitive cost weight due to low utilization")

        unexplained = self._compute_unexplained_variance()
        if unexplained > 0.2 and "value_of_information" not in [c[:5] for c in changes]:
            self.utility.terms["learning_value"].weight *= 1.1
            self.utility.terms["learning_value"].weight = min(
                self.utility.terms["learning_value"].weight,
                self.utility.terms["learning_value"].max_weight
            )
            changes.append("Increased learning value weight to explore new patterns")

        for change in changes:
            self.bus.publish(
                Event(
                    type=EventType.PARAMETER_ADJUSTED,
                    source="utility_estimator",
                    data={
                        "parameter": "utility_weights",
                        "change": change,
                        "weights": self.parameters,
                    },
                )
            )

        return changes

    def _compute_unexplained_variance(self) -> float:
        if len(self._performance_history) < 3:
            return 0.0
        recent = self._performance_history[-3:]
        values = [s.avg_utility for s in recent]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return min(variance / max(abs(mean), 0.01), 1.0)

    def _estimate_benefit(self, obs: Observation, domain_fn) -> float:
        if domain_fn:
            return domain_fn(obs)
        base = 1.0 - obs.uncertainty
        return max(base, 0.0)

    def _estimate_cost(self, obs: Observation, domain_fn) -> float:
        if domain_fn:
            return domain_fn(obs)
        return obs.uncertainty * 0.5

    def _estimate_risk(self, obs: Observation, domain_fn) -> float:
        if domain_fn:
            return domain_fn(obs)
        return obs.uncertainty * 0.3

    def _estimate_opportunity(self, obs: Observation) -> float:
        return obs.uncertainty * 0.2

    def _estimate_cognitive(self, obs: Observation) -> float:
        return 0.1 + obs.uncertainty * 0.2

    def _value_of_information(self, obs: Observation) -> float:
        return obs.uncertainty * 0.8

    def _learning_value(self, obs: Observation) -> float:
        return obs.uncertainty * 0.4

    def _on_uncertainty(self, event: Event) -> None:
        pass
