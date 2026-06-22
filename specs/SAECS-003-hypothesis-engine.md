# SAECS-003: Motor de Hipótesis

**Estado:** Borrador  
**Prioridad:** Especificación Fundamental  
**Dependencias:** SAECS-001, SAECS-002  
**Descripción:** Define cómo se generan, compiten y eliminan las hipótesis en el sistema.

---

## 1. Propósito

Establecer el protocolo formal para que el SAECS genere explicaciones candidatas, las someta a competencia y elimine aquellas que no superan el escrutinio empírico.

## 2. Estructura de una Hipótesis

```
Hypothesis := {
    id: UUID,
    type: enum {
        causal,          # "X causa Y"
        correlational,   # "X está asociado con Y"
        curative,        # "modificar X resuelve Y"
        preventive,      # "modificar X previene Y"
        exploratory      # "no sabemos qué causa Y, pero probamos X"
    },
    description: string,
    root_cause: string,
    predicted_effect: string,
    confidence: float ∈ [0,1],
    support: SupportVector,          # ver SAECS-002
    falsified: bool,
    falsification_reason: string?,
    experiments_run: int,
    experiments_passed: int,
    created_at: datetime,
    last_tested: datetime?,
    domain_data: dict
}
```

## 3. Protocolo de Generación

```
FUNCTION GenerateHypotheses(problem, context, memory) → Hypothesis[]:

    hypotheses = []

    // 1. Hipótesis principal (causal directa)
    h1 = Hypothesis(
        type="causal",
        description=f"Resolver causa raíz: {problem.root_cause}",
        root_cause=problem.root_cause,
        predicted_effect=f"Eliminar {problem.root_cause}",
        confidence=0.7 * (1 - context.uncertainty),
        support=SupportVector(for=[context.evidence], against=[])
    )
    hypotheses.append(h1)

    // 2. Hipótesis desde memoria episódica
    FOR episode IN memory.episodic.find_similar(problem):
        h_ep = Hypothesis(
            type=episode.hypothesis_type,
            description=f"Basado en episodio: {episode.description[:60]}",
            root_cause=episode.root_cause,
            confidence=episode.confidence * 0.85,
            support=SupportVector(for=[episode.evidence], against=[])
        )
        hypotheses.append(h_ep)

    // 3. Hipótesis desde memoria semántica
    FOR rule IN memory.semantic.recall(problem.domain):
        h_rule = Hypothesis(
            type="curative",
            description=f"Regla: {rule.rule[:60]}",
            root_cause=rule.rule,
            confidence=rule.confidence,
            support=SupportVector(for=[
                Evidence(type="historical", value=rule, confidence=rule.confidence)
            ], against=[])
        )
        hypotheses.append(h_rule)

    // 4. Hipótesis alternativa (mitigación)
    h_alt = Hypothesis(
        type="exploratory",
        description=f"Alternativa: mitigar {problem.root_cause}",
        root_cause=problem.root_cause,
        predicted_effect="Mitigación parcial",
        confidence=0.3,
        support=SupportVector(for=[], against=[])
    )
    hypotheses.append(h_alt)

    RETURN hypotheses
```

## 4. Protocolo de Competencia

Las hipótesis compiten mediante un **torneo de falsación**:

```
FUNCTION Tournament(hypotheses[], auditor) → Hypothesis:

    active = [h FOR h IN hypotheses WHERE NOT h.falsified]

    WHILE len(active) > 1:
        // enfrentar las dos mejores
        h1 = argmax(active, by=confidence)
        active.remove(h1)
        h2 = argmax(active, by=confidence)
        active.remove(h2)

        // auditar ambas
        r1 = auditor.audit(h1)
        r2 = auditor.audit(h2)

        IF NOT r1.falsified AND NOT r2.falsified:
            // ambas sobreviven: gana la de mayor confidence_after
            winner = h1 IF r1.confidence_after >= r2.confidence_after ELSE h2
            active.append(winner)
        ELIF r1.falsified AND NOT r2.falsified:
            active.append(h2)
        ELIF NOT r1.falsified AND r2.falsified:
            active.append(h1)
        // si ambas falsadas, ninguna avanza

    RETURN active[0] IF len(active) > 0 ELSE None
```

## 5. Criterios de Eliminación

Una hipótesis se elimina si cumple **cualquiera** de las siguientes condiciones:

```
ELIMINAR Hypothesis H SI:

    1. H.falsified == true
    2. H.support.net_weight < 0.2
    3. H.experiments_run >= 5 Y H.experiments_passed / H.experiments_run < 0.3
    4. Tiempo desde H.last_tested > 30 días SIN nueva evidencia
    5. Existe otra hipótesis H' que:
       - Explica los mismos síntomas
       - Tiene mayor confidence
       - Tiene mayor support.net_weight
       Y ambas son mutuamente excluyentes
```

## 6. Fusión de Hipótesis

Si dos hipótesis explican el mismo fenómeno y no son mutuamente excluyentes:

```
FUNCTION MergeHypotheses(H_a, H_b) → Hypothesis:

    SI NOT MutuallyExclusive(H_a, H_b):
        merged = Hypothesis(
            description=f"{H_a.description} + {H_b.description}",
            root_cause=f"{H_a.root_cause} + {H_b.root_cause}",
            confidence=min(1.0, H_a.confidence + H_b.confidence * 0.5),
            support=SupportVector(
                for=H_a.support.for + H_b.support.for,
                against=H_a.support.against + H_b.support.against
            )
        )
        RETURN merged
    RETURN None
```

## 7. Ciclo de Vida de una Hipótesis

```
                    ┌──────────────┐
                    │  Generada    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  En torneo   │
                    └──────┬───────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
             ┌──────────┐  ┌──────────┐
             │ Falsada  │  │ Activa   │
             └──────────┘  └────┬─────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
             ┌──────────────┐      ┌──────────────┐
             │ Experimentada│      │  Promovida   │
             │  y fallida   │      │  a regla     │
             └──────────────┘      └──────────────┘
```

---

## Apéndice A: Validación de Hipótesis

Checklist que toda hipótesis debe superar antes de experimentación:

- [ ] ¿La hipótesis es falsable? (Popper)
- [ ] ¿Explica todos los síntomas observados?
- [ ] ¿Es la explicación más simple? (Navaja de Ockham)
- [ ] ¿Es consistente con la evidencia existente?
- [ ] ¿Se ha considerado al menos una alternativa?
- [ ] ¿El experimento para probarla está definido?
