from __future__ import annotations
import math
import random
from collections import defaultdict
from typing import Any

from .bus import MessageBus, Event, EventType
from .types import CausalGraph, CausalEdge, CausalNode


class CausalGraphLearner:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._observation_history: list[dict[str, float]] = []
        self._correlation_matrix: dict[str, dict[str, float]] = defaultdict(dict)
        self._intervention_history: list[dict] = []
        self._candidate_edges: list[dict] = []
        self._min_observations_for_learning: int = 10
        self._correlation_threshold: float = 0.5

        bus.subscribe(EventType.OBSERVATION_READY, self._on_observation)
        bus.subscribe(EventType.EXPERIMENT_COMPLETE, self._on_experiment)

    def _on_observation(self, event: Event) -> None:
        data = event.data
        metrics = data.get("metrics", {})
        domain = event.domain or "generic"
        snapshot = {f"{domain}:{k}": float(v) for k, v in metrics.items()}
        self._observation_history.append(snapshot)
        if len(self._observation_history) >= self._min_observations_for_learning:
            self._update_correlations()

    def _on_experiment(self, event: Event) -> None:
        data = event.data
        self._intervention_history.append({
            "before": data.get("metrics_before", {}),
            "after": data.get("metrics_after", {}),
            "hypothesis_id": data.get("hypothesis_id", ""),
        })

    def _update_correlations(self) -> None:
        history = self._observation_history[-100:]
        if len(history) < 5:
            return

        variables = set()
        for snapshot in history:
            variables.update(snapshot.keys())

        for v1 in variables:
            for v2 in variables:
                if v1 >= v2:
                    continue
                vals1 = [s.get(v1, 0) for s in history]
                vals2 = [s.get(v2, 0) for s in history]
                corr = self._pearson(vals1, vals2)
                self._correlation_matrix[v1][v2] = corr
                self._correlation_matrix[v2][v1] = corr

                if abs(corr) > self._correlation_threshold:
                    direction = "positive" if corr > 0 else "negative"
                    self._candidate_edges.append({
                        "source": v1,
                        "target": v2,
                        "correlation": corr,
                        "direction": direction,
                        "evidence_strength": abs(corr),
                    })

    def _pearson(self, xs: list[float], ys: list[float]) -> float:
        n = min(len(xs), len(ys))
        if n < 3:
            return 0.0
        xs, ys = xs[-n:], ys[-n:]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = math.sqrt(
            sum((x - mean_x) ** 2 for x in xs)
            * sum((y - mean_y) ** 2 for y in ys)
        )
        return num / max(den, 0.001)

    def propose_edges(self, graph: CausalGraph, top_k: int = 5) -> list[dict]:
        existing_pairs = {(e.source, e.target) for e in graph.edges}
        candidates = [
            c for c in self._candidate_edges
            if (c["source"], c["target"]) not in existing_pairs
            and (c["target"], c["source"]) not in existing_pairs
        ]
        candidates.sort(key=lambda c: c["evidence_strength"], reverse=True)

        intervention_confirmed = self._infer_from_interventions(graph)
        for ic in intervention_confirmed:
            if ic not in candidates:
                candidates.append(ic)

        return candidates[:top_k]

    def _infer_from_interventions(self, graph: CausalGraph) -> list[dict]:
        confirmed = []
        for intervention in self._intervention_history[-20:]:
            before = intervention.get("before", {})
            after = intervention.get("after", {})
            changed_vars = {
                k for k in after
                if abs(after.get(k, 0) - before.get(k, 0)) > 0.01
            }
            if len(changed_vars) >= 2:
                changed_list = list(changed_vars)
                for i in range(len(changed_list)):
                    for j in range(i + 1, len(changed_list)):
                        confirmed.append({
                            "source": changed_list[i],
                            "target": changed_list[j],
                            "correlation": 0.8,
                            "direction": "positive",
                            "evidence_strength": 0.8,
                            "source_type": "intervention_inferred",
                        })
        return confirmed

    def apply_learned_edges(
        self, graph: CausalGraph, max_new_edges: int = 3
    ) -> list[str]:
        candidates = self.propose_edges(graph, top_k=max_new_edges)
        applied = []
        for c in candidates[:max_new_edges]:
            source = c["source"]
            target = c["target"]
            if source not in graph.nodes:
                graph.add_node(source, is_observable=True)
            if target not in graph.nodes:
                graph.add_node(target, is_observable=True)
            strength = min(abs(c.get("correlation", 0.5)), 0.95)
            graph.add_edge(
                source=source,
                target=target,
                strength=strength,
                uncertainty=max(0.1, 1.0 - strength),
                learned_from="structural_learning",
                samples=1,
            )
            applied.append(f"{source} -> {target} (r={strength:.2f})")

        if applied:
            self.bus.publish(Event(
                type=EventType.PATTERN_FOUND,
                source="causal_graph_learner",
                data={
                    "topic": "causal_structure",
                    "rule": "; ".join(applied),
                    "evidence": f"Learned from {len(self._observation_history)} observations",
                    "confidence": 0.7,
                },
            ))

        return applied

    def remove_weak_edges(self, graph: CausalGraph, min_strength: float = 0.1) -> int:
        removed = 0
        for edge in list(graph.edges):
            if edge.samples > 5 and edge.strength < min_strength:
                graph.edges.remove(edge)
                removed += 1
        return removed

    def summary(self) -> dict:
        return {
            "observations_analyzed": len(self._observation_history),
            "interventions_analyzed": len(self._intervention_history),
            "correlations_computed": sum(len(v) for v in self._correlation_matrix.values()),
            "candidate_edges": len(self._candidate_edges),
            "threshold": self._correlation_threshold,
        }
