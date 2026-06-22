from __future__ import annotations
import uuid
from .bus import MessageBus, Event, EventType, EventPriority
from .types import (
    ExpectedUtility, Observation, Decision, Hypothesis,
    PerformanceSnapshot, SystemMode,
)
from .utility import UtilityEstimator
from .strategies import DecisionStrategies, StrategySelector


class Director:
    def __init__(self, bus: MessageBus, utility: UtilityEstimator):
        self.bus = bus
        self.utility = utility
        self.strategies = DecisionStrategies()
        self.selector = StrategySelector()
        self.cognitive_budget: float = 1000.0
        self.cognitive_spent: float = 0.0
        self.active_cycles: dict[str, str] = {}
        self.mode: SystemMode = SystemMode.NORMAL

        self.hypothesis_threshold: float = 0.5
        self.min_confidence_for_execution: float = 0.6
        self.uncertainty_investigate_threshold: float = 0.5
        self.utility_execute_threshold: float = 1.0

        bus.subscribe(EventType.OBSERVATION_READY, self._on_observation)
        bus.subscribe(EventType.INVESTIGATION_COMPLETE, self._on_investigation)
        bus.subscribe(EventType.HYPOTHESES_GENERATED, self._on_hypotheses)
        bus.subscribe(EventType.HYPOTHESIS_CONFIRMED, self._on_confirmed)
        bus.subscribe(EventType.HYPOTHESIS_FALSIFIED, self._on_falsified)
        bus.subscribe(EventType.EXPERIMENT_FAILED, self._on_experiment_failed)
        bus.subscribe(EventType.EXECUTION_SUCCESS, self._on_executed)
        bus.subscribe(EventType.PARAMETER_ADJUSTED, self._on_parameter_adjusted)

    @property
    def parameters(self) -> dict[str, float]:
        return {
            "cognitive_budget": self.cognitive_budget,
            "hypothesis_threshold": self.hypothesis_threshold,
            "min_confidence_for_execution": self.min_confidence_for_execution,
            "uncertainty_investigate_threshold": self.uncertainty_investigate_threshold,
            "utility_execute_threshold": self.utility_execute_threshold,
            "budget_remaining": self.cognitive_budget - self.cognitive_spent,
        }

    def set_parameter(self, name: str, value: float) -> None:
        if hasattr(self, name):
            old = getattr(self, name)
            setattr(self, name, value)
            self.bus.publish(Event(
                type=EventType.PARAMETER_ADJUSTED,
                source="director",
                data={
                    "parameter": name,
                    "old_value": old,
                    "new_value": value,
                    "reason": f"Director parameter update: {name} = {value}",
                },
            ))

    def start_cycle(self, domain: str = "generic") -> str:
        cid = str(uuid.uuid4())[:8]
        self.active_cycles[cid] = domain

        self.bus.publish(
            Event(
                type=EventType.CYCLE_START,
                source="director",
                data={"cycle_id": cid, "domain": domain},
                priority=EventPriority.HIGH,
                domain=domain,
            )
        )
        return cid

    def end_cycle(self, cid: str) -> None:
        domain = self.active_cycles.pop(cid, "generic")

        snapshot = PerformanceSnapshot(
            cycle=len(self.active_cycles),
        )
        self.utility.evolve(snapshot)

        self.bus.publish(
            Event(
                type=EventType.CYCLE_COMPLETE,
                source="director",
                data={"cycle_id": cid, "domain": domain},
                domain=domain,
            )
        )

    def _check_budget(self, amount: float) -> bool:
        return self.cognitive_spent + amount <= self.cognitive_budget

    def _spend(self, amount: float) -> None:
        self.cognitive_spent += amount

    def _decide(
        self,
        observation: Observation,
        utility: ExpectedUtility,
        hypotheses: list[Hypothesis] | None = None,
    ) -> Decision:
        if not self._check_budget(utility.terms["cognitive_cost"].value * utility.terms["cognitive_cost"].weight):
            return Decision(
                action="skip",
                utility=utility,
                reasoning=[f"Cognitive budget exceeded ({self.cognitive_spent:.0f}/{self.cognitive_budget:.0f})"],
                approved=False,
            )

        if self.mode == SystemMode.MAINTENANCE:
            return Decision(
                action="skip",
                utility=utility,
                reasoning=[f"System in MAINTENANCE mode, skipping all actions"],
                approved=False,
            )

        if self.mode == SystemMode.CONSERVATIVE:
            if observation.uncertainty > 0.2:
                return Decision(
                    action="skip",
                    utility=utility,
                    reasoning=[f"CONSERVATIVE mode: uncertainty {observation.uncertainty:.2f} > 0.2"],
                    approved=False,
                )

        strategy_name = self.selector.select(
            uncertainty=observation.uncertainty,
            budget_remaining=1.0 - (self.cognitive_spent / max(self.cognitive_budget, 1)),
        )

        strategy_map = {
            "expected_utility": lambda: self.strategies.expected_utility(utility, observation),
            "regret_minimization": lambda: self.strategies.regret_minimization(utility, observation),
            "thompson_sampling": lambda: self.strategies.thompson_sampling(utility, observation, hypotheses),
            "mcts": lambda: self.strategies.mcts(utility, observation),
            "active_inference": lambda: self.strategies.active_inference(utility, observation),
        }
        decision_fn = strategy_map.get(strategy_name, strategy_map["expected_utility"])
        decision = decision_fn()
        decision.strategy = strategy_name

        self._spend(utility.terms["cognitive_cost"].value * utility.terms["cognitive_cost"].weight)

        self.bus.publish(
            Event(
                type=EventType.INACTION_DECIDED if decision.action == "skip" else EventType.DECISION_MADE,
                source="director",
                data={
                    "action": decision.action,
                    "strategy": strategy_name,
                    "utility": utility.summary(),
                    "reasoning": decision.reasoning,
                    "uncertainty": observation.uncertainty,
                },
                priority=EventPriority.HIGH,
                correlation_id=getattr(decision, 'correlation_id', None),
                domain=observation.domain_id,
            )
        )

        self.selector.record_outcome(strategy_name, utility.total)
        return decision

    def _on_observation(self, event: Event) -> None:
        data = event.data
        obs = Observation(
            domain_id=event.domain or "generic",
            uncertainty=data.get("uncertainty", 0.0),
            changes_detected=data.get("changes_detected", False),
            state=data.get("state"),
        )

        utility = self.utility.estimate(obs)
        decision = self._decide(obs, utility)

        if decision.action == "investigate":
            self.bus.publish(
                Event(
                    type=EventType.INVESTIGATION_REQUESTED,
                    source="director",
                    data={
                        "problem": data.get("problem", "High uncertainty"),
                        "observation": data,
                    },
                    priority=EventPriority.HIGH,
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )

    def _on_investigation(self, event: Event) -> None:
        if self._check_budget(10):
            self._spend(10)

    def _on_hypotheses(self, event: Event) -> None:
        hypotheses = event.data.get("hypotheses", [])
        if not hypotheses:
            self.bus.publish(
                Event(
                    type=EventType.INTERVENTION_CANCELLED,
                    source="director",
                    data={"reason": "No valid hypotheses"},
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )
            return

        filtered = [h for h in hypotheses if h.get("confidence", 0) >= self.hypothesis_threshold]
        if not filtered:
            filtered = sorted(hypotheses, key=lambda h: h.get("confidence", 0), reverse=True)[:1]

        best = max(filtered, key=lambda h: h.get("confidence", 0))
        self.bus.publish(
            Event(
                type=EventType.HYPOTHESIS_SELECTED,
                source="director",
                data={"hypothesis": best},
                correlation_id=event.correlation_id,
                domain=event.domain,
            )
        )

        if self._check_budget(15):
            self._spend(15)
            self.bus.publish(
                Event(
                    type=EventType.AUDIT_REQUESTED,
                    source="director",
                    data={"hypothesis": best},
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )

    def _on_confirmed(self, event: Event) -> None:
        data = event.data
        confidence = data.get("confidence_after", 0.0)

        if confidence >= self.min_confidence_for_execution and self._check_budget(30):
            self._spend(30)
            self.bus.publish(
                Event(
                    type=EventType.EXECUTION_REQUESTED,
                    source="director",
                    data={
                        "hypothesis": data.get("hypothesis", {}),
                        "confidence": confidence,
                    },
                    priority=EventPriority.HIGH,
                    correlation_id=event.correlation_id,
                    domain=event.domain,
                )
            )

    def _on_falsified(self, event: Event) -> None:
        pass

    def _on_experiment_failed(self, event: Event) -> None:
        pass

    def _on_executed(self, event: Event) -> None:
        for cid, domain in list(self.active_cycles.items()):
            self.end_cycle(cid)
            break

    def _on_parameter_adjusted(self, event: Event) -> None:
        data = event.data
        param = data.get("parameter", "")
        value = data.get("new_value")
        if hasattr(self, param) and value is not None:
            setattr(self, param, value)

    def summary(self) -> dict:
        return {
            "mode": self.mode.value,
            "strategy_selector": self.selector.summary(),
            "parameters": self.parameters,
            "budget_used": round(self.cognitive_spent, 1),
            "budget_limit": self.cognitive_budget,
            "budget_remaining": round(self.cognitive_budget - self.cognitive_spent, 1),
            "utilization_pct": round((self.cognitive_spent / self.cognitive_budget) * 100, 1),
            "active_cycles": len(self.active_cycles),
        }
