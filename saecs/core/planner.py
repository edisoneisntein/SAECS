from __future__ import annotations
import uuid
from typing import Any
from .bus import MessageBus, Event, EventType, EventPriority
from .types import Goal, Plan, PlannedStep, CausalGraph


class PlanningEngine:
    def __init__(self, bus: MessageBus, causal_model=None):
        self.bus = bus
        self.causal_model = causal_model
        self.active_plans: dict[str, Plan] = {}
        self.completed_plans: list[Plan] = []

        bus.subscribe(EventType.GOVERNANCE_REVIEW, self._on_review)
        bus.subscribe(EventType.EXECUTION_SUCCESS, self._on_step_complete)
        bus.subscribe(EventType.EXECUTION_FAILED, self._on_step_failed)

    def create_goal(
        self,
        description: str,
        goal_type: str = "improve_attribute",
        target_metrics: dict[str, float] | None = None,
        priority: float = 0.5,
        parent_goal: str | None = None,
    ) -> Goal:
        goal = Goal(
            id=str(uuid.uuid4())[:8],
            description=description,
            goal_type=goal_type,
            target_metrics=target_metrics or {},
            priority=priority,
            parent_goal=parent_goal,
        )
        return goal

    def decompose(self, goal: Goal, causal_model=None) -> Plan:
        model = causal_model or self.causal_model
        plan = Plan(
            id=str(uuid.uuid4())[:8],
            goal=goal,
            objective_function=f"maximize: {goal.description}",
            horizon=self._estimate_horizon(goal),
        )

        if goal.goal_type == "improve_attribute" and model:
            leverage = model.find_leverage_points()
            for lp in leverage[:3]:
                plan.steps.append(PlannedStep(
                    id=str(uuid.uuid4())[:8],
                    action="modify",
                    target=lp["node"],
                    expected_utility=lp["score"],
                    estimated_cost=10.0,
                    estimated_risk=lp.get("uncertainty", 0.5),
                ))
            if not plan.steps:
                for metric in goal.target_metrics or {"target": 1.0}:
                    plan.steps.append(self._verification_step(goal, metric))

        elif goal.goal_type == "fix_problem" and model:
            for metric in goal.target_metrics:
                root_causes = model.trace_root_causes(metric)
                for cause in root_causes[:3]:
                    plan.steps.append(PlannedStep(
                        id=str(uuid.uuid4())[:8],
                        action="intervene",
                        target=cause["node"],
                        expected_utility=cause["path_strength"],
                        estimated_cost=15.0,
                        estimated_risk=1.0 - cause["path_strength"],
                    ))
            if not plan.steps:
                for metric in goal.target_metrics or {"problem": 1.0}:
                    plan.steps.extend([
                        PlannedStep(
                            id=str(uuid.uuid4())[:8],
                            action="gather_evidence",
                            target=metric,
                            expected_utility=goal.priority * 0.8,
                            estimated_cost=5.0,
                            estimated_risk=0.2,
                        ),
                        self._verification_step(goal, metric),
                    ])

        elif goal.goal_type == "explore" and model:
            most_uncertain = max(
                model.graph.nodes.values(),
                key=lambda n: n.uncertainty,
                default=None,
            )
            if most_uncertain:
                plan.steps.append(PlannedStep(
                    id=str(uuid.uuid4())[:8],
                    action="measure",
                    target=most_uncertain.name,
                    expected_utility=most_uncertain.uncertainty * 0.8,
                    estimated_cost=5.0,
                ))

        else:
            plan.steps.append(PlannedStep(
                id=str(uuid.uuid4())[:8],
                action="investigate",
                target=goal.description,
                expected_utility=goal.priority,
                estimated_cost=10.0,
            ))

        plan.dependencies = self._build_dependencies(plan.steps)
        plan.horizon = self._estimate_horizon(goal)

        self.active_plans[plan.id] = plan
        return plan

    def get_ready_steps(self, plan_id: str) -> list[PlannedStep]:
        plan = self.active_plans.get(plan_id)
        if not plan:
            return []
        completed_ids = {
            s.id for s in plan.steps if s.status in ("completed", "skipped")
        }
        return [
            s for s in plan.steps
            if s.status == "pending"
            and all(dep in completed_ids for dep in s.dependencies)
        ]

    def execute_next(self, plan_id: str, director) -> bool:
        plan = self.active_plans.get(plan_id)
        if not plan or plan.status != "active":
            return False

        ready = self.get_ready_steps(plan_id)
        if not ready:
            if all(s.status in ("completed", "skipped", "failed") for s in plan.steps):
                plan.status = "completed"
                self.completed_plans.append(plan)
                del self.active_plans[plan_id]
                self.bus.publish(Event(
                    type=EventType.CYCLE_COMPLETE,
                    source="planner",
                    data={"plan_id": plan_id, "goal": plan.goal.description, "status": "completed"},
                ))
            return False

        ready.sort(key=lambda s: s.expected_utility / max(s.estimated_cost, 0.01), reverse=True)
        step = ready[0]

        if not director._check_budget(step.estimated_cost):
            self.bus.publish(Event(
                type=EventType.BUDGET_EXCEEDED,
                source="planner",
                data={"plan_id": plan_id, "step": step.id, "cost": step.estimated_cost},
            ))
            return False

        step.status = "in_progress"
        director._spend(step.estimated_cost)

        self.bus.publish(Event(
            type=EventType.EXECUTION_REQUESTED,
            source="planner",
            data={
                "plan_id": plan_id,
                "step": {
                    "id": step.id,
                    "action": step.action,
                    "target": step.target,
                },
            },
        ))
        return True

    def replan(self, plan_id: str, reason: str) -> Plan | None:
        plan = self.active_plans.get(plan_id)
        if not plan:
            return None

        completed = [s for s in plan.steps if s.status == "completed"]
        remaining = [s for s in plan.steps if s.status in ("pending", "failed")]

        if not remaining:
            plan.status = "completed"
            self.completed_plans.append(plan)
            del self.active_plans[plan_id]
            return plan

        new_plan = self.decompose(plan.goal, self.causal_model)
        new_plan.steps = completed + new_plan.steps
        new_plan.dependencies = self._build_dependencies(new_plan.steps)

        self.active_plans[plan_id] = new_plan

        self.bus.publish(Event(
            type=EventType.GOVERNANCE_REVIEW,
            source="planner",
            data={"plan_id": plan_id, "replan_reason": reason, "new_steps": len(new_plan.steps)},
        ))
        return new_plan

    def _build_dependencies(self, steps: list[PlannedStep]) -> dict:
        deps: dict[str, list[str]] = {}
        for i, step in enumerate(steps):
            deps[step.id] = [s.id for s in steps[:i] if s.estimated_risk > 0.3]
        return deps

    def _estimate_horizon(self, goal: Goal) -> int:
        if goal.goal_type == "explore":
            return 3
        elif goal.goal_type == "improve_attribute":
            return 10
        elif goal.goal_type == "fix_problem":
            return 5
        return 10

    def _verification_step(self, goal: Goal, metric: str) -> PlannedStep:
        return PlannedStep(
            id=str(uuid.uuid4())[:8],
            action="define_verification",
            target=metric,
            expected_utility=goal.priority * 0.6,
            estimated_cost=3.0,
            estimated_risk=0.1,
        )

    def _on_review(self, event: Event) -> None:
        data = event.data
        plan_id = data.get("plan_id")
        if plan_id and plan_id in self.active_plans:
            plan = self.active_plans[plan_id]
            if data.get("replan_reason"):
                self.replan(plan_id, data["replan_reason"])

    def _on_step_complete(self, event: Event) -> None:
        for plan_id, plan in list(self.active_plans.items()):
            for step in plan.steps:
                if step.status == "in_progress":
                    step.status = "completed"
                    step.result = event.data

    def _on_step_failed(self, event: Event) -> None:
        for plan_id, plan in list(self.active_plans.items()):
            for step in plan.steps:
                if step.status == "in_progress":
                    step.status = "failed"
                    self.replan(plan_id, f"Step {step.id} failed")

    def summary(self) -> dict:
        return {
            "active_plans": len(self.active_plans),
            "completed_plans": len(self.completed_plans),
            "plans": [
                {
                    "id": pid,
                    "goal": p.goal.description[:60],
                    "status": p.status,
                    "steps": len(p.steps),
                    "completed_steps": sum(1 for s in p.steps if s.status == "completed"),
                }
                for pid, p in self.active_plans.items()
            ],
        }
