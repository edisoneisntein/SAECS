# SAECS-007: Planning & Goal Decomposition

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001, SAECS-004, SAECS-006  
**Descripción:** Define cómo el SAECS establece objetivos, los descompone en subobjetivos, genera planes, ejecuta acciones secuenciales y replanifica ante fallos.

---

## 1. Propósito

Sin planificación, el sistema reacciona pero no ejecuta estrategias. Este RFC establece el motor de planes que permite al SAECS perseguir objetivos complejos mediante secuencias de acciones coordinadas.

## 2. Estructura de un Plan

```
Plan := {
    id: UUID,
    goal: Goal,
    objective_function: string,   # función de utilidad a maximizar
    horizon: int,                 # número de ciclos del plan
    created_at: datetime,
    status: enum {active, completed, failed, cancelled},
    steps: [PlannedStep],
    dependencies: DAG[step_id],   # grafo de dependencias entre pasos
    metrics: {
        expected_utility: float,
        risk: float,
        duration_estimate: int     # en ciclos
    }
}

Goal := {
    id: UUID,
    description: string,
    type: enum {
        improve_attribute,       # mejorar métrica X en Y%
        fix_problem,            # resolver problema específico
        explore,                # reducir incertidumbre sobre X
        learn,                  # adquirir conocimiento sobre Y
        maintain,               # mantener métrica dentro de rango
        transform               # cambiar arquitectura del sistema
    },
    target_metrics: {metric: target_value},
    constraints: [Constraint],
    priority: float ∈ [0,1],
    deadline: datetime?,
    parent_goal: UUID?          # si es subobjetivo
}

PlannedStep := {
    id: UUID,
    action: string,
    target: string,
    expected_utility: float,
    estimated_cost: float,
    estimated_risk: float,
    dependencies: [UUID],        # pasos que deben completarse antes
    status: enum {pending, in_progress, completed, failed, skipped},
    result: any?
}
```

## 3. Protocolo de Descomposición

```
FUNCTION DecomposeGoal(goal, causal_model) → Plan:

    plan = Plan(goal=goal)

    SI goal.type == "improve_attribute":
        // Encontrar puntos de apalancamiento (ver SAECS-006 §5)
        leverage = FindLeveragePoints(causal_model, goal.target_metrics)
        FOR node IN leverage[:3]:  // top 3
            plan.steps.append(PlannedStep(
                action="modify",
                target=node.variable,
                expected_utility=CalculateUtility(node, goal),
                estimated_cost=EstimateCost(node),
                dependencies=[]
            ))

    SI goal.type == "fix_problem":
        // Buscar causa raíz en grafo causal
        root_causes = TraceBack(causal_model, goal.target_metrics)
        FOR cause IN root_causes:
            plan.steps.append(PlannedStep(
                action="intervene",
                target=cause.variable,
                dependencies=[]
            ))

    SI goal.type == "explore":
        // Identificar la variable con mayor incertidumbre epistémica
        most_uncertain = ArgMax(
            causal_model.nodes,
            by=lambda n: n.uncertainty
        )
        plan.steps.append(PlannedStep(
            action="measure",
            target=most_uncertain.variable,
            expected_utility=most_uncertain.uncertainty * 0.5,
            estimated_cost=10.0
        ))

    // Construir DAG de dependencias
    plan.dependencies = BuildDependencyGraph(plan.steps)
    plan.horizon = EstimateHorizon(plan.steps)

    RETURN plan
```

## 4. Ejecución del Plan

