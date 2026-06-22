from __future__ import annotations
import math
import random
from typing import Any, Callable
from .types import (
    ExpectedUtility, Decision, DecisionStrategyType, Hypothesis, Observation,
)


class DecisionStrategies:
    @staticmethod
    def expected_utility(
        utility: ExpectedUtility,
        observation: Observation,
        **kwargs,
    ) -> Decision:
        if utility.total <= 0:
            return Decision(
                action="skip",
                utility=utility,
                reasoning=[f"EU={utility.total:.3f} <= 0, inaction is optimal"],
                strategy="expected_utility",
                approved=False,
            )
        if observation.uncertainty > 0.5:
            return Decision(
                action="investigate",
                utility=utility,
                reasoning=[f"EU={utility.total:.3f}, uncertainty={observation.uncertainty:.2f} > 0.5"],
                strategy="expected_utility",
                approved=True,
            )
        if utility.total > 1.0:
            return Decision(
                action="execute",
                utility=utility,
                reasoning=[f"EU={utility.total:.3f} > 1.0, direct execution"],
                strategy="expected_utility",
                approved=True,
            )
        return Decision(
            action="experiment",
            utility=utility,
            reasoning=[f"EU={utility.total:.3f} in (0, 1], experiment first"],
            strategy="expected_utility",
            approved=True,
        )

    @staticmethod
    def regret_minimization(
        utility: ExpectedUtility,
        observation: Observation,
        action_alternatives: list[dict] | None = None,
        **kwargs,
    ) -> Decision:
        alts = action_alternatives or [
            {"action": "skip", "benefit": 0, "cost": 0, "risk": 0},
            {"action": "investigate", "benefit": 3, "cost": 2, "risk": 0.1},
            {"action": "experiment", "benefit": 5, "cost": 5, "risk": 0.3},
            {"action": "execute", "benefit": 10, "cost": 8, "risk": 0.6},
        ]

        def action_utility(a: dict) -> float:
            return a["benefit"] - a["cost"] - a["risk"]

        utilities = {a["action"]: action_utility(a) for a in alts}
        max_util = max(utilities.values())
        regrets = {a: max_util - u for a, u in utilities.items()}
        best = min(regrets, key=regrets.get)

        return Decision(
            action=best,
            utility=utility,
            reasoning=[f"Minimax regret: {regrets}"],
            strategy="regret_minimization",
            approved=True,
        )

    @staticmethod
    def thompson_sampling(
        utility: ExpectedUtility,
        observation: Observation,
        hypotheses: list[Hypothesis] | None = None,
        **kwargs,
    ) -> Decision:
        if not hypotheses:
            return DecisionStrategies.expected_utility(utility, observation)

        samples = []
        for h in hypotheses:
            alpha = max(1, h.confidence * 10 - (h.falsified * 5))
            beta = max(1, (1 - h.confidence) * 10 + (h.falsified * 5))
            sample = random.betavariate(alpha, beta)
            samples.append((h, sample))

        best_h, best_sample = max(samples, key=lambda x: x[1])

        return Decision(
            action="experiment" if not best_h.falsified else "investigate",
            hypothesis_id=best_h.id,
            utility=utility,
            reasoning=[f"Thompson sample: {best_h.id} scored {best_sample:.3f}"],
            strategy="thompson_sampling",
            approved=True,
        )

    @staticmethod
    def mcts(
        utility: ExpectedUtility,
        observation: Observation,
        rollout_budget: int = 50,
        **kwargs,
    ) -> Decision:
        class MCTSNode:
            def __init__(self, action: str, parent=None):
                self.action = action
                self.parent = parent
                self.children: list[MCTSNode] = []
                self.visits = 0
                self.value = 0.0

            def ucb1(self, total_visits: int, c: float = 1.4) -> float:
                if self.visits == 0:
                    return float("inf")
                exploitation = self.value / self.visits
                exploration = c * math.sqrt(math.log(total_visits) / self.visits)
                return exploitation + exploration

        actions = ["skip", "investigate", "experiment", "execute"]
        root = MCTSNode("root")

        for i in range(rollout_budget):
            node = root
            path = []
            depth = 0
            while node.children and depth < 3:
                total = sum(c.visits for c in node.children)
                node = max(node.children, key=lambda c: c.ucb1(max(total, 1)))
                path.append(node)
                depth += 1

            if depth < 3 and node.visits > 0:
                remaining = [a for a in actions if a not in [c.action for c in node.children]]
                if remaining:
                    new_node = MCTSNode(random.choice(remaining), parent=node)
                    node.children.append(new_node)
                    node = new_node

            rollout_action = node
            rollout_value = random.uniform(0, 1)
            if rollout_action.action == "execute":
                rollout_value = random.uniform(0.3, 1.0)
            elif rollout_action.action == "skip":
                rollout_value = random.uniform(0, 0.3)

            while rollout_action:
                rollout_action.visits += 1
                rollout_action.value += rollout_value
                rollout_action = rollout_action.parent

        best_action = max(root.children, key=lambda c: c.visits).action if root.children else "skip"

        return Decision(
            action=best_action,
            utility=utility,
            reasoning=[f"MCTS (budget={rollout_budget}): best action={best_action}"],
            strategy="mcts",
            approved=True,
        )

    @staticmethod
    def active_inference(
        utility: ExpectedUtility,
        observation: Observation,
        **kwargs,
    ) -> Decision:
        uncertainty = observation.uncertainty
        pragmatic_cost = 1.0 - (1.0 - uncertainty)
        epistemic_value = uncertainty * 0.8
        free_energy = pragmatic_cost - epistemic_value

        if free_energy < -0.3:
            return Decision(
                action="investigate",
                utility=utility,
                reasoning=[f"Active inference: G={free_energy:.3f}, high epistemic value"],
                strategy="active_inference",
                approved=True,
            )
        if utility.total > 1.0 and uncertainty < 0.3:
            return Decision(
                action="execute",
                utility=utility,
                reasoning=[f"Active inference: G={free_energy:.3f}, low uncertainty, positive utility"],
                strategy="active_inference",
                approved=True,
            )
        return Decision(
            action="experiment",
            utility=utility,
            reasoning=[f"Active inference: G={free_energy:.3f}, moderate uncertainty"],
            strategy="active_inference",
            approved=True,
        )


