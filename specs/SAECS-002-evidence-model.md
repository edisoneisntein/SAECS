# SAECS-002: Modelo de Evidencia

**Estado:** Borrador  
**Prioridad:** Especificación Fundamental  
**Dependencias:** SAECS-001  
**Descripción:** Define qué constituye evidencia, cómo se mide, cómo se acumula y bajo qué condiciones se invalida.

---

## 1. Propósito

Establecer el marco formal para que el SAECS distinga entre datos, evidencia y conocimiento. Sin este modelo, el sistema no puede determinar objetivamente si una hipótesis está soportada o refutada.

## 2. Jerarquía del Conocimiento

```
Conocimiento (máxima certeza)
    ↑
Generalizaciones / Patrones
    ↑
Evidencia corroborada (múltiples fuentes)
    ↑
Evidencia simple (una fuente)
    ↑
Datos observacionales
    ↑
Ruido / Señales sin procesar
```

## 3. Definición Formal de Evidencia

```
Evidence := {
    id: UUID,
    type: enum {
        metric,           # medición cuantitativa (latencia, memoria, etc.)
        test_result,      # paso/fallo de una prueba
        observation,      # dato observado sin interpretación
        log_entry,        # registro de un evento en bitácora
        analysis,         # resultado de análisis estático/dinámico
        historical,       # dato proveniente de memoria episódica
        experiment        # resultado de un experimento controlado
    },
    value: Any,           # el dato concreto
    confidence: float ∈ [0,1],  # confianza en que el dato es correcto
    source: string,       # identificador de la fuente
    timestamp: datetime,
    context: dict,        # condiciones bajo las que se obtuvo
    validity: enum {
        valid,            # evidencia vigente
        expired,          # evidencia cuya fuente ya no es confiable
        superseded,       # reemplazada por evidencia más reciente
        invalidated       # demostrada como incorrecta
    }
}
```

## 4. Protocolo de Acumulación

La evidencia se acumula en un **vector de soporte** para cada proposición:

```
SupportVector(proposition P) := {
    for_evidence: [Evidence],    # evidencia a favor
    against_evidence: [Evidence], # evidencia en contra
    net_weight: float            # Σ(for.weight) - Σ(against.weight)
}
```

**Reglas de acumulación:**

```
AL RECIBIR nueva evidencia E para proposición P:

1. SI E.type == "experiment" Y E.valor == "failed":
   → AGREGAR a against_evidence
   → SI E.confidence > 0.8: INVALIDAR P inmediatamente

2. SI E.type == "metric" Y E.valor mejora línea base:
   → AGREGAR a for_evidence
   → ACTUALIZAR confidence.weight de P

3. SI E.type == "test_result" Y E.valor == "fail":
   → AGREGAR a against_evidence
   → SI count(against) >= 3 DE FUENTES INDEPENDIENTES:
     → INVALIDAR P

4. SI count(for_evidence) >= 5 DE FUENTES INDEPENDIENTES:
   → PROMOVER P a "patrón" en memoria semántica
```

## 5. Umbrales de Evidencia

| Nivel | Evidencia requerida | Acción permitida |
|-------|---------------------|------------------|
| `E0: Sin evidencia` | `support.net_weight = 0` | Solo investigar |
| `E1: Sospecha` | `support.net_weight > 0.3` | Generar hipótesis |
| `E2: Indicio` | `support.net_weight > 0.5` | Experimentar |
| `E3: Corroborado` | `support.net_weight > 0.7` | Ejecutar cambio |
| `E4: Demostrado` | `support.net_weight > 0.9` | Promover a regla semántica |

## 6. Invalidación de Evidencia

```
Evidence.Invalidated := {
    reason: string,
    by: Evidence,           # la evidencia que contradice
    timestamp: datetime,
    confidence_drop: float  # cuanto baja la confianza de la proposición
}
```

**Protocolo de invalidación:**

```
AL RECIBIR evidencia contradictoria E_contra sobre proposición P:

1. SI E_contra.confidence > max(for_evidence.confidence):
   → INVALIDAR toda for_evidence con confidence < E_contra.confidence
   → RE-EVALUAR P con solo la evidencia restante
   → SI P ya no tiene soporte: DESCARTAR P

2. SI E_contra.type == "experiment" Y E_contra es reproducible:
   → INVALIDACIÓN TOTAL de P
   → REGISTRAR en memoria como "fracaso documentado"
   → ACTUALIZAR probabilidad de éxito en memoria estratégica
```

## 7. Ciclo de Vida de la Evidencia

```
                    ┌──────────────┐
                    │  Recolectada │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
               ┌───│  Validada    │───┐
               │   └──────┬───────┘   │
               │          │           │
               ▼          ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Activa   │ │ Superseded│ │ Inválida │
        └──────────┘ └──────────┘ └──────────┘
               │
               ▼
        ┌──────────┐
        │ Expirada │ (por tiempo o por nueva fuente)
        └──────────┘
```

## 8. Independencia de Fuentes

Para evitar sesgo de confirmación, el sistema exige **independencia**:

```
Fuente := {
    id: string,
    type: enum {metric_provider, test_suite, log_aggregator, analyzer, external},
    independence_score: float ∈ [0,1]
}
```

**Regla de independencia:**
- Dos fuentes son independientes si `correlación( fuente_A, fuente_B ) < 0.3`
- Para alcanzar nivel `E3`, se requieren al menos **2 fuentes independientes**
- Para `E4`, se requieren al menos **3 fuentes independientes**

## 9. Valor de la Evidencia

Cada pieza de evidencia tiene un "valor de información" calculado:

```
VOI(evidence) = H(before) - H(after)

Donde:
    H = incertidumbre epistémica sobre la proposición
    before = incertidumbre antes de la evidencia
    after = incertidumbre después de la evidencia
```

Este VOI alimenta la función de utilidad general (SAECS-001, sección 5).

---

## Apéndice A: Checklist de Evidencia

Antes de que cualquier proposición sea aceptada:

- [ ] ¿Existe al menos una pieza de evidencia directa?
- [ ] ¿La evidencia es reproducible?
- [ ] ¿Proviene de al menos dos fuentes independientes?
- [ ] ¿Se ha intentado falsar?
- [ ] ¿La evidencia en contra ha sido considerada?
- [ ] ¿La confianza de la evidencia supera el umbral del nivel requerido?
