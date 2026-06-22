from __future__ import annotations
import math
from typing import Any

from .types import ExpectedUtility, UtilityTerm


class MultiObjectiveUtility:
    def __init__(self):
        self.objectives: dict[str, Objective] = {
            "performance": Objective("performance", weight=1.0, direction="maximize"),
            "safety": Objective("safety", weight=0.8, direction="maximize"),
            "cost": Objective("cost", weight=0.6, direction="minimize"),
            "risk": Objective("risk", weight=0.7, direction="minimize"),
            "maintainability": Objective("maintainability", weight=0.4, direction="maximize"),
        }

    def compute(self, scores: dict[str, float]) -> MultiObjectiveResult:
        raw = {}
        for name, obj in self.objectives.items():
            s = scores.get(name, 0.0)
            if obj.direction == "minimize":
                s = -s
            raw[name] = s * obj.weight

        return MultiObjectiveResult(
            objective_scores=raw,
            pareto_vector=[raw.get(n, 0.0) for n in self.objectives],
            total=sum(raw.values()),
        )

    def cvar(self, outcomes: list[dict[str, float]], alpha: float = 0.05) -> dict[str, float]:
        if not outcomes:
            return {}
        cvar_scores = {}
        for obj_name in self.objectives:
            vals = sorted(
                o.get(obj_name, 0.0) for o in outcomes
            )
            n_tail = max(1, int(len(vals) * alpha))
            tail = vals[:n_tail]
            cvar_scores[obj_name] = sum(tail) / len(tail)
        return cvar_scores

    def pareto_frontier(
        self, candidates: list[dict[str, float]]
    ) -> list[dict[str, float]]:
        frontier = []
        for i, c in enumerate(candidates):
            dominated = False
            for j, d in enumerate(candidates):
                if i == j:
                    continue
                if all(self._better_or_equal(d, c, obj) for obj in self.objectives.values()) and \
                   any(self._strictly_better(d, c, obj) for obj in self.objectives.values()):
                    dominated = True
                    break
            if not dominated:
                frontier.append(c)
        return frontier

    def _better_or_equal(
        self, a: dict, b: dict, obj: Objective
    ) -> bool:
        val_a = a.get(obj.name, 0.0)
        val_b = b.get(obj.name, 0.0)
        if obj.direction == "maximize":
            return val_a >= val_b
        return val_a <= val_b

    def _strictly_better(self, a: dict, b: dict, obj: Objective) -> bool:
        val_a = a.get(obj.name, 0.0)
        val_b = b.get(obj.name, 0.0)
        if obj.direction == "maximize":
            return val_a > val_b
        return val_a < val_b


class Objective:
    def __init__(
        self, name: str, weight: float = 1.0,
        direction: str = "maximize",
    ):
        self.name = name
        self.weight = weight
        self.direction = direction
        self.learnable = True


class MultiObjectiveResult:
    def __init__(
        self,
        objective_scores: dict[str, float],
        pareto_vector: list[float],
        total: float,
    ):
        self.objective_scores = objective_scores
        self.pareto_vector = pareto_vector
        self.total = total

    def summary(self) -> dict:
        return {
            "objectives": self.objective_scores,
            "pareto_vector": [round(v, 3) for v in self.pareto_vector],
            "total": round(self.total, 3),
        }


class RiskSensitiveUtility:
    @staticmethod
    def exp_utility(utility: ExpectedUtility, risk_aversion: float = 1.0) -> float:
        u = utility.total
        if risk_aversion == 0:
            return u
        return -math.exp(-risk_aversion * u) / risk_aversion

    @staticmethod
    def cvar_utility(
        outcomes: list[float], alpha: float = 0.05
    ) -> float:
        sorted_outcomes = sorted(outcomes)
        n_tail = max(1, int(len(sorted_outcomes) * alpha))
        return sum(sorted_outcomes[:n_tail]) / n_tail

    @staticmethod
    def mean_variance(
        outcomes: list[float], risk_penalty: float = 0.5
    ) -> float:
        mean = sum(outcomes) / max(len(outcomes), 1)
        variance = sum((x - mean) ** 2 for x in outcomes) / max(len(outcomes), 1)
        return mean - risk_penalty * math.sqrt(variance)


class UtilityEvolver:
    def __init__(self, utility: ExpectedUtility):
        self.utility = utility
        self._history: list[dict] = []

    def propose_modification(self, performance_delta: float) -> list[str]:
        changes = []
        for term in self.utility.terms.values():
            if not term.learnable:
                continue
            if performance_delta > 0.1:
                if term.sign == 1:
                    term.weight = min(term.weight * 1.05, term.max_weight)
                    changes.append(f"Increased {term.name} to {term.weight:.2f}")
            elif performance_delta < -0.1:
                if term.sign == -1:
                    term.weight = min(term.weight * 1.05, term.max_weight)
                    changes.append(f"Increased {term.name} penalty to {term.weight:.2f}")
                elif term.weight > 0.1:
                    term.weight = max(term.weight * 0.95, term.min_weight)
                    changes.append(f"Decreased {term.name} to {term.weight:.2f}")

        self._history.append({
            "delta": performance_delta,
            "weights": {n: t.weight for n, t in self.utility.terms.items()},
        })
        return changes

    def summary(self) -> dict:
        return {
            "terms": {n: {"weight": t.weight, "sign": t.sign} for n, t in self.utility.terms.items()},
            "modifications": len(self._history),
        }
