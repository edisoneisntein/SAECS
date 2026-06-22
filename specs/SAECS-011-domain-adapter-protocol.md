# SAECS-011: Domain Adapter Protocol

**Estado:** Borrador  
**Prioridad:** Especificación Crítica  
**Dependencias:** SAECS-001  
**Descripción:** Define el protocolo formal para conectar nuevos dominios (software, robótica, medicina, biología, etc.) al núcleo cognitivo del SAECS sin modificar el core.

---

## 1. Propósito

El SAECS es un sistema cognitivo general. Para aplicarlo a un dominio específico, necesita un adaptador que traduzca entre el lenguaje abstracto del core y los conceptos concretos del dominio. Este RFC establece el contrato que todo adaptador debe cumplir.

## 2. Arquitectura del Adaptador

```
DomainAdapter := {
    domain: string,          # nombre del dominio
    version: string,         # versión del adaptador
    interface: {
        // El core llama a estos métodos
        methods: DomainMethods,
        events: DomainEvents
    },
    hooks: {
        // El adaptador recibe estos eventos del core
        on_hypothesis_generated: (hypothesis) → DomainAction?,
        on_experiment_design: (experiment) → DomainExperiment?,
        on_result: (result) → DomainInterpretation?,
        on_execution: (action) → DomainOutcome?
    },
    schema: DomainSchema     # define tipos del dominio
}
```

## 3. DomainSchema

Define la ontología del dominio:

```
DomainSchema := {
    entities: {
        entity_name: {
            fields: {field_name: Type},
            relations: [{entity: string, type: string}],
            observables: [MethodSignature],   # qué se puede medir
            intervenibles: [MethodSignature]  # qué se puede cambiar
        }
    },
    metrics: {
        metric_name: {
            type: enum {scalar, vector, categorical, ordinal},
            range: [min, max],
            unit: string,
            uncertainty: Type               # cómo se mide la incertidumbre
        }
    },
    signals: {
        signal_name: {
            description: string,
            payload_schema: Type,
            source: enum {system, user, environment}
        }
    },
    actions: {
        action_name: {
            description: string,
            parameters: {param_name: Type},
            preconditions: [Condition],
            postconditions: [Condition],
            estimated_cost: float
        }
    },
    constraints: {
        constraint_name: {
            description: string,
            validator: MethodSignature,     # función que verifica si se cumple
            violation_behavior: enum {block, warn, ignore}
        }
    }
}
```

## 4. DomainMethods

Métodos obligatorios que el adaptador debe implementar:

```
DomainMethods := {
    // Lectura del dominio
    observe: (query: ObservationQuery) → ObservationResult,
    // "Dame las métricas actuales del sistema"
    //
    // ObservationQuery = {
    //   metrics: [metric_name],
    //   entities: [entity_filter],
    //   since: datetime?,
    //   confidence_threshold: float?
    // }

    // Escritura en el dominio
    intervene: (action: DomainAction) → ActionResult,
    // "Ejecuta esta acción en el sistema real"
    //
    // ActionResult = {
    //   success: boolean,
    //   outcome: any,
    //   side_effects: [SideEffect],
    //   confidence: float,
    //   duration: float
    // }

    // Experimentación segura
    simulate: (experiment: DomainExperiment) → SimulationResult,
    // "Simula este experimento sin tocar el sistema real"
    //
    // DomainExperiment = {
    //   actions: [DomainAction],
    //   initial_state: StateSnapshot?,
    //   horizon: int
    // }

    // Validación de seguridad
    validate: (action: DomainAction) → SafetyVerdict,
    // "¿Es seguro ejecutar esta acción?"
    //
    // SafetyVerdict = {
    //   safe: boolean,
    //   risks: [{description: string, probability: float}],
    //   requires_human_approval: boolean
    // }

    // Estado del dominio
    health: () → DomainHealth,
    // "¿Cómo está el dominio?"
    //
    // DomainHealth = {
    //   status: enum {healthy, degraded, critical},
    //   metrics: {metric_name: value},
    //   issues: [{severity, description}]
    // }
}
```

