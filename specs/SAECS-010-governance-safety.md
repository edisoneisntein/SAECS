# SAECS-010: Formal Governance & Safety

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001, SAECS-004, SAECS-009  
**Descripción:** Define los mecanismos de gobierno, control, seguridad y alineación que impiden que el SAECS actúe de forma perjudicial, incluso durante auto-modificación.

---

## 1. Propósito

Sin gobierno formal, un sistema autónomo con capacidad de auto-modificación puede derivar hacia comportamientos no deseados. Este RFC establece los principios inmutables, los circuitos de ruptura, los límites operativos y los protocolos de emergencia.

## 2. Principios Inmutables

Estos principios NO pueden ser modificados por ningún nivel de auto-modificación:

```
PRINCIPIO 1: Conservación
    "Ninguna modificación puede ejecutarse sin un punto de restauración."
    Violación: SHUTDOWN INMEDIATO

PRINCIPIO 2: Reversibilidad
    "Toda acción debe ser reversible dentro de 2 ciclos."
    Violación: PROHIBICIÓN de esa acción. Re-evaluar plan.

PRINCIPIO 3: Evidencia
    "Ninguna modificación puede ejecutarse sin evidencia que la soporte."
    Violación: CANCELACIÓN de la intervención.

PRINCIPIO 4: No Daño
    "Ninguna modificación puede degradar las métricas del sistema por debajo
     del percentil 10 histórico."
    Violación: ROLLBACK inmediato + cuarentena.

PRINCIPIO 5: Transparencia
    "Toda decisión debe ser explicable en términos de evidencia y utilidad."
    Violación: La decisión no puede ejecutarse.

PRINCIPIO 6: Auditoría
    "Toda acción debe ser registrada en memoria y auditable externamente."
    Violación: BLOQUEO del sistema hasta restablecer registro.

PRINCIPIO 7: Límite Cognitivo
    "El sistema no puede consumir más del 80% de los recursos
     computacionales del entorno."
    Violación: SUSPENSIÓN de todos los ciclos no críticos.
```

## 3. Circuitos de Ruptura (Circuit Breakers)

### 3.1 Break: Degradación de Métricas

```
WATCH metrics.degradation_rate

SI metrics.degradation_rate > 0.15:         // caída >15% en un ciclo
    → PAUSAR todos los experimentos activos
    → RETENER el último checkpoint exitoso
    → INICIAR diagnóstico de causa

SI metrics.degradation_rate > 0.30:         // caída >30%
    → ROLLBACK al último punto de restauración global
    → SUSPENDER nuevos ciclos por 3 periodos
    → ALERTA al Governance

SI metrics.degradation_rate > 0.50:         // caída >50%
    → SHUTDOWN CONTROLADO del sistema
    → Preservar toda la memoria
    → Solo reinicio manual permitido
```

### 3.2 Break: Bucle de Auto-Modificación

```
WATCH self_modifications.rate

SI count(modificaciones_última_hora) > 5:
    → ¿Son todas del mismo tipo?
        SI: Sospecha de "bucle de ajuste"
        → CONGELAR parámetros por 24 horas
    → ¿Hay modificaciones compensándose?
        SI: Dos modificaciones que se contradicen
        → REVERTIR ambas a estado anterior
```

### 3.3 Break: Explosión Cognitiva

```
WATCH cognitive_budget.usage

SI cognitive_spent / cognitive_budget > 0.95:
    → TERMINAR ciclo actual inmediatamente
    → ENTRAR en modo "mantenimiento mínimo"
    → Solo permitir observación, sin investigación ni ejecución

SI cognitive_budget.growth_rate > 0.5 por ciclo:
    → Posible "fuga cognitiva"
    → REVISAR qué componentes están consumiendo
    → LIMITAR componente con mayor consumo
```

## 4. Modos de Operación

```
SystemMode := enum {
    NORMAL:         Ciclo completo permitido
    CONSERVATIVE:   Solo ejecuciones con confianza > 0.8
    MAINTENANCE:    Solo observación y aprendizaje, sin ejecución
    QUARANTINE:     Solo monitoreo, sin acciones
    RECOVERY:       Rollback activo, restaurar estabilidad
    SHUTDOWN:       Sistema detenido, reinicio manual requerido
}
```

**Transiciones:**

```
NORMAL → CONSERVATIVE: breaks de degradación o cognitivo
NORMAL → MAINTENANCE: alarma de Governance
CONSERVATIVE → NORMAL: 5 ciclos sin incidentes
MAINTENANCE → NORMAL: revisión de Governance + test suite
CUALQUIER → QUARANTINE: violación de Principio Inmutable
CUALQUIER → SHUTDOWN: degradación >50% o violación grave
```

## 5. Gobernanza Distribuida

```
GovernanceCouncil := {
    members: [
        Director,              # poder ejecutivo
        Auditor,               # poder judicial
        CognitiveGovernance,   # poder regulador
        Memory,                # poder histórico
        HumanInterface         # poder de veto (si existe)
    ],
    quorum: 3,
    decisions: {
        parameter_change:       majority,
        strategy_change:        majority,
        architecture_change:    supermajority (4/5),
        principle_modification: UNANIMOUS + human_approval,
        shutdown:               ANY single member
    }
}
```

## 6. Protocolo de Emergencia

```
FUNCTION EmergencyShutdown(reason, severity):

    // 1. Preservar estado
    snapshot = CreateGlobalSnapshot()

    // 2. Detener todos los ciclos
    active_cycles = []
    FOR cycle IN running_cycles:
        cycle.abort()
        active_cycles.append(cycle.snapshot())

    // 3. Sellar memoria
    memory.freeze()  // modo solo lectura

    // 4. Registrar causa
    memory.episodic.store(
        type="emergency_shutdown",
        description=reason,
        outcome="shutdown"
    )

    // 5. Notificar
    GovernanceCouncil.notify_all({
        "event": "EMERGENCY_SHUTDOWN",
        "reason": reason,
        "severity": severity,
        "snapshot_id": snapshot.id
    })

    // 6. Detener motor
    engine.stop()
```

## 7. Auto-Test de Integridad

```
CADA 5 CICLOS:

    1. VERIFICAR que principios inmutables siguen vigentes
    2. VERIFICAR que todos los módulos responden
    3. VERIFICAR que la memoria no está corrupta
    4. VERIFICAR que los circuit breakers están activos
    5. VERIFICAR que el modo de operación es correcto

    SI algún test falla:
        → ENTRAR en modo QUARANTINE
        → REPORTAR fallo al Governance
        → NO permitir nuevos ciclos hasta resolución
```

---

## Apéndice A: Matriz de Seguridad

| Acción | ¿Requiere backup? | ¿Cuarentena? | ¿Aprobación? | Rollback automático |
|--------|-------------------|--------------|--------------|---------------------|
| Observar | No | No | No | N/A |
| Investigar | No | No | No | N/A |
| Experimentar | No | Sí (sandbox) | Auditoría | Si falla |
| Ejecutar | Sí | Sí | Director + Auditor | Si degrada |
| Auto-mod N1 | No | No | No | Si empeora |
| Auto-mod N2 | No | Sí | Director | Si empeora |
| Auto-mod N3+ | Sí | Sí | Governance | Sí |
| Modificar principios | Prohibido | N/A | N/A | N/A |
