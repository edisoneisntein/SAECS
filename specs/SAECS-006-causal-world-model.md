# SAECS-006: Causal World Model

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001, SAECS-002, SAECS-003  
**Descripción:** Define cómo el SAECS representa, aprende y utiliza relaciones causales entre variables del sistema para predecir efectos secundarios y guiar la intervención quirúrgica.

---

## 1. Propósito

Sin un modelo causal, el sistema trata síntomas, no causas. Este RFC establece el grafo causal que permite al SAECS predecir el impacto de cualquier modificación antes de ejecutarla, calculando caminos de propagación y puntos de apalancamiento.

## 2. Estructura del Grafo Causal

```
CausalGraph := {
    nodes: [CausalNode],
    edges: [CausalEdge],
    metadata: {
        last_updated: datetime,
        uncertainty: float,
        version: int
    }
}

CausalNode := {
    id: UUID,
    variable: string,          # nombre de la variable del sistema
    type: enum {
        latent,                # no observable directamente
        observable,            # medible con métricas
        controllable,          # modificable por el sistema
        dependent              # solo cambia como consecuencia
    },
    current_value: float?,
    domain: [float, float],    # rango posible
    unit: string
}

CausalEdge := {
    id: UUID,
    source: UUID,              # nodo origen
    target: UUID,              # nodo destino
    relationship: enum {
        direct_cause,          # A → B siempre
        probabilistic,         # A → B con cierta probabilidad
        inhibitory,            # A → ¬B
        moderating,            # A modera la relación entre B y C
        feedback_positive,     # A → B → ... → A (refuerzo)
        feedback_negative      # A → B → ... → ¬A (equilibrio)
    },
    strength: float ∈ [0,1],  # fuerza de la relación causal
    delay: float?,             # tiempo promedio en propagarse
    confidence: float ∈ [0,1], # qué tan seguros estamos
    evidence: [EvidenceID]     # evidencia que soporta este edge
}
```

## 3. Aprendizaje del Grafo

### 3.1 Desde datos observacionales

```
FUNCTION LearnCausalEdges(observations[], current_graph) → CausalEdge[]:

    candidates = []

    // Detección de correlaciones
    FOR (var_a, var_b) IN pairs(observations.variables):
        corr = pearson_correlation(var_a, var_b, observations)
        IF abs(corr) > 0.5:
            // Posible relación causal (requiere más evidencia)

    // Detección temporal (causa precede a efecto)
    FOR (var_a, var_b) IN pairs(observations.variables):
        lag = cross_correlation_lag(var_a, var_b, observations)
        IF lag > 0:  // var_a cambia antes que var_b
            candidates.append(Edge(source=var_a, target=var_b, lag=lag))

    // Detección por intervención
    FOR experiment IN memory.episodic.query(type="experiment"):
        cause = experiment.independent_variable
        FOR effect IN experiment.measured_variables:
            IF experiment.result.confidence > 0.8:
                candidates.append(Edge(
                    source=cause, target=effect,
                    strength=experiment.effect_size,
                    confidence=experiment.result.confidence
                ))

    // Filtrado: mantener solo edges con soporte suficiente
    RETURN [c FOR c IN candidates WHERE c.confidence > 0.3]
```

### 3.2 Desde intervención directa (gold standard)

```
FUNCTION TestCausalHypothesis(source_var, target_var) → CausalEdge:

    // 1. Intervenir sobre source_var
    old_value = system.get(source_var)
    system.set(source_var, perturbed_value)

    // 2. Observar target_var después del delay estimado
    wait(delay)
    new_value = system.get(target_var)

    // 3. Revertir
    system.set(source_var, old_value)

    // 4. Calcular efecto causal
    effect = (new_value - old_value) / perturbed_value

    RETURN CausalEdge(
        source=source_var,
        target=target_var,
        strength=abs(effect),
        confidence=min(1.0, effect_size / baseline_variance)
    )
```

