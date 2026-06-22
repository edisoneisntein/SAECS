# SAECS-005: Memoria Evolutiva

**Estado:** Borrador  
**Prioridad:** Especificación Fundamental  
**Dependencias:** SAECS-001, SAECS-002  
**Descripción:** Define cómo el sistema aprende, olvida, resume y reutiliza conocimiento. La memoria no es un registro pasivo sino un motor activo de capital cognitivo.

---

## 1. Propósito

Establecer la arquitectura formal de la memoria del SAECS. A diferencia de una base de datos, la Memoria Evolutiva clasifica el conocimiento por tipo y nivel de confianza, generaliza patrones, y poda información redundante o irrelevante.

## 2. Arquitectura de Tres Capas

```
┌─────────────────────────────────────────────────────┐
│                  MEMORIA ESTRATÉGICA                │
│   Cómo pensar: estrategias, meta-reglas,           │
│   lecciones sobre el proceso de investigación       │
├─────────────────────────────────────────────────────┤
│                  MEMORIA SEMÁNTICA                  │
│   Qué aprendimos: patrones, reglas generalizadas,   │
│   relaciones causales, conocimiento del dominio     │
├─────────────────────────────────────────────────────┤
│                  MEMORIA EPISÓDICA                  │
│   Qué ocurrió: eventos crudos, timelines,           │
│   resultados de experimentos, decisiones tomadas    │
└─────────────────────────────────────────────────────┘
```

## 3. Memoria Episódica

### 3.1 Estructura

```
EpisodicEntry := {
    id: UUID,
    timestamp: datetime,
    event_type: string,
    description: string,
    outcome: enum {success, failed, cancelled, rolled_back, inaction},
    domain: string,
    metadata: {
        confidence_before: float?,
        confidence_after: float?,
        uncertainty_before: float?,
        uncertainty_after: float?,
        cognitive_cost: float?,
        utility: float?
    },
    hypotheses: [HypothesisID],
    evidence: [EvidenceID],
    tags: [string]
}
```

### 3.2 Protocolo de Almacenamiento

```
AL COMPLETAR cualquier estado del ciclo cognitivo:

    1. CREAR EpisodicEntry con el resultado
    2. ASIGNAR tags automáticos: dominio, tipo_evento, outcome
    3. SI outcome == "success":
       → INCREMENTAR contador de éxito para este tipo de evento
    4. SI outcome == "failed" O "rolled_back":
       → REGISTRAR como "fracaso documentado"
       → EXTRACTAR aprendizaje para memoria semántica
    5. SI el episodio es similar (distancia < 0.2) a uno existente:
       → FUSIONAR: mantener el más reciente, preservar evidencia
```

### 3.3 Protocolo de Olvido

```
FOR EACH EpisodicEntry donde edad > TTL:

    SI outcome == "success" Y ya existe patrón semántico equivalente:
        → ARCHIVAR (comprimir a resumen de 1 línea)

    SI outcome == "failed" Y no se ha referenciado en > 30 días:
        → CONSERVAR solo metadatos (qué, cuándo, outcome)
        → ELIMINAR hipótesis y evidencia asociada

    SI outcome == "inaction" Y no aporta aprendizaje:
        → ELIMINAR directamente

    SI entry se ha referenciado en los últimos 7 días:
        → EXTENDER TTL en 30 días (refuerzo)

TTL por defecto:
    success: 90 días
    failed: 180 días (los fracasos valen más)
    rolled_back: 180 días
    inaction: 30 días
```

## 4. Memoria Semántica

### 4.1 Estructura

```
SemanticRule := {
    id: UUID,
    topic: string,
    rule: string,
    evidence_summary: string,
    confidence: float ∈ [0,1],
    weight: float,                # cantidad de episodios que la soportan
    source_episodes: [EpisodicEntryID],
    type: enum {
        pattern,                  # "cuando X, generalmente Y"
        causal_relation,          # "X causa Y"
        heuristic,                # "X suele funcionar mejor"
        invariant,                # "X siempre es cierto"
        negative_result           # "X nunca funcionó"
    },
    created_at: datetime,
    last_confirmed: datetime,
    applicability: {              # condiciones bajo las que aplica
        domain: [string],
        min_confidence: float,
        context: dict
    }
}
```

### 4.2 Protocolo de Generalización

```
FUNCTION Generalize(episodes[]):

    patterns = GROUP episodes BY description_prefix

    FOR (pattern, group) IN patterns:
        rate = count(group.success) / len(group)
        IF len(group) >= 3:
            CREATE SemanticRule(
                type="pattern",
                topic=pattern.domain,
                rule=f"Patrón: {pattern.short_desc} → {rate:.0%} éxito",
                confidence=rate,
                weight=len(group),
                source_episodes=[e.id FOR e IN group]
            )

    causal = FIND causal_relations(episodes)
    FOR relation IN causal:
        CREATE SemanticRule(
            type="causal_relation",
            rule=relation.description,
            confidence=relation.confidence,
            weight=relation.evidence_count
        )
```

### 4.3 Protocolo de Confianza

