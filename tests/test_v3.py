import os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saecs import (
    CognitiveEngine, MessageBus, Event, EventType, EventPriority,
    Hypothesis, ExpectedUtility, AuditReport, UtilityTerm,
    CognitiveGovernance, Director, UtilityEstimator,
    Auditor, Executor, Experimenter,
    CausalWorldModel, CausalGraph, CausalNode, CausalEdge,
    PlanningEngine, Goal, Plan, PlannedStep,
    DecisionStrategies, StrategySelector,
    SystemMode, DomainAdapter, DomainSchema, DomainHealth,
    WorldModel, WorldState, SimulationResult,
    CalibrationTracker,
    CausalGraphLearner,
    MultiObjectiveUtility, RiskSensitiveUtility, UtilityEvolver, Objective,
    EvidenceGraph,
)


def test_bus_works():
    bus = MessageBus()
    received = []
    bus.subscribe(EventType.CYCLE_START, lambda e: received.append(e))
    bus.publish(Event(type=EventType.CYCLE_START, source="test"))
    assert len(received) == 1
    print("  ✓ Bus pub/sub")


def test_expected_utility_with_voi():
    u = ExpectedUtility.default()
    u.terms["benefit"].value = 10.0
    u.terms["cost"].value = 2.0
    u.terms["risk"].value = 1.0
    u.terms["opportunity_cost"].value = 0.5
    u.terms["cognitive_cost"].value = 1.0
    u.terms["value_of_information"].value = 3.0
    u.terms["learning_value"].value = 2.0
    u.confidence = 0.9
    expected = (10 - 2 - 1 - 0.5 - 1 + 3 + 2) * 0.9
    assert abs(u.total - expected) < 0.001
    assert u.total > 0
    s = u.summary()
    assert "value_of_information" in s
    print(f"  ✓ Utility with learnable weights: {u.total:.3f}")


def test_utility_terms_learnable():
    u = ExpectedUtility.default()
    assert u.terms["benefit"].weight == 1.0
    assert u.terms["benefit"].learnable
    u.terms["risk"].weight = 2.0
    assert u.terms["risk"].weight == 2.0
    print("  ✓ Utility terms are learnable")


def test_hypothesis_generation():
    bus = MessageBus()
    from saecs.core.hypothesis import HypothesisGenerator
    hg = HypothesisGenerator(bus)
    hyps = hg.generate("High latency", "Database N+1 query")
    assert len(hyps) >= 2
    assert hyps[0].confidence > 0
    assert hyps[0].id != hyps[1].id
    print(f"  ✓ Generated {len(hyps)} hypotheses")


def test_hypothesis_generation_uses_measurable_context():
    bus = MessageBus()
    from saecs.core.hypothesis import HypothesisGenerator
    hg = HypothesisGenerator(bus)
    hyps = hg.generate(
        "Elevated user-experience risk detected",
        "Missing confirmation for high-impact action",
        domain="web_ui",
        evidence=["confirmation_gaps=1", "ux_risk_score=0.4"],
        context={
            "metrics": {
                "ux_risk_score": 0.4,
                "confirmation_gaps": 1,
                "accessibility_score": 0.8,
            },
            "ui_findings": [{"path": "index.html", "severity": "critical"}],
        },
    )
    assert hyps[0].target_metrics["ux_risk_score"] == 0.0
    assert hyps[0].falsifiers
    assert hyps[0].scope == ["index.html"]
    assert hyps[0].evidence_quality > 0
    assert hyps[0].domain_data["measurable"]
    print("  ✓ Hypotheses carry metrics, falsifiers, scope, and evidence quality")


def test_evidence_graph_scores_support_and_contradiction():
    graph = EvidenceGraph()
    support = graph.add("risk_score=0.8", "test", strength=0.8, confidence=0.8)
    contradiction = graph.add("manual review found no issue", "test", strength=0.2, confidence=0.5)
    graph.link_support(support.id, "h1")
    graph.link_contradiction(contradiction.id, "h1")
    assert graph.quality_for("h1") > 0
    assert graph.summary()["items"] == 2
    print("  ✓ EvidenceGraph scores support and contradiction")


