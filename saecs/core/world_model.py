from __future__ import annotations
import math
import random
from copy import deepcopy
from typing import Any
from collections import defaultdict

from .bus import MessageBus, Event, EventType, EventPriority
from .types import CausalGraph, CausalNode, CausalEdge, DomainState


class WorldState:
    def __init__(self, variables: dict[str, float] | None = None):
        self.variables: dict[str, float] = variables or {}
        self.timestamp: float = 0.0
        self.metadata: dict[str, Any] = {}

    def copy(self) -> WorldState:
        ws = WorldState(variables=dict(self.variables))
        ws.timestamp = self.timestamp
        ws.metadata = dict(self.metadata)
        return ws

    def snapshot(self) -> dict:
        return {
            "variables": dict(self.variables),
            "timestamp": self.timestamp,
        }


class SimulationResult:
    def __init__(
        self,
        next_state: WorldState,
        reward: float = 0.0,
        risk: float = 0.0,
        confidence: float = 1.0,
        side_effects: list[dict] | None = None,
        success_probability: float = 1.0,
        info: dict | None = None,
    ):
        self.next_state = next_state
        self.reward = reward
        self.risk = risk
        self.confidence = confidence
        self.side_effects = side_effects or []
        self.success_probability = success_probability
        self.info = info or {}


