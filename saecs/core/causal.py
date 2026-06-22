from __future__ import annotations
import math
from typing import Any
from .bus import MessageBus, Event, EventType, EventPriority
from .types import CausalGraph, CausalNode, CausalEdge, DomainState


class CausalWorldModel:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.graph = CausalGraph()
        bus.subscribe(EventType.OBSERVATION_READY, self._on_observation)
        bus.subscribe(EventType.EXPERIMENT_COMPLETE, self._on_experiment)

    def _on_observation(self, event: Event) -> None:
        data = event.data
        metrics = data.get("metrics", {})
        domain = event.domain or "generic"
        for name, value in metrics.items():
            node_name = f"{domain}:{name}"
            if node_name not in self.graph.nodes:
                self.graph.add_node(
                    name=node_name,
                    value=float(value),
                    uncertainty=data.get("uncertainty", 0.5),
                    is_observable=True,
                    is_intervenible=True,
                )
            else:
                node = self.graph.nodes[node_name]
                old_value = node.value
                node.value = float(value)
                delta = abs(value - old_value) / max(abs(old_value), 0.01)
                node.uncertainty = max(0.1, node.uncertainty * 0.9 + delta * 0.1)

    def _on_experiment(self, event: Event) -> None:
        data = event.data
        domain = event.domain or "generic"
        metrics_before = data.get("metrics_before", {})
        metrics_after = data.get("metrics_after", {})

        for name in metrics_after:
            before = metrics_before.get(name, 0)
            after = metrics_after.get(name, 0)
            delta = after - before
            node_name = f"{domain}:{name}"

            if node_name in self.graph.nodes and abs(delta) > 0.001:
                node = self.graph.nodes[node_name]
                evidence_magnitude = abs(delta) / max(abs(before), 0.01)

                for edge in self.graph.edges:
                    if edge.target == node_name:
                        edge.strength = 0.7 * edge.strength + 0.3 * evidence_magnitude
                        edge.uncertainty *= 0.9
                        edge.samples += 1

    def learn_from_intervention(self, intervened_node: str, observed_deltas: dict[str, float]) -> None:
        for target, delta in observed_deltas.items():
            if target == intervened_node:
                continue
            existing = [
                e for e in self.graph.edges
                if e.source == intervened_node and e.target == target
            ]
            if existing:
                edge = existing[0]
                old_strength = edge.strength
                edge.strength = 0.7 * edge.strength + 0.3 * min(abs(delta), 1.0)
                edge.uncertainty = max(0.1, edge.uncertainty * 0.85)
                edge.samples += 1
            else:
                if abs(delta) > 0.05:
                    self.graph.add_edge(
                        source=intervened_node,
                        target=target,
                        strength=min(abs(delta), 1.0),
                        uncertainty=0.5,
                        learned_from="intervention",
                        samples=1,
                    )

    def predict_impact(self, node_name: str, delta: float, depth: int = 3) -> dict[str, float]:
        predictions: dict[str, float] = {node_name: delta}
        visited: set[str] = set()

        def _propagate(current: str, impact: float, remaining: int):
            if remaining <= 0 or current in visited:
                return
            visited.add(current)
            for edge in self.graph.get_children(current):
                propagated = impact * edge.strength * (1.0 - edge.uncertainty)
                predictions[edge.target] = predictions.get(edge.target, 0.0) + propagated
                _propagate(edge.target, propagated, remaining - 1)

        _propagate(node_name, delta, depth)
        return predictions

    def detect_side_effects(self, node_name: str, delta: float) -> list[dict]:
        predictions = self.predict_impact(node_name, delta)
        side_effects = []
        for target, impact in predictions.items():
            if target != node_name and abs(impact) > 0.1:
                side_effects.append({
                    "target": target,
                    "predicted_impact": round(impact, 3),
                    "severity": "high" if abs(impact) > 0.5 else "medium",
                })
        return sorted(side_effects, key=lambda x: abs(x["predicted_impact"]), reverse=True)

    def find_leverage_points(self) -> list[dict]:
        scores = []
        for name, node in self.graph.nodes.items():
            if not node.is_intervenible:
                continue
            children = self.graph.get_children(name)
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
        for edge in self.graph.edges:
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
            parents = self.graph.get_parents(current)
            if not parents:
                results.append({"node": current, "path_strength": round(path_strength, 3)})
            for edge in parents:
                _walk(edge.source, path_strength * edge.strength * (1.0 - edge.uncertainty), remaining - 1)
        _walk(node_name, 1.0, depth)
        return results

    def compute_uncertainty_of(self, node_name: str) -> float:
        if node_name not in self.graph.nodes:
            return 1.0
        node = self.graph.nodes[node_name]
        parents = self.graph.get_parents(node_name)
        if not parents:
            return node.uncertainty
        parent_uncertainty = sum(
            p.uncertainty * p.strength for p in parents
        ) / max(sum(p.strength for p in parents), 0.01)
        return 0.5 * node.uncertainty + 0.5 * parent_uncertainty

    def summary(self) -> dict:
        return {
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "node_list": list(self.graph.nodes.keys()),
            "leverage_points": self.find_leverage_points()[:3],
        }