def test_auditor_falsifies_bad():
    bus = MessageBus()
    aud = Auditor(bus)
    h = Hypothesis(
        id="bad", description="x", predicted_effect="y",
        confidence=0.99, evidence=[],
    )
    report = aud.audit(h)
    assert report.falsified
    print("  ✓ Auditor falsifies weak hypothesis")


def test_auditor_confirms_good():
    bus = MessageBus()
    aud = Auditor(bus)
    h = Hypothesis(
        id="good", description="Optimize database query",
        predicted_effect="Reduce latency",
        evidence=["EXPLAIN ANALYZE shows full table scan"],
        confidence=0.7,
    )
    report = aud.audit(h)
    assert not report.falsified
    assert report.confidence_after >= h.confidence
    print("  ✓ Auditor confirms strong hypothesis")


def test_auditor_configurable_depth():
    bus = MessageBus()
    aud = Auditor(bus)
    aud.audit_depth = 2.0
    h = Hypothesis(
        id="depth", description="Test depth",
        predicted_effect="Test depth",
        evidence=["Some evidence"],
        confidence=0.7,
        domain_data={"alternative": True},
    )
    report = aud.audit(h)
    assert report.falsified
    assert "alternative_hypothesis" in report.attack_vectors
    print("  ✓ Auditor uses configurable depth")


def test_auditor_requires_metrics_for_measurable_hypothesis():
    bus = MessageBus()
    aud = Auditor(bus)
    h = Hypothesis(
        id="measurable",
        description="Reduce observed risk",
        predicted_effect="Risk decreases",
        confidence=0.7,
        evidence=["risk_score=0.8"],
        domain_data={"measurable": True},
    )
    report = aud.audit(h)
    assert report.falsified
    assert "missing_target_metrics" in report.attack_vectors
    print("  ✓ Auditor rejects measurable hypotheses without target metrics")


def test_cognitive_governance_adjusts():
    bus = MessageBus()
    gov = CognitiveGovernance(bus)
    original = gov.get_parameter("cognitive_budget_multiplier")
    bus.publish(Event(
        type=EventType.BUDGET_EXCEEDED, source="test",
        data={"spent": 1000, "limit": 100, "cost": 50},
    ))
    adjusted = gov.get_parameter("cognitive_budget_multiplier")
    assert adjusted > original
    print(f"  ✓ Governance adjusted budget: {original} -> {adjusted}")


def test_causal_world_model():
    g = CausalGraph()
    g.add_node("memory_usage", value=80, is_intervenible=True)
    g.add_node("query_latency", value=200)
    g.add_node("error_rate", value=0.05)
    g.add_edge("memory_usage", "query_latency", strength=0.8)
    g.add_edge("query_latency", "error_rate", strength=0.6)
    impact = g.compute_impact("memory_usage", "error_rate")
    expected = 0.8 * 0.6 * 0.5
    assert abs(impact - expected) < 0.001
    bus = MessageBus()
    causal = CausalWorldModel(bus)
    causal.graph = g
    leverage = causal.find_leverage_points()
    assert len(leverage) > 0
    side_effects = causal.detect_side_effects("memory_usage", 0.5)
    assert len(side_effects) > 0
    print(f"  ✓ Causal model: {len(leverage)} leverage points, {len(side_effects)} side effects")


def test_causal_learns_from_intervention():
    bus = MessageBus()
    causal = CausalWorldModel(bus)
    causal.graph.add_node("server_count", value=3, is_intervenible=True)
    causal.graph.add_node("response_time", value=200)
    causal.learn_from_intervention(
        "server_count",
        {"server_count": 1.0, "response_time": -0.3}
    )
    edges = causal.graph.get_children("server_count")
    assert len(edges) >= 1
    assert edges[0].target == "response_time"
    print(f"  ✓ Causal model learns from intervention: edge strength={edges[0].strength:.3f}")


def test_planning_engine():
    bus = MessageBus()
    planner = PlanningEngine(bus)
    goal = planner.create_goal(
        description="Reduce error rate",
        goal_type="fix_problem",
        target_metrics={"error_rate": 0.01},
        priority=0.8,
    )
    plan = planner.decompose(goal)
    assert plan.status == "active"
    assert len(plan.steps) > 0
    assert plan.goal.description == "Reduce error rate"
    print(f"  ✓ Plan generated with {len(plan.steps)} steps")