class StrategySelector:
    def __init__(self):
        self.performance: dict[str, list[float]] = {
            "expected_utility": [],
            "regret_minimization": [],
            "thompson_sampling": [],
            "mcts": [],
            "active_inference": [],
        }
        self.default_utility: dict[str, float] = {
            "expected_utility": 0.7,
            "regret_minimization": 0.5,
            "thompson_sampling": 0.6,
            "mcts": 0.4,
            "active_inference": 0.3,
        }
        self.epsilon = 0.2

    def select(self, uncertainty: float, budget_remaining: float) -> str:
        available = list(self.performance.keys())
        if not available:
            return "expected_utility"

        if random.random() < self.epsilon:
            chosen = random.choice(available)
            return chosen

        if budget_remaining < 0.2 or uncertainty < 0.15:
            candidates = ["expected_utility", "regret_minimization"]
            scores = [
                (s, self._avg_performance(s))
                for s in candidates if self.performance.get(s)
            ]
            return max(scores, key=lambda x: x[1])[0] if scores else "expected_utility"

        if uncertainty > 0.6:
            candidates = ["active_inference", "thompson_sampling"]

            scores = [
                (s, self._avg_performance(s))
                for s in candidates if self.performance.get(s)
            ]
            return max(scores, key=lambda x: x[1])[0] if scores else "active_inference"

        scores = [
            (s, self._avg_performance(s))
            for s in available if self.performance.get(s)
        ]
        return max(scores, key=lambda x: x[1])[0] if scores else "expected_utility"

    def record_outcome(self, strategy: str, utility: float) -> None:
        if strategy in self.performance:
            self.performance[strategy].append(utility)
            if len(self.performance[strategy]) > 50:
                self.performance[strategy].pop(0)

    def _avg_performance(self, strategy: str) -> float:
        perfs = self.performance.get(strategy, [])
        if perfs:
            return sum(perfs) / len(perfs)
        return self.default_utility.get(strategy, 0.3)

    def summary(self) -> dict:
        return {
            "epsilon": self.epsilon,
            "performance": {
                s: round(self._avg_performance(s), 3)
                for s in self.performance
            },
        }