## 4. Propagación de Intervenciones

```
FUNCTION PredictImpact(intervention_node, delta, graph, depth=3) → ImpactTree:

    tree = ImpactTree(root=intervention_node, delta=delta)

    // BFS limitado por profundidad
    queue = [(intervention_node, delta, 0)]
    visited = set()

    WHILE queue:
        current_node, current_delta, d = queue.pop(0)
        IF d >= depth: continue
        IF current_node in visited: continue
        visited.add(current_node)

        FOR edge IN graph.edges WHERE edge.source == current_node:
            propagated = current_delta * edge.strength * edge.confidence
            arrival_time = d * avg_delay

            tree.add_impact(
                node=edge.target,
                delta=propagated,
                arrival_time=arrival_time,
                confidence=edge.confidence
            )

            queue.append((edge.target, propagated, d + 1))

    RETURN tree
```

## 5. Identificación de Puntos de Apalancamiento

```
FUNCTION FindLeveragePoints(graph, objective_variable, desired_delta) → [CausalNode]:

    // Nodos con alto "impacto total" sobre el objetivo
    scores = []
    FOR node IN graph.nodes:
        impact_tree = PredictImpact(node.id, 1.0, graph)
        total_impact = SUM(
            impact.delta * impact.confidence
            FOR impact IN impact_tree.impacts
            WHERE impact.node == objective_variable
        )
        cost = EstimateCost(node)
        scores.append((node, total_impact / cost))

    // Ordenar por impacto por unidad de costo
    RETURN [node FOR node, score IN sorted(scores, key=descending)]
```

## 6. Detección de Efectos Secundarios

```
FUNCTION DetectSideEffects(intervention_plan, graph) → [RiskForecast]:

    risks = []

    // Simular intervención
    prediction = PredictImpact(
        intervention_plan.target_variable,
        intervention_plan.delta,
        graph
    )

    // Identificar impactos negativos no previstos
    FOR impact IN prediction.impacts:
        IF impact.delta < 0:
            risks.append(RiskForecast(
                variable=impact.node,
                expected_degradation=abs(impact.delta),
                probability=impact.confidence,
                arrival_time=impact.arrival_time,
                mitigation=""
            ))

    // Identificar ciclos de retroalimentación positiva peligrosa
    FOR cycle IN FindFeedbackLoops(graph, intervention_plan.target_variable):
        IF cycle.type == "positive" AND cycle.amplification > 1.5:
            risks.append(RiskForecast(
                variable=cycle.variables,
                expected_degradation="runaway",
                probability=0.3,
                mitigation="break_cycle_at: " + cycle.breakpoint
            ))

    RETURN risks
```

## 7. Ciclo de Vida del Modelo Causal

```
CADA CICLO:

    1. OBSERVAR nuevas correlaciones en datos recientes
    2. PROPONER edges candidatos
    3. TESTEAR hipótesis causales mediante intervención mínima
    4. ACTUALIZAR graph.confidence
    5. PODAR edges con confidence < 0.1
    6. DETECTAR nodos latentes (variables no medidas que explicarían residuos)

CADA 10 CICLOS:

    1. RECOMPONER estructura del grafo con nuevos datos
    2. VALIDAR poder predictivo contra episodios recientes
    3. REPORTAR al Governance: "El modelo causal explica el X% de la varianza"
```

---

## Apéndice A: Métricas del Modelo Causal

| Métrica | Fórmula | Objetivo |
|---------|---------|----------|
| Cobertura causal | `edges / posibles_pares` | > 0.3 |
| Precisión predictiva | `predicciones_acertadas / total_predicciones` | > 0.7 |
| Densidad de ciclos | `feedback_loops / total_edges` | < 0.1 (o monitoreados) |
| Confianza promedio | `AVG(edge.confidence)` | > 0.5 |
| Poder de intervención | `mejora_real / mejora_predicha` | 0.8 - 1.2 |