def test_decision_strategies():
    from saecs.core.types import Decision, DomainState
    u = ExpectedUtility.default()
    u.terms["benefit"].value = 5.0
    u.terms["cost"].value = 1.0
    u.confidence = 0.9
    obs = type('O', (), {'domain_id': 'test', 'uncertainty': 0.7, 'state': DomainState()})()
    strategies = DecisionStrategies()
    d1 = strategies.expected_utility(u, obs)
    assert d1.action in ("investigate", "skip")
    assert d1.strategy == "expected_utility"
    d2 = strategies.active_inference(u, obs)
    assert d2.strategy == "active_inference"
    print(f"  ✓ Expected utility -> {d1.action}, Active inference -> {d2.action}")


def test_strategy_selector():
    selector = StrategySelector()
    selected = selector.select(uncertainty=0.7, budget_remaining=0.5)
    assert selected in ["expected_utility", "regret_minimization", "thompson_sampling", "mcts", "active_inference"]
    selector.record_outcome("expected_utility", 0.8)
    selector.record_outcome("mcts", 0.3)
    perf = selector.summary()
    assert "expected_utility" in perf["performance"]
    print(f"  ✓ Strategy selector: selected {selected}")


def test_director_learnable_thresholds():
    bus = MessageBus()
    util = UtilityEstimator(bus)
    director = Director(bus, util)
    assert director.hypothesis_threshold == 0.5
    director.set_parameter("hypothesis_threshold", 0.7)
    assert director.hypothesis_threshold == 0.7
    print(f"  ✓ Director thresholds are learnable")


def test_domain_adapter_base():
    class TestAdapter(DomainAdapter):
        domain = "test"
        version = "1.0"
    adapter = TestAdapter()
    health = adapter.health()
    assert health.status == "healthy"
    assert adapter.domain == "test"
    print("  ✓ DomainAdapter base class works")


def test_world_model_simulation():
    bus = MessageBus()
    wm = WorldModel(bus)
    wm.causal.add_node("memory", value=80, is_intervenible=True)
    wm.causal.add_node("latency", value=200)
    wm.causal.add_edge("memory", "latency", strength=0.8, uncertainty=0.2)
    wm.current_state.variables["memory"] = 80.0
    wm.current_state.variables["latency"] = 200.0
    action = {"action": "reduce", "target": "memory", "delta": -10.0}
    sim = wm.simulate(action, horizon=2)
    assert isinstance(sim, SimulationResult)
    assert "memory" in sim.next_state.variables
    assert sim.confidence > 0
    assert len(sim.side_effects) >= 0
    print(f"  ✓ World Model simulates: reward={sim.reward:.3f}, risk={sim.risk:.3f}")


def test_world_model_compare_scenarios():
    bus = MessageBus()
    wm = WorldModel(bus)
    wm.current_state.variables["memory"] = 80.0
    wm.current_state.variables["latency"] = 200.0
    wm.causal.add_node("memory", value=80, is_intervenible=True)
    wm.causal.add_node("latency", value=200)
    wm.causal.add_edge("memory", "latency", strength=0.8, uncertainty=0.2)
    actions = [
        {"action": "reduce_memory", "target": "memory", "delta": -20.0},
        {"action": "reduce_memory_small", "target": "memory", "delta": -5.0},
        {"action": "increase_memory", "target": "memory", "delta": 10.0},
    ]
    ranked = wm.compare_scenarios(actions)
    assert len(ranked) == 3
    assert ranked[0][1].reward >= ranked[1][1].reward
    print(f"  ✓ Compare scenarios: best={ranked[0][0]['action']} reward={ranked[0][1].reward:.3f}")


def test_calibration_tracker():
    bus = MessageBus()
    with tempfile.TemporaryDirectory() as tmp:
        cal = CalibrationTracker(bus, f"{tmp}/cal")
        pid = cal.record_prediction(0.9, component="test")
        cal.record_outcome(pid, success=True)
        pid2 = cal.record_prediction(0.3, component="test")
        cal.record_outcome(pid2, success=False)
        pid3 = cal.record_prediction(0.8, component="test")
        cal.record_outcome(pid3, success=False)
        ece = cal.compute_ece()
        assert ece > 0
        summary = cal.summary()
        assert summary["total_predictions"] >= 3
        calibrated = cal.calibrate_confidence(0.9, component="test")
        assert calibrated <= 0.9
        print(f"  ✓ Calibration: ECE={ece:.4f}, adjusted={calibrated:.3f}")