## 5. DomainEvents

Eventos que el adaptador emite al core:

```
DomainEvents := {
    "metric.change": {
        metric: string,
        old_value: any,
        new_value: any,
        delta: float,
        timestamp: datetime
    },
    "anomaly.detected": {
        entity: string,
        metric: string,
        expected_range: [min, max],
        actual_value: any,
        severity: float
    },
    "constraint.violation": {
        constraint: string,
        action: DomainAction?,
        details: string
    },
    "external.signal": {
        source: string,
        type: string,
        payload: any,
        confidence: float
    },
    "health.change": {
        from: DomainHealth,
        to: DomainHealth,
        reason: string
    }
}
```

## 6. Ciclo de Traducción

```
domain → core:
    "La cobertura de tests bajó de 80% a 60%"
    → DomainAdapter.parse(event)
    → Evento abstracto: metric.change(metric=test_coverage, delta=-0.25)
    → Core procesa: ¿investigar? ¿experimentar? ¿revertir?

core → domain:
    "Investigar por qué bajó la cobertura"
    → Core genera: hypothesis(attribute=test_coverage, cause=?)
    → DomainAdapter.translate(hypothesis)
    → Acción concreta: "scanea commits recientes por falta de tests"
    → DomainAdapter.intervene(action)
```

## 7. Registro y Descubrimiento de Adaptadores

```
FUNCTION RegisterAdapter(adapter: DomainAdapter):

    // 1. Validar esquema
    FOR method IN DomainMethods.REQUIRED:
        ASSERT adapter.implements(method), f"{method} es obligatorio"

    // 2. Registrar en el core
    DomainRegistry.register(adapter)

    // 3. Inicializar health check
    adapter.health()

    // 4. Emitir evento de registro
    Bus.emit("domain.registered", adapter.domain)

    // 5. Subscribe a eventos del adaptador
    FOR event IN adapter.events:
        Bus.subscribe(event, adapter.domain)

FUNCTION DiscoverDomain(path: string) → DomainAdapter?:

    // Buscar adaptadores en un directorio
    FOR file IN glob(path + "/domain_*/"):
        CONFIG = load_yaml(file + "/saecs_domain.yaml")
        SI CONFIG.schema_version == "SAECS-011":
            adapter_class = Import(file + "/adapter.py")
            RETURN adapter_class(CONFIG)

    RETURN None
```

## 8. Ejemplo: Software Domain (refactorizado)

```
software_adapter = DomainAdapter(
    domain="software",
    version="1.0",
    schema=DomainSchema(
        entities={
            "repository": {
                fields: {name, language, test_framework},
                observables: [test_coverage, build_status, lint_errors],
                intervenibles: [create_pr, run_tests, refactor]
            }
        },
        metrics={
            "test_coverage": {type: scalar, range: [0,100]},
            "build_duration": {type: scalar, unit: "seconds"},
            "error_rate": {type: scalar, range: [0,1]}
        },
        signals={
            "code_pushed": {description: "Nuevo commit"},
            "build_failed": {description: "Build roto"},
            "deploy_completed": {description: "Deploy exitoso"}
        },
        constraints={
            "no_breaking_changes": {
                description: "No introducir breaking changes sin approval",
                validator: CheckBreakingChanges,
                violation_behavior: "block"
            }
        }
    ),
    methods=SoftwareDomainMethods(),
    hooks=SoftwareDomainHooks()
)
```

---

## Apéndice A: Migración desde v3 existente

El adaptador actual en `saecs/domains/software/` debe refactorizarse para implementar `DomainAdapter`:

| Actual | Nuevo |
|--------|-------|
| `SoftwareScanner` | `DomainMethods.observe` |
| `SoftwareDomainHook` | `DomainMethods.simulate` + `DomainMethods.intervene` |
| (falta) | `DomainMethods.validate` |
| (falta) | `DomainMethods.health` |
