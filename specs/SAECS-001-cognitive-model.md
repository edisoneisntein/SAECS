# SAECS-001: Modelo Cognitivo

**Estado:** Borrador  
**Prioridad:** Especificación Fundamental  
**Dependencias:** Ninguna  
**Descripción:** Define los estados, eventos, estructura de confianza, incertidumbre y decisiones del Sistema Autónomo de Evolución Continua.

---

## 1. Propósito

Definir el modelo formal del ciclo cognitivo universal. Este RFC establece el vocabulario, la máquina de estados, y los protocolos de decisión que cualquier implementación del SAECS debe respetar, independientemente del dominio de aplicación.

## 2. Máquina de Estados del Ciclo Cognitivo

El sistema transita por una secuencia estricta de estados. Cada estado tiene precondiciones, acciones y postcondiciones definidas.

```
                    ┌──────────────────┐
                    │   OBSERVING      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  MODELING        │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
               ┌───│  EVALUATING      │
               │   └────────┬─────────┘
               │            │
               │     ┌──────┴──────┐
               │     ▼             ▼
               │  ┌────────┐  ┌──────────┐
               │  │ SKIP   │  │ DECIDED  │
               │  └────────┘  └────┬─────┘
               │                   │
               │            ┌──────┴──────┐
               │            ▼             ▼
               │     ┌───────────┐  ┌──────────┐
               │     │ RESEARCH  │  │ EXECUTE  │
               │     └─────┬─────┘  └────┬─────┘
               │           │             │
               │           ▼             │
               │     ┌───────────┐       │
               │     │ HYPOTHESIZE       │
               │     └─────┬─────┘       │
               │           │             │
               │           ▼             │
               │     ┌───────────┐       │
               │     │ EXPERIMENT        │
               │     └─────┬─────┘       │
               │           │             │
               │           ▼             │
               │     ┌───────────┐       │
               │     │ VALIDATE  │       │
               │     └─────┬─────┘       │
               │           │             │
               │           ▼             ▼
               │     ┌──────────────────────┐
               └─────│      LEARN           │
                     └──────────────────────┘
```

### 2.1 Definición de Estados

| Estado | ID | Precondición | Postcondición |
|--------|----|-------------|---------------|
| Observing | `OBS` | Sistema activo | `Observation` emitida |
| Modeling | `MOD` | `Observation` disponible | `ModelState` actualizado |
| Evaluating | `EVL` | `ModelState` completo | `Decision` emitida |
| Skip | `SKP` | `Decision.action == "skip"` | Ciclo termina en inacción |
| Decided | `DCD` | `Decision.action != "skip"` | Hipótesis o ejecución inicia |
| Research | `RCH` | Decidido investigar | `InvestigationReport` |
| Hypothesize | `HYP` | `InvestigationReport` | `Hypothesis[]` |
| Experiment | `EXP` | `Hypothesis` seleccionada | `ExperimentResult` |
| Validate | `VLD` | `ExperimentResult` | `ValidationReport` |
| Execute | `EXE` | Hipótesis validada | `ExecutionReport` |
| Learn | `LRN` | Cualquier resultado | Memoria actualizada |

## 3. Estructura de Confianza

La confianza es un tuple `(valor, peso, fuente)` que acompaña toda proposición en el sistema.

```
Confidence := {
    value: float ∈ [0, 1],
    weight: float ∈ [0, 1],    # cantidad de evidencia
    source: enum {evidence, statistical, heuristic, inferred},
    timestamp: datetime
}
```

**Reglas:**
- `confidence.value = 0` → proposición falsada
- `confidence.value = 1` → proposición demostrada (solo tras 100% validación)
- `confidence.weight = 0` → la confianza no tiene respaldo
- Solo proposiciones con `weight ≥ 0.3` pueden usarse para decisiones

## 4. Estructura de Incertidumbre

```
Uncertainty := {
    aleatory: float ∈ [0, 1],     # incertidumbre inherente (ruido)
    epistemic: float ∈ [0, 1],    # incertidumbre por falta de conocimiento
    total: float ∈ [0, 1],        # max(aleatory, epistemic)
    sources: [string],            # qué causa la incertidumbre
    reduction_path: [string]      # qué información la reduciría
}
```