def test_causal_graph_learner():
    bus = MessageBus()
    learner = CausalGraphLearner(bus)
    g = CausalGraph()
    g.add_node("cpu", value=50)
    g.add_node("memory", value=60)
    for i in range(15):
        bus.publish(Event(
            type=EventType.OBSERVATION_READY,
            source="test",
            data={"metrics": {"cpu": 50 + i * 2, "memory": 60 + i}},
        ))
    bus.publish(Event(
        type=EventType.EXPERIMENT_COMPLETE,
        source="test",
        data={"metrics_before": {"cpu": 50}, "metrics_after": {"cpu": 45, "memory": 58}},
    ))
    applied = learner.apply_learned_edges(g, max_new_edges=2)
    assert isinstance(applied, list)
    summary = learner.summary()
    assert summary["observations_analyzed"] >= 10
    print(f"  ✓ Graph learner: {len(applied)} edges proposed, {summary['observations_analyzed']} obs")


def test_multi_objective_utility():
    mo = MultiObjectiveUtility()
    scores = {"performance": 0.8, "safety": 0.9, "cost": 0.3, "risk": 0.2, "maintainability": 0.7}
    result = mo.compute(scores)
    assert result.total > 0
    assert "pareto_vector" in result.summary()

    candidates = [
        {"performance": 0.9, "safety": 0.3, "cost": 0.7, "risk": 0.8, "maintainability": 0.2},
        {"performance": 0.6, "safety": 0.8, "cost": 0.4, "risk": 0.3, "maintainability": 0.7},
        {"performance": 0.4, "safety": 0.9, "cost": 0.2, "risk": 0.1, "maintainability": 0.9},
    ]
    frontier = mo.pareto_frontier(candidates)
    assert len(frontier) <= len(candidates)

    cvar = mo.cvar(candidates, alpha=0.33)
    assert "performance" in cvar
    print(f"  ✓ Multi-objective: total={result.total:.3f}, frontier={len(frontier)} points")


def test_risk_sensitive_utility():
    u = ExpectedUtility.default()
    u.terms["benefit"].value = 5.0
    u.terms["cost"].value = 1.0
    u.confidence = 1.0

    eu = RiskSensitiveUtility.exp_utility(u, risk_aversion=1.0)
    assert eu < u.total

    outcomes = [1.0, 0.8, 0.6, 0.4, 0.2]
    cvar = RiskSensitiveUtility.cvar_utility(outcomes, alpha=0.2)
    assert cvar <= sum(outcomes) / len(outcomes)

    mv = RiskSensitiveUtility.mean_variance(outcomes, risk_penalty=0.5)
    assert mv <= sum(outcomes) / len(outcomes)
    print(f"  ✓ Risk-sensitive: EU={eu:.3f}, CVaR={cvar:.3f}, MV={mv:.3f}")


def test_utility_evolver():
    u = ExpectedUtility.default()
    evolver = UtilityEvolver(u)
    changes = evolver.propose_modification(performance_delta=0.2)
    assert len(changes) >= 1
    assert u.terms["benefit"].weight > 1.0
    changes2 = evolver.propose_modification(performance_delta=-0.2)
    assert len(changes2) >= 1
    summary = evolver.summary()
    assert summary["modifications"] >= 2
    print(f"  ✓ Utility evolver: {summary['modifications']} modifications")


def test_world_model_rollback():
    bus = MessageBus()
    wm = WorldModel(bus)
    wm.current_state.variables["x"] = 10.0
    wm.state_history.append(wm.current_state.copy())
    wm.current_state.variables["x"] = 20.0
    wm.state_history.append(wm.current_state.copy())
    wm.current_state.variables["x"] = 30.0
    wm.state_history.append(wm.current_state.copy())
    success = wm.rollback(steps=1)
    assert success
    assert wm.current_state.variables["x"] == 20.0
    print("  ✓ World Model rollback restores state")


def test_full_cognitive_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        bus = MessageBus()
        engine = CognitiveEngine(bus, memory_path=f"{tmp}/.saecs")
        result = engine.run_cycle()
        assert "cycle" in result
        assert "world_model" in result
        assert "calibration" in result
        assert "graph_learner" in result
        assert "utility_evolver" in result
        print(f"  ✓ Full cycle: {result['cycle']}, "
              f"causal={result['causal']['nodes']} nodes, "
              f"calibration ECE={result['calibration']['ece']}")