```
AL CREAR regla semántica:
    confidence_inicial = tasa_éxito * 0.8  (penalización por generalización)

AL CONFIRMAR regla con nuevo episodio:
    confidence = confidence * 0.9 + nuevo_resultado * 0.1

AL ENCONTRAR contraejemplo:
    confidence = confidence * 0.5
    SI confidence < 0.2:
        → INVALIDAR regla
        → MOVER a "reglas descartadas"
        → REGISTRAR contraejemplo como episodio

Nunca permitir confidence > 0.95 sin:
    - Mínimo 10 episodios de soporte
    - Mínimo 3 fuentes independientes
    - Al menos 1 intento de falsación documentado
```

## 5. Memoria Estratégica

### 5.1 Estructura

```
StrategicKnowledge := {
    id: UUID,
    type: enum {
        strategy_effectiveness,    # qué tan bien funciona cada estrategia
        budget_lesson,             # lecciones sobre presupuesto cognitivo
        meta_pattern,              # patrones sobre el proceso de investigación
        parameter_calibration,     # ajustes de parámetros del sistema
        failure_pattern            # patrones de fracaso del propio SAECS
    },
    observation: string,
    implication: string,
    effectiveness: float,          # qué tan útil ha sido este conocimiento
    times_applied: int,
    domain: string?,
    timestamp: datetime
}
```

### 5.2 Protocolo de Meta-Aprendizaje

```
AL COMPLETAR CICLO:

    1. Calcular eficiencia del ciclo:
       eficiencia = utility_generada / costo_cognitivo

    2. SI eficiencia < umbral (0.5):
       → ALMACENAR en estratégica:
         "Ciclo de baja eficiencia. Estrategia actual puede ser inadecuada."

    3. ACUMULAR métricas de efectividad por estrategia:

       Estrategia A: 3 usos, eficiencia promedio 0.7
       Estrategia B: 2 usos, eficiencia promedio 0.3

    4. RECOMENDAR estrategia con mayor eficiencia histórica
       para contextos similares

    5. SI una estrategia tiene eficiencia < 0.2 tras 5 usos:
       → MARCAR como "deprecated"
       → NO recomendar en futuros ciclos
```

### 5.3 Protocolo de Podado Estratégico

```
FOR EACH StrategicKnowledge donde edad > 60 días:

    SI effectiveness < 0.3 Y times_applied < 3:
        → ELIMINAR (nunca fue útil)

    SI effectiveness < 0.2 Y times_applied >= 3:
        → ARCHIVAR en "lecciones negativas" (puede ser útil como contraejemplo)

    SI effectiveness > 0.8 Y times_applied >= 5:
        → PROMOVER a regla por defecto del sistema
```

## 6. Protocolo de Búsqueda y Recuperación

El sistema consulta las tres memorias simultáneamente:

```
FUNCTION QueryMemory(problem, context) → QueryResult:

    result = QueryResult()

    // Memoria episódica: eventos similares
    result.similar_episodes = episodic.find(
        query=problem.description,
        limit=5,
        min_similarity=0.3
    )

    // Memoria semántica: reglas aplicables
    result.applicable_rules = semantic.recall(
        topic=problem.domain,
        min_confidence=0.3
    )

    // Memoria estratégica: estrategias efectivas
    result.recommended_strategies = strategic.recommend(
        domain=problem.domain,
        context=context
    )

    // Síntesis: generar respuesta integrada
    result.synthesis = Synthesize(
        episodes=result.similar_episodes,
        rules=result.applicable_rules,
        strategies=result.recommended_strategies
    )

    RETURN result
```

## 7. Protocolo de Reutilización

```
FUNCTION ReuseKnowledge(problem, memory) → bool:

    similar = memory.episodic.find_similar(problem)

    FOR episode IN similar:
        SI episode.hypotheses_failed:
            // No repetir: las hipótesis ya fueron falsadas
            MARK as "avoid"
            RETURN False

        SI episode.outcome == "success":
            // Reaplicar con ajuste de confianza
            confidence = episode.confidence * 0.9
            IF confidence > 0.6:
                RETURN True  // Se puede reutilizar

    RETURN False  // No hay conocimiento reutilizable
```

## 8. Métricas de Salud de la Memoria

| Métrica | Fórmula | Objetivo |
|---------|---------|----------|
| Tasa de acierto | `éxitos / total_consultas` | > 0.6 |
| Tasa de reutilización | `consultas_con_resultado / total_consultas` | > 0.4 |
| Densidad de conocimiento | `reglas_semánticas / dominio` | > 2 por dominio |
| Frescura | `episodios_recientes / total_episodios` | > 0.3 |
| Tasa de olvido | `episodios_podados / total_episodios` | < 0.1 por ciclo |

---

## Apéndice A: Ciclo de Mantenimiento de Memoria

```
CADA 10 ciclos:

    1. EJECUTAR podado episódico (olvido)
    2. EJECUTAR generalización semántica de episodios recientes
    3. ACTUALIZAR confianza de reglas semánticas
    4. CALIBRAR parámetros estratégicos
    5. COMPACTAR almacenamiento (desfragmentar, comprimir)
    6. REPORTAR salud de memoria al Governance
```