class WorldModel:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.causal = CausalGraph()
        self.current_state = WorldState()
        self.state_history: list[WorldState] = []
        self.transition_model: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._epistemic_uncertainty: dict[str, float] = {}
        self._simulation_cache: dict[str, SimulationResult] = {}

        bus.subscribe(EventType.OBSERVATION_READY, self._on_observation)
        bus.subscribe(EventType.EXPERIMENT_COMPLETE, self._on_experiment)
        bus.subscribe(EventType.EXECUTION_SUCCESS, self._on_execution)

    def _on_observation(self, event: Event) -> None:
        data = event.data
        metrics = data.get("metrics", {})
        domain = event.domain or "generic"
        for name, value in metrics.items():
            var_name = f"{domain}:{name}"
            self.current_state.variables[var_name] = float(value)
            if var_name not in self.causal.nodes:
                self.causal.add_node(
                    name=var_name,
                    value=float(value),
                    uncertainty=data.get("uncertainty", 0.5),
                )
            else:
                node = self.causal.nodes[var_name]
                delta = abs(value - node.value) / max(abs(node.value), 0.01)
                node.uncertainty = max(0.05, node.uncertainty * 0.9 + delta * 0.1)
                node.value = float(value)

        self.current_state.timestamp = len(self.state_history)
        self.state_history.append(self.current_state.copy())

    def _on_experiment(self, event: Event) -> None:
        data = event.data
        metrics_before = data.get("metrics_before", {})
        metrics_after = data.get("metrics_after", {})
        self._learn_transition(metrics_before, metrics_after)

    def _on_execution(self, event: Event) -> None:
        data = event.data
        self.bus.publish(Event(
            type=EventType.CYCLE_COMPLETE,
            source="world_model",
            data={"state": self.current_state.snapshot()},
        ))

    def _learn_transition(self, before: dict, after: dict) -> None:
        for var, val_before in before.items():
            val_after = after.get(var, val_before)
            delta = val_after - val_before
            self.transition_model[var].append((val_before, delta))
            if len(self.transition_model[var]) > 100:
                self.transition_model[var].pop(0)

    def update_state(self, variable: str, delta: float) -> None:
        old = self.current_state.variables.get(variable, 0.0)
        self.current_state.variables[variable] = old + delta
        if variable in self.causal.nodes:
            self.causal.nodes[variable].value = old + delta

    def simulate(
        self,
        action: dict,
        horizon: int = 3,
        noise: float = 0.05,
    ) -> SimulationResult:
        action_type = action.get("action", "unknown")
        target = action.get("target", "")
        delta = action.get("delta", 0.1)

        cache_key = f"{action_type}:{target}:{delta}:{horizon}"
        if cache_key in self._simulation_cache:
            return self._simulation_cache[cache_key]

        sim_state = self.current_state.copy()

        if target in sim_state.variables or target in self.causal.nodes:
            var_name = target if target in sim_state.variables else target
            sim_state.variables[var_name] = sim_state.variables.get(var_name, 0.0) + delta

            if target in self.causal.nodes:
                predictions = self._propagate_impact(target, delta, sim_state, horizon)
                for var, impact in predictions.items():
                    sim_state.variables[var] = sim_state.variables.get(var, 0.0) + impact

        side_effects = self._detect_side_effects(action, delta, sim_state)
        success_prob = self._estimate_success_probability(action, delta)
        risk = self._estimate_risk(action, delta, side_effects)
        reward = self._estimate_reward(action, sim_state)
        confidence = self._estimate_confidence(action, delta, success_prob)

        for var in sim_state.variables:
            noise_val = random.gauss(0, noise * abs(sim_state.variables[var] + 0.01))
            sim_state.variables[var] += noise_val

        sim_state.timestamp = self.current_state.timestamp + 1

        result = SimulationResult(
            next_state=sim_state,
            reward=reward,
            risk=risk,
            confidence=confidence,
            side_effects=side_effects,
            success_probability=success_prob,
            info={
                "action": action_type,
                "target": target,
                "horizon": horizon,
                "state_variables": len(sim_state.variables),
            },
        )

        if len(self._simulation_cache) < 500:
            self._simulation_cache[cache_key] = result

        return result

    def _propagate_impact(
        self, source: str, delta: float, state: WorldState, depth: int
    ) -> dict[str, float]:
        predictions: dict[str, float] = {}
        visited: set[str] = set()

        def _walk(current: str, impact: float, remaining: int):
            if remaining <= 0 or current in visited:
                return
            visited.add(current)
            for edge in self.causal.get_children(current):
                if edge.target in visited:
                    continue
                propagated = impact * edge.strength * (1.0 - edge.uncertainty)
                predictions[edge.target] = predictions.get(edge.target, 0.0) + propagated
                _walk(edge.target, propagated, remaining - 1)

        _walk(source, delta, depth)
        return predictions

    def _detect_side_effects(
        self, action: dict, delta: float, sim_state: WorldState
    ) -> list[dict]:
        effects = []
        target = action.get("target", "")
        predictions = self._propagate_impact(target, delta, sim_state, 3)
        for var, impact in predictions.items():
            if var != target and abs(impact) > 0.05:
                effects.append({
                    "variable": var,
                    "predicted_delta": round(impact, 4),
                    "severity": "high" if abs(impact) > 0.3 else "low",
                })
        return effects

    def _estimate_success_probability(self, action: dict, delta: float) -> float:
        target = action.get("target", "")
        if target in self.transition_model:
            transitions = self.transition_model[target]
            if len(transitions) >= 3:
                recent = transitions[-3:]
                consistent = sum(
                    1 for b, d in recent if abs(d - delta) < abs(delta * 0.5 + 0.01)
                )
                return 0.5 + (consistent / len(recent)) * 0.5
        if target in self.causal.nodes:
            return 1.0 - self.causal.nodes[target].uncertainty
        return 0.7

    def _estimate_risk(self, action: dict, delta: float, side_effects: list[dict]) -> float:
        base_risk = 0.1
        for effect in side_effects:
            if effect["severity"] == "high":
                base_risk += 0.2
            else:
                base_risk += 0.05
        target = action.get("target", "")
        if target in self.causal.nodes:
            base_risk += self.causal.nodes[target].uncertainty * 0.3
        return min(base_risk, 0.95)

    def _estimate_reward(self, action: dict, sim_state: WorldState) -> float:
        target = action.get("target", "")
        current = self.current_state.variables.get(target, 0.0)
        future = sim_state.variables.get(target, 0.0)
        improvement = future - current
        reward = improvement
        for effect in self._detect_side_effects(action, improvement, sim_state):
            if effect["severity"] == "high":
                reward -= abs(effect["predicted_delta"]) * 0.5
        return reward

    def _estimate_confidence(self, action: dict, delta: float, success_prob: float) -> float:
        target = action.get("target", "")
        if target in self._epistemic_uncertainty:
            epistemic = self._epistemic_uncertainty[target]
        else:
            epistemic = 0.3
        if target in self.causal.nodes:
            aleatoric = self.causal.nodes[target].uncertainty
        else:
            aleatoric = 0.5
        confidence = success_prob * (1.0 - epistemic) * (1.0 - aleatoric * 0.5)
        return max(0.05, min(confidence, 0.99))

    def rollback(self, steps: int = 1) -> bool:
        if len(self.state_history) < steps:
            return False
        target_idx = max(0, len(self.state_history) - steps - 1)
        self.current_state = self.state_history[target_idx].copy()
        self.state_history = self.state_history[:target_idx + 1]
        for var, val in self.current_state.variables.items():
            if var in self.causal.nodes:
                self.causal.nodes[var].value = val
        return True

    def get_state_at(self, var: str) -> tuple[float, float]:
        val = self.current_state.variables.get(var, 0.0)
        node = self.causal.nodes.get(var)
        uncertainty = node.uncertainty if node else 0.5
        return val, uncertainty

    def compare_scenarios(
        self, actions: list[dict]
    ) -> list[tuple[dict, SimulationResult]]:
        results = []
        for action in actions:
            sim = self.simulate(action)
            results.append((action, sim))
        return sorted(results, key=lambda x: x[1].reward, reverse=True)

    def find_leverage_points(self) -> list[dict]:
        scores = []
        for name, node in self.causal.nodes.items():
            if not node.is_intervenible:
                continue
            children = self.causal.get_children(name)
            total_impact = sum(e.strength * (1.0 - e.uncertainty) for e in children)
            uncertainty_reduction = node.uncertainty
            score = total_impact * (1.0 + uncertainty_reduction)
            scores.append({
                "node": name,
                "score": round(score, 3),
                "impact": round(total_impact, 3),
                "uncertainty": round(node.uncertainty, 3),
            })
        return sorted(scores, key=lambda x: x["score"], reverse=True)

    def trace_root_causes(self, target_metric: str) -> list[dict]:
        causes = []
        for edge in self.causal.edges:
            if edge.target == target_metric:
                upstream = self._trace_upstream(edge.source)
                for cause in upstream:
                    if cause["node"] not in [c["node"] for c in causes]:
                        causes.append(cause)
        return sorted(causes, key=lambda x: x["path_strength"], reverse=True)

    def _trace_upstream(self, node_name: str, depth: int = 5) -> list[dict]:
        results = []
        visited = set()
        def _walk(current: str, path_strength: float, remaining: int):
            if remaining <= 0 or current in visited:
                return
            visited.add(current)
            parents = self.causal.get_parents(current)
            if not parents:
                results.append({"node": current, "path_strength": round(path_strength, 3)})
            for edge in parents:
                _walk(edge.source, path_strength * edge.strength * (1.0 - edge.uncertainty), remaining - 1)
        _walk(node_name, 1.0, depth)
        return results

    def detect_side_effects(self, node_name: str, delta: float) -> list[dict]:
        predictions = self._propagate_impact(node_name, delta, self.current_state, 3)
        side_effects = []
        for target, impact in predictions.items():
            if target != node_name and abs(impact) > 0.1:
                side_effects.append({
                    "target": target,
                    "predicted_impact": round(impact, 3),
                    "severity": "high" if abs(impact) > 0.5 else "medium",
                })
        return sorted(side_effects, key=lambda x: abs(x["predicted_impact"]), reverse=True)

    def learn_from_intervention(self, intervened_node: str, observed_deltas: dict[str, float]) -> None:
        for target, delta in observed_deltas.items():
            if target == intervened_node:
                continue
            existing = [
                e for e in self.causal.edges
                if e.source == intervened_node and e.target == target
            ]
            if existing:
                edge = existing[0]
                edge.strength = 0.7 * edge.strength + 0.3 * min(abs(delta), 1.0)
                edge.uncertainty = max(0.1, edge.uncertainty * 0.85)
                edge.samples += 1
            else:
                if abs(delta) > 0.05:
                    self.causal.add_edge(
                        source=intervened_node,
                        target=target,
                        strength=min(abs(delta), 1.0),
                        uncertainty=0.5,
                        learned_from="intervention",
                        samples=1,
                    )

    def causal_summary(self) -> dict:
        return {
            "nodes": len(self.causal.nodes),
            "edges": len(self.causal.edges),
            "node_list": list(self.causal.nodes.keys()),
            "leverage_points": self.find_leverage_points()[:3],
        }

    def summary(self) -> dict:
        return {
            "variables": len(self.current_state.variables),
            "state_history": len(self.state_history),
            "causal_nodes": len(self.causal.nodes),
            "causal_edges": len(self.causal.edges),
            "transition_models": len(self.transition_model),
            "simulation_cache": len(self._simulation_cache),
            "current_state": dict(self.current_state.variables),
        }