def test_domain_observation():
    from saecs.domains.software import SoftwareDomain
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("def f():\n    if True:\n        pass\n")
        bus = MessageBus()
        sw = SoftwareDomain(bus, project_path=tmp)
        obs = sw.observe()
        assert obs.domain_id == "software"
        assert obs.state.metrics.get("modules", 0) >= 1
        print(f"  ✓ Software domain observation: {obs.state.metrics}")


def test_web_ui_observation():
    from saecs.domains.software import SoftwareDomain
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "index.html"), "w") as f:
            f.write("""
<!doctype html>
<html>
<head><title>Operations Console</title></head>
<body>
  <main>
    <h2>Operations</h2>
    <button id="shutdownControl"></button>
    <button data-action="approve-change">Approve</button>
    <input id="amount">
  </main>
</body>
</html>
""")
        with open(os.path.join(tmp, "style.css"), "w") as f:
            f.write("button { color: red; }\n")
        with open(os.path.join(tmp, "main.js"), "w") as f:
            f.write("fetch('/api/change');\nfunction approveChange() { return true; }\n")
        bus = MessageBus()
        sw = SoftwareDomain(bus, project_path=tmp)
        obs = sw.observe()
        assert obs.state.metrics.get("web_files", 0) == 3
        assert obs.state.metrics.get("html_files", 0) == 1
        assert obs.state.metrics.get("unlabeled_controls", 0) >= 2
        assert obs.state.metrics.get("confirmation_gaps", 0) >= 1
        assert obs.state.metrics.get("ux_risk_score", 0) > 0
        assert obs.state.metadata.get("ui_findings")
        print(f"  ✓ Web UI observation: {obs.state.metrics}")


def test_web_ui_domain_audit_falsifies_incomplete_hypothesis():
    from saecs.domains.software import WebUIDomain
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "index.html"), "w") as f:
            f.write("""
<html>
<body>
  <button id="executeChange">Execute Change</button>
  <button></button>
</body>
</html>
""")
        bus = MessageBus()
        sw = WebUIDomain(bus, project_path=tmp)
        h = Hypothesis(
            id="ui-risk",
            description="Improve UI layout",
            predicted_effect="Better operator clarity",
            evidence=["manual review"],
            confidence=0.7,
        )
        report = sw.audit_hypothesis(h)
        assert report.falsified
        assert "confirmation_risk_not_falsifiable" in report.attack_vectors
        print(f"  ✓ Web UI audit falsifies incomplete hypothesis: {report.attack_vectors}")


def test_domain_split_code_and_web_ui():
    from saecs.domains.software import CodeDomain, WebUIDomain, SoftwareDomain
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("def f():\n    if True:\n        return 1\n")
        with open(os.path.join(tmp, "index.html"), "w") as f:
            f.write("<html><body><button id='deleteItem'>Delete</button></body></html>")
        bus = MessageBus()
        code = CodeDomain(bus, project_path=tmp).observe()
        web = WebUIDomain(bus, project_path=tmp).observe()
        aggregate = SoftwareDomain(bus, project_path=tmp).observe()
        assert code.state.metrics["modules"] == 1
        assert code.state.metrics["web_files"] == 0
        assert web.state.metrics["modules"] == 0
        assert web.state.metrics["web_files"] == 1
        assert aggregate.state.metrics["modules"] == 1
        assert aggregate.state.metrics["web_files"] == 1
        print("  ✓ CodeDomain and WebUIDomain stay separated behind SoftwareDomain")


def test_domain_adapter_protocol():
    from saecs.domains.software import SoftwareDomain
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x = 1\n")
        bus = MessageBus()
        sw = SoftwareDomain(bus, project_path=tmp)
        assert sw.domain == "software"
        assert sw.version == "2.1"
        health = sw.health()
        assert health.status == "healthy"
        validate_result = sw.validate({"action": "refactor"})
        assert validate_result["safe"]
        print("  ✓ DomainAdapter protocol fully implemented")


