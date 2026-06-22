# SAECS-009: Learning & Self-Modification

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001, SAECS-004, SAECS-005, SAECS-008  
**Descripción:** Define cómo el SAECS aprende de la experiencia, modifica sus propios parámetros, evoluciona su función de utilidad, y se rediseña a sí mismo dentro de límites de seguridad.

---

## 1. Propósito

La capacidad de auto-modificación distingue un sistema adaptativo de uno estático. Este RFC establece los protocolos para que el SAECS mejore sus propios mecanismos de decisión, memoria y metacognición sin comprometer su estabilidad.

## 2. Jerarquía de Aprendizaje

```
Nivel 1: Aprendizaje de parámetros
    Ajustar umbrales, pesos, tasas dentro de la arquitectura actual.
    Ejemplo: "El umbral de incertidumbre 0.7 era óptimo para dominio X."
    Seguro: siempre (cambios reversibles)

Nivel 2: Aprendizaje de estrategias
    Seleccionar entre estrategias de decisión existentes.
    Ejemplo: "En contextos de alta incertidumbre, MCTS funciona mejor."
    Seguro: siempre (solo cambia la selección)

Nivel 3: Aprendizaje de arquitectura
    Modificar estructura de componentes, añadir/eliminar módulos.
    Ejemplo: "Añadir un validador cruzado entre experimenter y auditor."
    Seguro: con validación y aprobación del Governance

Nivel 4: Aprendizaje de objetivos
    Modificar la función de utilidad, metas, restricciones.
    Ejemplo: "La utility actual no penaliza suficiente la deuda técnica."
    Seguro: con cuarentena y rollback automático

Nivel 5: Meta-aprendizaje
    Aprender a aprender: modificar la tasa de aprendizaje, la exploración.
    Ejemplo: "Reducir exploration_rate porque el sistema ya converge."
    Seguro: monitoreado por Governance
```

## 3. Protocolo de Auto-Modificación

### 3.1 Propuesta

```
FUNCTION ProposeModification(current_state, performance_gap) → Modification:

    gap = performance_gap  // diferencia entre rendimiento actual y esperado

    SI gap.attributable_to_parameter_x:
        RETURN Modification(
            target="parameter",
            component="director",
            parameter="uncertainty_threshold",
            current_value=current_state.uncertainty_threshold,
            proposed_value=current_state.uncertainty_threshold + gap.direction * 0.05,
            rationale=f"Ajuste por brecha de {gap.value:.2f} en {gap.metric}"
        )

    SI gap.attributable_to_strategy:
        RETURN Modification(
            target="strategy",
            component="decision_engine",
            parameter="active_strategy",
            proposed_value=SelectStrategy(current_state.context),
            rationale="Cambio de estrategia basado en rendimiento histórico"
        )

    SI gap.attributable_to_architecture:
        RETURN Modification(
            target="architecture",
            component=gap.component,
            parameter=gap.parameter,
            proposed_value=gap.proposed_value,
            rationale=f"Modificación arquitectónica: {gap.description}",
            level=3  // requiere aprobación
        )
```

### 3.2 Validación

```
FUNCTION ValidateModification(modification) → ValidationResult:

    // Nivel 1: siempre aprobado
    SI modification.level == 1:
        RETURN ValidationResult(approved=true)

    // Nivel 2: requiere 2 ciclos de prueba
    SI modification.level == 2:
        simulated = SimulateWithModification(modification, cycles=2)
        SI simulated.utility > current.utility * 0.95:
            RETURN ValidationResult(approved=true)
        ELSE:
            RETURN ValidationResult(approved=false, reason="degradación")

    // Nivel 3+: requiere aprobación del Governance
    SI modification.level >= 3:
        // Modo cuarentena
        CreateSnapshot()
        ApplyModification(modification)
        RunValidationSuite()
        SI all_validations_pass:
            RETURN ValidationResult(approved=true)
        ELSE:
            Rollback()
            RETURN ValidationResult(approved=false, reason="validación fallida")
```

### 3.3 Implementación

```
FUNCTION ApplyModification(modification):

    // Preservar estado anterior para rollback
    old_state = Snapshot(modification.target)

    CREAR backup en memoria estratégica

    SI modification.target == "parameter":
        SetParameter(modification.component, modification.parameter, modification.proposed_value)

    SI modification.target == "strategy":
        SwitchStrategy(modification.proposed_value)

    SI modification.target == "architecture":
        // Desplegar en paralelo, no reemplazar
        DeployAlongside(modification.component, modification.proposed_value)
        // Validar durante N ciclos antes de conmutar
        ScheduleValidation(modification, cycles=10)

    REGISTRAR en memoria episódica:
        "Modificación {id}: {modification.rationale[:100]}"

    SI modification.level <= 2:
        CONFIRMAR inmediatamente
    ELSE:
        ENTRAR en período de observación (N ciclos)
```

### 3.4 Rollback

```
FUNCTION Rollback(modification):

    SI modification.level <= 2:
        Revertir parámetro a old_state
        REGISTRAR: "Rollback por bajo rendimiento"

    SI modification.level >= 3:
        Restaurar desde snapshot
        REGISTRAR: "Rollback arquitectónico: {reason}"
        // No proponer misma modificación por 30 ciclos
        BLACKLIST(modification, duration=30)

    ACTUALIZAR memoria estratégica:
        "{modification} falló. Revertido."
```

## 4. Tasa de Aprendizaje Adaptativa

```
FUNCTION AdaptiveLearningRate(performance_history):

    trend = Slope(performance_history[-10:])

    SI trend > 0.05:  // mejorando rápido
        learning_rate = learning_rate * 0.95  // reducir, ya funciona
    SI trend < -0.05:  // empeorando
        learning_rate = learning_rate * 1.1   // aumentar, necesita cambiar
    SI abs(trend) < 0.01:  // estancado
        learning_rate = learning_rate * 1.2   // explorar más

    RETURN clamp(learning_rate, 0.01, 0.5)
```

## 5. Caja de Herramientas de Auto-Modificación

| Nivel | Componente | Qué puede aprender | Seguridad |
|-------|------------|-------------------|-----------|
| 1 | Director | Umbrales de decisión | Automática |
| 1 | Utility | Pesos de términos VOI, learning, riesgo | Automática |
| 1 | Auditor | Profundidad de falsación | Automática |
| 2 | Decisión | Estrategia activa (MCTS, Bayes, etc.) | 2 ciclos |
| 3 | Memoria | TTL, políticas de podado, generalización | Cuarentena |
| 3 | Hipótesis | Número de hipótesis, método de competencia | Cuarentena |
| 4 | Utility | Términos completos, estructura de la función | Governance |
| 4 | Objetivos | Metas, prioridades, restricciones | Governance |
| 5 | Governance | Su propia tasa de revisión, criterios | Governance+ |

---

## Apéndice A: Principios de Seguridad en Auto-Modificación

1. **Una modificación a la vez**: No aplicar cambios concurrentes en diferentes niveles
2. **Reversibilidad**: Toda modificación debe tener un snapshot previo
3. **Período de observación**: Toda modificación nivel 3+ requiere N ciclos de monitoreo
4. **Límite de tasa**: Máximo 1 modificación nivel 3+ cada 10 ciclos
5. **Conservadurismo creciente**: A mayor nivel, mayor validación requerida
6. **Registro obligatorio**: Toda modificación se registra en los tres tipos de memoria