**Protocolo de gestión de incertidumbre:**

```
SI uncertainty.total > 0.7:
    → No ejecutar. Solo investigar.
SI uncertainty.epistemic > uncertainty.aleatory:
    → Priorizar recolección de información sobre acción.
SI uncertainty.total < 0.2:
    → Ejecución directa permitida (si utility > 0).
```

## 5. Decisiones

Toda decisión se representa como:

```
Decision := {
    id: UUID,
    timestamp: datetime,
    context: Observation,
    options: [{
        action: enum {investigate, experiment, execute, skip},
        utility: float,           # utility.total calculada
        confidence: float,        # confianza en la estimación
        reasoning: [string]       # cadena de inferencia
    }],
    selected: int,                # índice de la opción elegida
    approved: bool
}
```

**Criterio de selección:**

```
SELECT option WHERE:
    1. option.utility > 0
    2. option.confidence * option.utility es máximo
    3. SI ninguna opción cumple (1): seleccionar "skip"
```

## 6. Eventos del Ciclo

Todos los componentes se comunican mediante eventos:

| Evento | Emisor | Receptor | Datos |
|--------|--------|----------|-------|
| `observation.ready` | Observer | Director | `Observation` |
| `uncertainty.evaluated` | Modeler | Director | `Uncertainty` |
| `decision.made` | Director | Todos | `Decision` |
| `investigation.requested` | Director | Investigator | problema, contexto |
| `investigation.complete` | Investigator | Director | `InvestigationReport` |
| `hypotheses.generated` | HypothesisEngine | Director | `Hypothesis[]` |
| `experiment.requested` | Director | Experimenter | `Hypothesis` |
| `experiment.complete` | Experimenter | Director | `ExperimentResult` |
| `audit.requested` | Director | Auditor | `Hypothesis` |
| `hypothesis.falsified` | Auditor | Director | `AuditReport` |
| `hypothesis.confirmed` | Auditor | Director | `AuditReport` |
| `execution.requested` | Director | Executor | `ExecutionPlan` |
| `execution.success` | Executor | Director | `ExecutionReport` |
| `execution.failed` | Executor | Director | error, rollback |
| `cycle.complete` | Director | Memoria, Governance | resumen del ciclo |

## 7. Protocolo de Cancelación

```
SI durante cualquier estado:
    costo_cognitivo_acumulado > presupuesto_asignado * 1.5
    → EMITIR intervention.cancelled
    → TRANSICIÓN A Learn
    → REGISTRAR motivo en memoria episódica
    → NO modificar el sistema

SI utility.total <= 0 después de actualizar incertidumbre:
    → EMITIR inaction.decided
    → TRANSICIÓN A Learn
    → CONSIDERAR victoria de optimización
```

## 8. Métricas del Ciclo

Cada ciclo completo genera:

```
CycleMetrics := {
    id: UUID,
    domain: string,
    states_visited: [State],
    duration_ms: float,
    cognitive_cost: float,
    decisions_made: int,
    hypotheses_generated: int,
    experiments_run: int,
    audits_passed: int,
    audits_failed: int,
    outcome: enum {success, rolled_back, cancelled, inaction},
    uncertainty_before: float,
    uncertainty_after: float
}
```

---

## Apéndice A: Glosario Formal

| Término | Definición |
|---------|------------|
| Ciclo cognitivo | Una iteración completa del SAECS: OBS → MOD → EVL → [SKP | DCD → RCH → HYP → EXP → VLD → EXE] → LRN |
| Confianza | Medida de credibilidad en una proposición, compuesta por valor, peso y fuente |
| Incertidumbre | Medida de desconocimiento, separada en aleatoria (inherente) y epistémica (falta de datos) |
| Decisión | Selección entre opciones basada en utilidad esperada y confianza |
| Evidencia | Dato empírico que soporta o contradice una proposición |
| Utility | Valor neto esperado de una acción, incluyendo VOI y valor de aprendizaje |