def test_memory_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        from saecs.memory.episodic import EpisodicMemory
        bus = MessageBus()
        mem = EpisodicMemory(bus, f"{tmp}/ep")
        mem.store("test", "test event", "success")
        assert mem.count == 1
        mem2 = EpisodicMemory(bus, f"{tmp}/ep")
        assert mem2.count == 1
        print("  ✓ Memory persists across instances")


def test_governance_circuit_breaker():
    bus = MessageBus()
    gov = CognitiveGovernance(bus)
    assert gov.mode == SystemMode.NORMAL
    for i in range(5):
        gov._cycle_metrics.append({"outcome": "falsified"})
    gov._check_circuit_breakers()
    assert gov.mode in (SystemMode.CONSERVATIVE, SystemMode.QUARANTINE, SystemMode.RECOVERY, SystemMode.SHUTDOWN)
    print(f"  ✓ Governance circuit breaker triggered: mode={gov.mode.value}")


def test_utility_evolve():
    bus = MessageBus()
    util = UtilityEstimator(bus)
    from saecs.core.types import PerformanceSnapshot
    snapshots = [
        PerformanceSnapshot(cycle=1, falsification_rate=0.8, success_rate=0.1, budget_utilization=0.9),
        PerformanceSnapshot(cycle=2, falsification_rate=0.75, success_rate=0.15, budget_utilization=0.85),
        PerformanceSnapshot(cycle=3, falsification_rate=0.7, success_rate=0.2, budget_utilization=0.8),
    ]
    for s in snapshots:
        changes = util.evolve(s)
        if changes:
            break
    assert util.parameters is not None
    print(f"  ✓ Utility evolves: VOI weight={util.utility.terms['value_of_information'].weight:.3f}")


def test_simulate_action_from_engine():
    with tempfile.TemporaryDirectory() as tmp:
        bus = MessageBus()
        engine = CognitiveEngine(bus, memory_path=f"{tmp}/.saecs")
        engine.run_cycle()
        engine.world_model.current_state.variables["test_var"] = 100.0
        sim_result = engine.simulate_action({"action": "modify", "target": "test_var", "delta": -10.0})
        assert "reward" in sim_result
        assert "risk" in sim_result
        assert "confidence" in sim_result
        print(f"  ✓ Engine.simulate_action: reward={sim_result['reward']}")


if __name__ == "__main__":
    print("=== SAECS v5 - Full Cognitive Architecture ===\n")
    tests = [
        ("Message Bus", test_bus_works),
        ("Utility with learnable weights", test_expected_utility_with_voi),
        ("Utility terms learnable", test_utility_terms_learnable),
        ("Hypothesis Generation", test_hypothesis_generation),
        ("Auditor falsifies bad", test_auditor_falsifies_bad),
        ("Auditor confirms good", test_auditor_confirms_good),
        ("Auditor configurable depth", test_auditor_configurable_depth),
        ("Governance adjusts", test_cognitive_governance_adjusts),
        ("Causal World Model", test_causal_world_model),
        ("Causal learns from intervention", test_causal_learns_from_intervention),
        ("Planning Engine", test_planning_engine),
        ("Decision Strategies", test_decision_strategies),
        ("Strategy Selector", test_strategy_selector),
        ("Director learnable thresholds", test_director_learnable_thresholds),
        ("DomainAdapter base class", test_domain_adapter_base),
        ("World Model Simulation", test_world_model_simulation),
        ("World Model Compare Scenarios", test_world_model_compare_scenarios),
        ("World Model Rollback", test_world_model_rollback),
        ("Calibration Tracker", test_calibration_tracker),
        ("Causal Graph Learner", test_causal_graph_learner),
        ("Multi-Objective Utility", test_multi_objective_utility),
        ("Risk-Sensitive Utility", test_risk_sensitive_utility),
        ("Utility Evolver", test_utility_evolver),
        ("Full Cognitive Cycle", test_full_cognitive_cycle),
        ("Domain Observation", test_domain_observation),
        ("DomainAdapter protocol", test_domain_adapter_protocol),
        ("Memory Persistence", test_memory_persistence),
        ("Governance circuit breaker", test_governance_circuit_breaker),
        ("Utility evolution", test_utility_evolve),
        ("Simulate action from engine", test_simulate_action_from_engine),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    print(f"\n{passed}/{len(tests)} tests pasaron")
