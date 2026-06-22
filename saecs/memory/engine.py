from ..core.bus import MessageBus, Event, EventType
from ..core.types import ExpectedUtility, Observation, SystemMode
from ..core.director import Director
from ..core.utility import UtilityEstimator
from ..core.hypothesis import HypothesisGenerator
from ..core.experimenter import Experimenter
from ..core.auditor import Auditor
from ..core.executor import Executor
from ..core.governance import CognitiveGovernance
from ..core.planner import PlanningEngine
from ..core.strategies import StrategySelector
from ..core.world_model import WorldModel
from ..core.calibration import CalibrationTracker
from ..core.learning import CausalGraphLearner
from ..core.multiobjective import MultiObjectiveUtility, RiskSensitiveUtility, UtilityEvolver
from ..core.evidence import EvidenceGraph
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .strategic import StrategicMemory


class CognitiveEngine:
    def __init__(self, bus: MessageBus, memory_path: str = ".saecs"):
        self.bus = bus

        self.episodic = EpisodicMemory(bus, f"{memory_path}/episodic")
        self.semantic = SemanticMemory(bus, f"{memory_path}/semantic")
        self.strategic = StrategicMemory(bus, f"{memory_path}/strategic")

        self.utility = UtilityEstimator(bus)
        self.world_model = WorldModel(bus)
        self.planner = PlanningEngine(bus, causal_model=self.world_model)
        self.director = Director(bus, self.utility)
        self.hypothesis = HypothesisGenerator(bus)
        self.experimenter = Experimenter(bus)
        self.auditor = Auditor(bus)
        self.executor = Executor(bus)
        self.governance = CognitiveGovernance(bus)

        self.calibration = CalibrationTracker(bus, f"{memory_path}/calibration")
        self.graph_learner = CausalGraphLearner(bus)
        self.multi_objective = MultiObjectiveUtility()
        self.utility_evolver = UtilityEvolver(self.utility.utility)
        self.evidence_graph = EvidenceGraph()

        self.cycle_count = 0
        bus.subscribe(EventType.OBSERVATION_READY, self._on_observation_ready)
        bus.subscribe(EventType.HYPOTHESES_GENERATED, self._on_hypotheses_generated)

    @property
    def mode(self) -> SystemMode:
        return self.governance.mode

    def run_cycle(self, domain_fn=None) -> dict:
        self.cycle_count += 1

        if self.governance.mode == SystemMode.SHUTDOWN:
            return {
                "cycle": f"C{self.cycle_count}",
                "error": "System in SHUTDOWN mode",
                "mode": "shutdown",
            }

        if self.governance.mode == SystemMode.QUARANTINE:
            _ = self.bus.get_history(limit=5)
            return {
                "cycle": f"C{self.cycle_count}",
                "mode": "quarantine",
                "error": "System in QUARANTINE mode, no actions allowed",
            }

        cid = self.director.start_cycle()

        if domain_fn:
            domain_fn()

        new_edges = self.graph_learner.apply_learned_edges(
            self.world_model.causal, max_new_edges=2
        )
        if new_edges:
            self.episodic.store(
                event_type="causal_learning",
                description=f"Learned edges: {', '.join(new_edges)}",
                outcome="completed",
                domain="core",
                metadata={"edges": new_edges},
            )

        if self.planner.active_plans:
            for plan_id in list(self.planner.active_plans.keys()):
                self.planner.execute_next(plan_id, self.director)

        removed = self.graph_learner.remove_weak_edges(self.world_model.causal)
        if removed:
            self.episodic.store(
                event_type="causal_pruning",
                description=f"Removed {removed} weak edges",
                outcome="completed",
                domain="core",
            )

        events = self.bus.get_history(limit=30)
        result = {
            "cycle": f"C{self.cycle_count}",
            "cid": cid,
            "mode": self.governance.mode.value,
            "events": len(events),
            "director": self.director.summary(),
            "causal": self.world_model.causal_summary(),
            "world_model": self.world_model.summary(),
            "planner": self.planner.summary(),
            "calibration": self.calibration.summary(),
            "graph_learner": self.graph_learner.summary(),
            "utility_evolver": self.utility_evolver.summary(),
            "evidence": self.evidence_graph.summary(),
            "memory": {
                "episodic": self.episodic.summary(),
                "semantic": self.semantic.summary(),
                "strategic": self.strategic.summary(),
            },
            "governance": self.governance.summary(),
        }

        episode_data = {
            k: v for k, v in result.items()
            if k in ("cycle", "mode", "events", "director")
        }
        self.episodic.store(
            event_type="cycle_complete",
            description=f"Cycle {self.cycle_count} complete",
            outcome="completed",
            domain="core",
            metadata=episode_data,
        )

        return result

    def simulate_action(self, action: dict) -> dict:
        sim = self.world_model.simulate(action)
        return {
            "action": action,
            "reward": round(sim.reward, 3),
            "risk": round(sim.risk, 3),
            "confidence": round(sim.confidence, 3),
            "success_probability": round(sim.success_probability, 3),
            "side_effects": sim.side_effects,
            "predicted_state": sim.next_state.snapshot(),
        }

    def compare_actions(self, actions: list[dict]) -> list[dict]:
        results = self.world_model.compare_scenarios(actions)
        return [
            {
                "action": a,
                "reward": round(s.reward, 3),
                "risk": round(s.risk, 3),
                "confidence": round(s.confidence, 3),
            }
            for a, s in results
        ]

    def multi_objective_evaluate(self, scores: dict[str, float]) -> dict:
        result = self.multi_objective.compute(scores)
        return result.summary()

    def summary(self) -> dict:
        return {
            "cycle_count": self.cycle_count,
            "mode": self.governance.mode.value,
            "director": self.director.summary(),
            "causal": self.world_model.causal_summary(),
            "world_model": self.world_model.summary(),
            "planner": self.planner.summary(),
            "calibration": self.calibration.summary(),
            "graph_learner": self.graph_learner.summary(),
            "utility_evolver": self.utility_evolver.summary(),
            "evidence": self.evidence_graph.summary(),
            "memory": {
                "episodic": self.episodic.summary(),
                "semantic": self.semantic.summary(),
                "strategic": self.strategic.summary(),
            },
            "governance": self.governance.summary(),
        }

    def _on_observation_ready(self, event: Event) -> None:
        evidence = event.data.get("evidence", [])
        for claim in evidence:
            self.evidence_graph.add(
                claim=str(claim),
                source=event.source,
                kind="observation",
                strength=0.6,
                confidence=max(0.1, 1.0 - float(event.data.get("uncertainty", 0.5))),
                metadata={"domain": event.domain, "correlation_id": event.correlation_id},
            )

    def _on_hypotheses_generated(self, event: Event) -> None:
        recent = list(self.evidence_graph.items.values())[-10:]
        for hypothesis in event.data.get("hypotheses", []):
            hid = hypothesis.get("id")
            if not hid:
                continue
            for item in recent:
                self.evidence_graph.link_support(item.id, hid)
