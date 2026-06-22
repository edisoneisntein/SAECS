import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from saecs import (
    CognitiveEngine, EventType, MessageBus,
    CausalWorldModel, PlanningEngine, DecisionStrategies, StrategySelector,
    SystemMode, DomainAdapter, DomainSchema, Goal,
)


def main():
    print("=" * 72)
    print("SAECS v4 - Cognitive Architecture for Autonomous Systems")
    print("=" * 72)
    print()

    bus = MessageBus()
    engine = CognitiveEngine(bus)

    from saecs.domains.software import SoftwareDomain
    software = SoftwareDomain(bus)

    print("--- Cycle 1: Observe software project ---")
    r1 = engine.run_cycle(domain_fn=lambda: software.observe())
    print(f"  Events: {r1['events']}")
    print(f"  Director: {r1['director']['budget_used']:.0f} budget used, mode={r1['mode']}")
    print(f"  Causal model: {r1['causal']['nodes']} nodes, {r1['causal'].get('edges', 0)} edges")
    print(f"  Memory: {r1['memory']['episodic']['total']} episodes stored")

    print("\n--- Cycle 2: Observe again ---")
    r2 = engine.run_cycle(domain_fn=lambda: software.observe())
    print(f"  Events: {r2['events']}")
    print(f"  Director strategy: {r2['director']['strategy_selector']['performance']}")
    print(f"  Memory: {r2['memory']['episodic']['total']} episodes")

    print("\n--- Causal Model ---")
    causal = r2.get('causal', {})
    print(f"  Nodes: {causal.get('node_list', [])}")
    print(f"  Leverage points: {causal.get('leverage_points', [])}")

    print("\n--- Planner ---")
    planner = r2.get('planner', {})
    print(f"  Plans: {planner}")

    print("\n--- Create a Goal & Plan ---")
    goal = engine.planner.create_goal(
        description="Improve codebase quality",
        goal_type="improve_attribute",
        target_metrics={"test_coverage": 80},
        priority=0.9,
    )
    print(f"  Goal: {goal.description} (id={goal.id})")

    plan = engine.planner.decompose(goal, engine.causal)
    print(f"  Plan: {plan.id}, {len(plan.steps)} steps")

    for step in plan.steps:
        print(f"    Step: {step.action} -> {step.target} "
              f"(EU={step.expected_utility:.2f}, cost={step.estimated_cost:.0f})")

    print("\n--- Memory Summary ---")
    for tier, data in r2.get('memory', {}).items():
        print(f"  {tier}: {data}")

    print("\n--- Governance ---")
    gov = r2.get('governance', {})
    print(f"  Mode: {gov.get('mode', 'normal')}")
    print(f"  Parameters: {gov.get('parameters', {})}")
    print(f"  Circuit breakers: {len(gov.get('circuit_breakers', []))}")

    episodes = engine.episodic.query()
    semantic_rules = engine.semantic.generalize(episodes)
    print(f"\n  Semantic generalization: {semantic_rules} patterns found")

    print("\n" + "=" * 72)
    print("SAECS v4 operativo. Arquitectura cognitiva completa.")
    print()
    print("Componentes:")
    print("  Governance    - Circuit breakers + Modos de operacion + Principios inmutables")
    print("  Causal        - Grafo causal + prediccion de impacto + efectos secundarios")
    print("  Planner       - Metas + descomposicion + replanificacion")
    print("  Director      - Umbrales aprendibles + seleccion de estrategias")
    print("  Utility       - Pesos evolucionables por experiencia")
    print("  Strategies    - Expected Utility, Regret, Thompson, MCTS, Active Inference")
    print("  Hypothesis    - Generacion con filtro por umbral aprendible")
    print("  Auditor       - Falsacion adversarial con profundidad configurable")
    print("  Executor      - Puntos de restauracion + rollback")
    print("  Memory (3)    - Episodica, Semantica, Estrategica")
    print("  Adapter       - Protocolo formal de dominio (SAECS-011)")
    print()
    print("SAECS-006 a SAECS-012 implementados.")


if __name__ == "__main__":
    main()