```
FUNCTION ExecutePlan(plan, director):

    // 1. Validar que el plan sigue siendo relevante
    SI NOT IsPlanStillValid(plan):
        RETURN Replan(plan, reason="plan obsoleto")

    // 2. Obtener pasos listos para ejecutar
    ready = GetReadySteps(plan)  // pasos sin dependencias pendientes

    // 3. Priorizar por utilidad esperada / costo
    sorted_steps = SORT(ready, BY=expected_utility / estimated_cost, DESC)

    FOR step IN sorted_steps:
        // 4. Verificar presupuesto cognitivo
        IF NOT director.CheckBudget(step.estimated_cost):
            PAUSE plan
            RETURN

        // 5. Ejecutar paso (delega al componente correspondiente)
        result = ExecuteStep(step)

        // 6. Evaluar resultado
        SI result == success:
            step.status = completed
            plan.metrics.expected_utility -= step.estimated_cost
        ELSE:
            step.status = failed
            // Replanificar desde aquí
            RETURN Replan(plan, reason=f"step {step.id} failed")

    // 7. Verificar si el plan está completo
    IF ALL plan.steps.status IN {completed, skipped}:
        plan.status = completed
        RETURN plan

    // 8. Continuar en siguiente ciclo
    RETURN plan
```

## 5. Protocolo de Replanificación

```
FUNCTION Replan(plan, reason):

    // 1. Preservar pasos ya completados
    completed = [s FOR s IN plan.steps WHERE s.status == completed]

    // 2. Evaluar qué cambió
    changes = DetectChanges(plan)

    // 3. Si el cambio es menor, ajustar pasos restantes
    SI changes.magnitude < 0.2:
        remaining = [s FOR s IN plan.steps WHERE s.status == pending]
        FOR step IN remaining:
            Reestimate(step, changes)
        RETURN plan

    // 4. Si el cambio es mayor, regenerar desde el objetivo
    SI changes.magnitude >= 0.2:
        new_plan = DecomposeGoal(plan.goal, causal_model)
        new_plan.steps = completed + new_plan.steps
        RETURN new_plan

    // 5. Si el objetivo ya no es alcanzable:
    SI changes makes goal.unreachable:
        RETURN None  // El Director decide: ¿nuevo objetivo? ¿abortar?
```

## 6. Horizonte Temporal

```
Horizon := {
    short_term: int = 3,      # ciclos inmediatos
    medium_term: int = 10,     # semanas de ciclos
    long_term: int = 50        # meses de ciclos
}
```

**Reglas:**
- `horizon < 3`: decisiones tácticas sin plan formal
- `3 <= horizon < 10`: plan detallado paso a paso
- `10 <= horizon < 50`: plan con hitos, no pasos individuales
- `horizon >= 50`: plan estratégico con revisión periódica

## 7. Planificación Multi-Objetivo

```
FUNCTION MultiObjectivePlan(goals[], causal_model):

    // 1. Detectar conflictos entre objetivos
    conflicts = []
    FOR (g1, g2) IN pairs(goals):
        impact_g1_on_g2 = PredictImpact(g1, causal_model, on=g2)
        IF impact_g1_on_g2 < 0:
            conflicts.append((g1, g2, impact_g1_on_g2))

    // 2. Resolver conflictos (negociación entre objetivos)
    IF conflicts:
        ParetoFrontier(goals, conflicts)  // encontrar trade-offs óptimos

    // 3. Generar plan combinado
    plan = Plan()
    FOR goal IN goals:
        subplan = DecomposeGoal(goal, causal_model)
        plan.steps.extend(subplan.steps)

    // 4. Fusionar dependencias entre subplanes
    plan.dependencies = MergeDependencies(plan.steps)

    RETURN plan
```

---

## Apéndice A: Evaluación de Planes

| Criterio | Pregunta | ¿Replanificar? |
|----------|----------|----------------|
| Utilidad | ¿Utilidad esperada sigue siendo > 0? | Si < 0 |
| Riesgo | ¿Riesgo acumulado > 0.7? | Si |
| Horizonte | ¿Quedan < 20% de ciclos? | Acelerar o simplificar |
| Cambio externo | ¿Cambió el modelo causal? | Si, significativamente |
| Fracaso | ¿Falló un paso crítico? | Si, desde ese paso |
