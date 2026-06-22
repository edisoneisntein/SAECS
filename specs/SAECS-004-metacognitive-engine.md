# SAECS-004: Motor Metacognitivo

**Estado:** Borrador  
**Prioridad:** Especificación Fundamental  
**Dependencias:** SAECS-001, SAECS-002  
**Descripción:** Define el presupuesto cognitivo, el costo de pensar, los criterios de parada y el protocolo de inacción estratégica.

---

## 1. Propósito

Establecer el marco formal para que el SAECS gestione sus propios recursos cognitivos. Este motor decide **si** pensar, **cuánto** pensar, y **cuándo dejar** de pensar. Es la capa que diferencia un sistema autónomo eficiente de uno que simplemente它era sin criterio.

## 2. Presupuesto Cognitivo

El sistema opera con un presupuesto cognitivo finito que debe administrar:

```
CognitiveBudget := {
    total: float,             # presupuesto total del ciclo
    allocated: float,         # ya asignado a tareas
    spent: float,             # ya consumido
    remaining: float,         # total - spent
    reserve: float,           # reserva para emergencias (20% de total)
    per_component: {
        observer: float,
        investigator: float,
        hypothesis_generator: float,
        experimenter: float,
        auditor: float,
        executor: float
    }
}
```

**Asignación inicial por defecto:**

| Componente | Porcentaje | Justificación |
|------------|-----------|---------------|
| Observer | 5% | Escaneo ligero |
| Investigator | 25% | Causa raíz es costosa |
| Hypothesis Generator | 10% | Generación es barata |
| Experimenter | 30% | Simulación es lo más costoso |
| Auditor | 20% | Falsación rigurosa |
| Executor | 10% | Ejecución directa |

## 3. Costo Cognitivo

Cada operación tiene un costo estimado:

```
CostoEstimado := {
    scan_project: float = 5.0,
    analyze_dependency: float = 8.0,
    generate_hypothesis: float = 3.0,
    run_simulation: float = 25.0,
    run_audit: float = 15.0,
    cross_validate: float = 20.0,
    execute_change: float = 10.0,
    rollback: float = 5.0
}
```

**Regla de costo real:**

```
SI costo_real > costo_estimado * 1.5:
    → EMITIR warning de eficiencia
    → REGISTRAR en memoria estratégica para recalibrar estimación

SI costo_real > costo_estimado * 3.0:
    → CANCELAR operación actual
    → ROLLBACK si es necesario
    → REGISTRAR como "fracaso cognitivo"
```

## 4. Función de Utilidad General

La decisión de invertir recursos cognitivos se rige por:

```
U = E[beneficio] - E[costo] - E[riesgo] - costo_oportunidad
    - costo_cognitivo + VOI + valor_aprendizaje

Donde:
    E[beneficio] = impacto_esperado * probabilidad_mejora
    E[costo] = tiempo_implementación + recursos_computacionales
    E[riesgo] = probabilidad_fallo * impacto_fallo
    costo_oportunidad = beneficio_de_la_siguiente_mejor_opción
    costo_cognitivo = costo_de_pensar_en_esta_opción
    VOI = valor_de_la_información_que_se_obtendría (ver SAECS-002 §9)
    valor_aprendizaje = beneficio_futuro_estimado * tasa_aprendizaje
```

## 5. Criterios de Parada

El Director evalúa continuamente si continuar invirtiendo:

```
// Parada por retorno negativo
SI utility_acumulada < utility_invertida_en_pensar * 1.2:
    → DETENER investigación actual
    → REGISTRAR punto de parada
    → PASAR a siguiente prioridad

// Parada por estancamiento
SI NO se ha reducido incertidumbre en > 10% tras 3 iteraciones:
    → DETENER línea de investigación
    → REGISTRAR como "estancamiento"
    → CAMBIAR estrategia

// Parada por límite de presupuesto
SI cognitive_budget.spent > cognitive_budget.total * 0.8:
    → ENTRAR en modo conservador (solo ejecuciones seguras)
    → CANCELAR todas las investigaciones exploratorias

// Parada por evidencia concluyente
SI hypothesis.support.net_weight > 0.9:
    → DETENER experimentación
    → PROCEDER a ejecución
```

## 6. Protocolo de Inacción Estratégica

La inacción es una decisión activa, no un default:

```
FUNCTION ShouldAct(utility, uncertainty, budget) → bool:

    // No actuar si:
    SI utility.total <= 0:
        RETURN False  // Razón: utilidad negativa o nula

    SI uncertainty.total > 0.7 Y utility.total < 2.0:
        RETURN False  // Razón: demasiada incertidumbre para poca ganancia

    SI budget.remaining < budget.total * 0.1:
        RETURN False  // Razón: presupuesto cognitivo insuficiente

    // Actuar solo si:
    SI utility.total > 1.0 Y uncertainty.total < 0.3:
        RETURN True   // Alta confianza, alta utilidad

    SI utility.value_of_information > utility.cost * 2:
        RETURN True   // El valor de aprender justifica el costo

    // Zona gris: experimentar, no ejecutar
    RETURN "experiment"  // Decisión intermedia
```

## 7. Metaobjetivo de la Inacción

```
La inacción se considera ÉXITO DEL SISTEMA cuando:

    1. utility.total <= 0 después de evaluación rigurosa
    2. uncertainty.total < 0.2 (el sistema ya está cerca del óptimo)
    3. No existe hipótesis con confidence > 0.5 sin falsar
    4. El costo de seguir investigando > beneficio esperado

En estos casos, se registra:
    - "Inacción estratégica: sistema en estado cercano al óptimo"
    - Se actualiza memoria estratégica con la decisión
    - Se liberan recursos cognitivos para el siguiente ciclo
```

## 8. Protocolo de Cancelación Automática

```
FUNCTION AutoCancel(investigation, budget):

    SI investigation.cost_accumulated > budget.allocated * 1.5:
        → Cancelar
        → Registrar motivo
        → NO revertir (no hay cambios que revertir)
        → Actualizar memoria estratégica:
            "La investigación {id} excedió su presupuesto sin resultados concluyentes"

    SI investigation.iterations_without_progress >= 3:
        → Cancelar
        → Registrar: "Estancamiento después de {iterations} iteraciones"
        → Sugerir estrategia alternativa si existe en memoria
```

## 9. Costo de Oportunidad

El sistema evalua explícitamente lo que sacrifica al elegir una opción:

```
OpportunityCost(target_intervention) :=
    max_utility(available_interventions EXCLUDING target_intervention)
    - max_utility(all_available_interventions)
```

Este costo se incluye en la función de utilidad (ver §4).

---

## Apéndice A: Indicadores de Metacognición

| Indicador | Fórmula | Alarma si |
|-----------|---------|-----------|
| Eficiencia cognitiva | `beneficio_neto / costo_cognitivo_total` | < 1.0 |
| Tasa de falsación | `hipótesis_falsadas / total_hipótesis` | > 0.8 |
| Retorno de inversión | `utilidad_generada / presupuesto_gastado` | < 0.5 |
| Velocidad de aprendizaje | `nuevas_reglas_semánticas / ciclos_ejecutados` | < 0.1 |
| Precisión del Director | `decisiones_acertadas / total_decisiones` | < 0.6 |
