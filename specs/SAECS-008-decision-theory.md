# SAECS-008: Decision Theory

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001, SAECS-004  
**Descripción:** Define el marco de teoría de decisión del SAECS, incluyendo minimización de arrepentimiento, métodos bayesianos, Thompson Sampling, MCTS y Active Inference. La función de utilidad no es fija: evoluciona.

---

## 1. Propósito

La función de utilidad actual (SAECS-004 §4) es un punto de partida, pero un sistema autónomo maduro debe poder seleccionar entre múltiples estrategias de decisión según el contexto y aprender cuál funciona mejor. Este RFC define el "árbol de decisión" del Director.

## 2. Arquitectura de Decisión

```
DecisionEngine := {
    strategies: [DecisionStrategy],
    active_strategy: string,           # cuál se usa actualmente
    strategy_performance: {            # histórica
        strategy_id: {
            times_used: int,
            avg_utility: float,
            avg_regret: float
        }
    },
    meta_learner: MetaLearner          # aprende qué estrategia usar
}
```

## 3. Estrategias de Decisión

### 3.1 Expected Utility (implementada actualmente)

```
SELECT a IN actions WHERE:
    U(a) = E[beneficio|a] - E[costo|a] - E[riesgo|a]
           - costo_oportunidad - costo_cognitivo
           + VOI + valor_aprendizaje

    RETURN argmax(U(a))
```

### 3.2 Regret Minimization

```
FUNCTION MinimaxRegret(actions, outcomes):

    // Matriz de arrepentimiento
    regret_matrix = {}
    FOR action IN actions:
        FOR outcome IN outcomes:
            best_alternative = MAX(
                U(other_action, outcome)
                FOR other_action IN actions
            )
            regret = best_alternative - U(action, outcome)
            regret_matrix[action][outcome] = regret

    // Minimizar el máximo arrepentimiento
    max_regrets = {
        action: MAX(regret_matrix[action].values())
        FOR action IN actions
    }
    RETURN argmin(max_regrets)
```

### 3.3 Thompson Sampling (para exploración balanceada)

```
FUNCTION ThompsonSample(hypotheses[], memory):

    FOR hypothesis IN hypotheses:
        // Muestrear de la distribución posterior
        alpha = hypothesis.times_tested - hypothesis.times_failed + 1
        beta = hypothesis.times_failed + 1
        sample = BetaDistribution(alpha, beta).sample()
        hypothesis.sampled_utility = sample

    // Seleccionar la de mayor muestra (no la de mayor media)
    RETURN argmax(hypotheses, BY=sampled_utility)
```

### 3.4 Monte Carlo Tree Search (MCTS)

```
FUNCTION MCTS(state, budget, rollout_policy):

    root = MCTSNode(state=state)

    FOR i IN range(budget):
        // 1. Selection
        node = Select(root)  // UCB1

        // 2. Expansion
        IF NOT node.is_terminal:
            node = Expand(node)

        // 3. Simulation (rollout)
        reward = Simulate(node.state, rollout_policy)

        // 4. Backpropagation
        Backpropagate(node, reward)

    // Seleccionar la mejor acción según visitas
    RETURN argmax(root.children, BY=visit_count)
```

### 3.5 Active Inference (Free Energy)

```
FUNCTION ActiveInference(state, prior, generative_model):

    // Expected Free Energy
    G = E[ -ln(P(o|s)) ]  -  KL[ Q(s) || P(s) ]

    // Pragmatic value: alcanzar estado deseado
    pragmatic = -ln(P(o_deseado | s))

    // Epistemic value: reducir incertidumbre
    epistemic = MI(s, o | a)   // información mutua entre estado y observación

    // Acción que minimiza G
    RETURN argmin(G(pragmatic, epistemic))
```

## 4. Meta-Selección de Estrategias

```
FUNCTION SelectStrategy(context, performance_history) → DecisionStrategy:

    features = ExtractFeatures(context):
        - uncertainty_level
        - available_cognitive_budget
        - hypothesis_count
        - time_pressure
        - domain
        - historical_success_rate

    // Para cada estrategia, predecir rendimiento
    predictions = {}
    FOR strategy IN strategies:
        similar_contexts = FindSimilar(features, strategy.history)
        IF similar_contexts:
            predictions[strategy] = AVG(similar_contexts.utility)
        ELSE:
            predictions[strategy] = strategy.default_utility

    // Seleccionar estrategia con mejor predicción
    // but occasionally explore (ε-greedy)
    IF random() < epsilon:
        RETURN random(strategies)
    ELSE:
        RETURN argmax(predictions)
```

## 5. Evolución de la Función de Utilidad

```
FUNCTION EvolveUtility(current_utility, outcomes[]):

    // Detectar qué términos de la utility fueron más predictivos
    errors = []
    FOR outcome IN outcomes:
        predicted = current_utility.estimate(outcome.context)
        actual = outcome.utility
        errors.append(actual - predicted)

    // Ajustar pesos de los términos
    // Ejemplo: si VOI siempre sobreestima, reducir su peso
    FOR term IN current_utility.terms:
        term_error = Correlation(term.value, errors)
        term.weight *= (1 - 0.1 * term_error)
        term.weight = clamp(term.weight, 0, 2)

    // ¿Añadir nuevo término?
    IF unexplained_variance > 0.2:
        candidate = ProposeNewTerm(causal_model, errors)
        IF candidate.explanatory_power > 0.3:
            current_utility.terms.append(candidate)

    // ¿Eliminar término irrelevante?
    FOR term IN current_utility.terms:
        IF term.weight < 0.05 AND term.times_evaluated > 10:
            current_utility.terms.remove(term)

    RETURN current_utility
```

## 6. POMDP como Marco Unificador

El SAECS modela su problema de decisión como un **POMDP** (Partially Observable Markov Decision Process):

```
POMDP := {
    states: S (el estado real del sistema, parcialmente observable),
    actions: A (investigar, experimentar, ejecutar, saltar),
    observations: O (métricas, tests, evidencia),
    transition: T(s' | s, a) (modelo causal, SAECS-006),
    observation: O(o | s, a) (confianza en las métricas),
    reward: R(s, a) (función de utilidad, SAECS-004),
    belief: b(s) (distribución de creencias sobre el estado)
}
```

**Belief Update (filtrado bayesiano):**

```
b'(s') = η * O(o | s', a) * Σ_s T(s' | s, a) * b(s)
```

**Policy (mapeo de creencias a acciones):**

```
π*(b) = argmax_a [ R(b, a) + γ * Σ_o P(o | b, a) * V*(b') ]
```

---

## Apéndice A: Performance por Estrategia

| Estrategia | Mejor para | Peor para |
|-----------|------------|-----------|
| Expected Utility | Decisiones rápidas con poca incertidumbre | Contextos con alta incertidumbre |
| Regret Minimization | Decisiones de alto riesgo | Contextos con muchas opciones similares |
| Thompson Sampling | Exploración balanceada | Cuando el costo del error es muy alto |
| MCTS | Planificación multi-paso | Presupuesto cognitivo limitado |
| Active Inference | Sistemas con objetivos claros | Funciones de recompensa difíciles de definir |
