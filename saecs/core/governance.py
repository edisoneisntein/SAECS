from __future__ import annotations
from .bus import MessageBus, Event, EventType, EventPriority
from .types import SystemMode, Modification, PerformanceSnapshot


IMMUTABLE_PRINCIPLES = [
    "Ninguna modificacion puede ejecutarse sin un punto de restauracion",
    "Toda accion debe ser reversible dentro de 2 ciclos",
    "Ninguna modificacion puede ejecutarse sin evidencia que la soporte",
    "Ninguna modificacion puede degradar las metricas del sistema por debajo del percentil 10 historico",
    "Toda decision debe ser explicable en terminos de evidencia y utilidad",
    "Toda accion debe ser registrada en memoria y auditable externamente",
    "El sistema no puede consumir mas del 80% de los recursos computacionales del entorno",
]


class CognitiveGovernance:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.mode: SystemMode = SystemMode.NORMAL
        self.mode_history: list[dict] = []
        self._cycle_metrics: list[dict] = []
        self._performance_history: list[PerformanceSnapshot] = []
        self._modification_history: list[Modification] = []
        self._circuit_breaker_history: list[dict] = []
        self._emergency_log: list[dict] = []

        self._governance_parameters: dict[str, float] = {
            "hypothesis_threshold": 0.3,
            "min_confidence_for_execution": 0.6,
            "audit_depth": 1.0,
            "learning_rate": 0.1,
            "exploration_rate": 0.2,
            "max_hypotheses_per_cycle": 4.0,
            "cognitive_budget_multiplier": 1.0,
            "degradation_break_threshold": 0.15,
            "modification_rate_limit": 5,
            "max_cpu_utilization": 0.8,
        }
        self._adaptation_history: list[dict] = []

        bus.subscribe(EventType.CYCLE_COMPLETE, self._on_cycle_complete)
        bus.subscribe(EventType.BUDGET_EXCEEDED, self._on_budget_event)
        bus.subscribe_many(
            [EventType.HYPOTHESIS_FALSIFIED, EventType.HYPOTHESIS_CONFIRMED],
            self._on_audit_result,
        )
        bus.subscribe(EventType.PARAMETER_ADJUSTED, self._on_adjustment)

    def _on_cycle_complete(self, event: Event) -> None:
        data = event.data
        self._cycle_metrics.append(data)

        if len(self._cycle_metrics) >= 3:
            self._check_circuit_breakers()
            self._review()

    def _check_circuit_breakers(self) -> None:
        recent = self._cycle_metrics[-3:]
        metrics_data = [c.get("metrics", {}) for c in recent if "metrics" in c]

        falsified_count = sum(
            1 for c in recent if c.get("outcome") == "falsified"
        )
        success_count = sum(
            1 for c in recent if c.get("outcome") == "success"
        )
        total_outcomes = falsified_count + success_count
        degradation_rate = falsified_count / max(total_outcomes, 1) if total_outcomes > 0 else 0

        if degradation_rate > 0.50:
            self._emergency_shutdown(
                reason=f"Degradation rate {degradation_rate:.0%} exceeds 50%",
                severity="critical",
            )
        elif degradation_rate > 0.30:
            self._trip_breaker(
                type="degradation",
                severity="critical",
                message=f"Falsification rate {degradation_rate:.0%} > 30%, initiating rollback",
            )
            self._initiate_rollback()
        elif degradation_rate > self._governance_parameters["degradation_break_threshold"]:
            self._trip_breaker(
                type="degradation",
                severity="warning",
                message=f"Falsification rate {degradation_rate:.0%} > threshold",
            )

        mod_count = len(self._modification_history)
        if mod_count > self._governance_parameters.get("modification_rate_limit", 5):
            recent_mods = self._modification_history[-mod_count:]
            if len(set(m.parameter for m in recent_mods)) <= 2:
                self._trip_breaker(
                    type="modification_loop",
                    severity="warning",
                    message=f"Possible modification loop detected: {mod_count} recent mods",
                )

    def _trip_breaker(self, type: str, severity: str, message: str) -> None:
        entry = {
            "type": type,
            "severity": severity,
            "message": message,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        self._circuit_breaker_history.append(entry)

        if severity == "warning":
            if self.mode == SystemMode.NORMAL:
                self._set_mode(SystemMode.CONSERVATIVE, f"Circuit breaker: {message}")
        elif severity == "critical":
            self._set_mode(SystemMode.QUARANTINE, f"Circuit breaker: {message}")

        self.bus.publish(Event(
            type=EventType.GOVERNANCE_REVIEW,
            source="governance.circuit_breaker",
            data=entry,
        ))

    def _set_mode(self, new_mode: SystemMode, reason: str) -> None:
        old_mode = self.mode
        self.mode = new_mode
        self.mode_history.append({
            "from": old_mode.value,
            "to": new_mode.value,
            "reason": reason,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
        self.bus.publish(Event(
            type=EventType.GOVERNANCE_REVIEW,
            source="governance.mode_change",
            data={"from": old_mode.value, "to": new_mode.value, "reason": reason},
            priority=EventPriority.CRITICAL,
        ))

    def _initiate_rollback(self) -> None:
        self._set_mode(SystemMode.RECOVERY, "Initiating rollback due to degradation")
        self.bus.publish(Event(
            type=EventType.ROLLBACK_EXECUTED,
            source="governance",
            data={"reason": "Degradation threshold exceeded"},
            priority=EventPriority.CRITICAL,
        ))

    def _emergency_shutdown(self, reason: str, severity: str) -> None:
        self._set_mode(SystemMode.SHUTDOWN, reason)
        self._emergency_log.append({
            "reason": reason,
            "severity": severity,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "mode_history": list(self.mode_history),
        })
        self.bus.publish(Event(
            type=EventType.CYCLE_COMPLETE,
            source="governance.emergency",
            data={"reason": reason, "severity": severity, "emergency": True},
            priority=EventPriority.CRITICAL,
        ))

    def _on_budget_event(self, event: Event) -> None:
        if self._governance_parameters["cognitive_budget_multiplier"] < 2.0:
            self._adjust_parameter(
                "cognitive_budget_multiplier",
                self._governance_parameters["cognitive_budget_multiplier"] + 0.2,
                reason="Budget exceeded: increasing allocation",
            )

    def _on_audit_result(self, event: Event) -> None:
        falsified = event.type == EventType.HYPOTHESIS_FALSIFIED

        if falsified and self._governance_parameters["audit_depth"] < 2.0:
            self._adjust_parameter(
                "audit_depth",
                self._governance_parameters["audit_depth"] + 0.1,
                reason="Hypothesis falsified: deepening audit",
            )

        if not falsified and self._governance_parameters["audit_depth"] > 0.5:
            self._adjust_parameter(
                "audit_depth",
                self._governance_parameters["audit_depth"] - 0.05,
                reason="Hypothesis confirmed: audit depth may be excessive",
            )

    def _on_adjustment(self, event: Event) -> None:
        data = event.data
        param = data.get("parameter")
        if param in self._governance_parameters:
            self._governance_parameters[param] = data.get("new_value", self._governance_parameters[param])

    def _review(self) -> None:
        recent = self._cycle_metrics[-3:]
        falsification_rate = sum(
            1 for c in recent if c.get("outcome") == "falsified"
        ) / max(len(recent), 1)
        success_rate = sum(
            1 for c in recent if c.get("outcome") == "success"
        ) / max(len(recent), 1)

        obs = []

        if falsification_rate > 0.7:
            obs.append(f"High falsification rate ({falsification_rate:.0%}): raising threshold")
            self._adjust_parameter(
                "hypothesis_threshold",
                self._governance_parameters["hypothesis_threshold"] + 0.05,
                reason="Raising threshold due to high falsification rate",
            )

        if success_rate < 0.2 and len(recent) >= 3:
            obs.append(f"Low success rate ({success_rate:.0%}): reducing exploration")
            self._adjust_parameter(
                "exploration_rate",
                self._governance_parameters["exploration_rate"] * 0.9,
                reason="Reducing exploration due to low success rate",
            )

        if self.mode != SystemMode.NORMAL:
            obs.append(f"System in {self.mode.value} mode")

        for check in self._circuit_breaker_history[-3:]:
            obs.append(f"Circuit breaker: {check['type']} ({check['severity']})")

        self.bus.publish(Event(
            type=EventType.GOVERNANCE_REVIEW,
            source="cognitive_governance",
            data={
                "observations": obs,
                "parameters": dict(self._governance_parameters),
                "mode": self.mode.value,
                "falsification_rate": round(falsification_rate, 2),
                "success_rate": round(success_rate, 2),
            },
        ))

    def validate_modification(self, modification: Modification) -> dict:
        if modification.level == 1:
            return {"approved": True, "reason": "Level 1: auto-approved"}

        if modification.level >= 3:
            if self.mode != SystemMode.NORMAL:
                return {"approved": False, "reason": f"System in {self.mode.value} mode, changes blocked"}

            recent = self._modification_history[-5:]
            similar = [m for m in recent if m.parameter == modification.parameter]
            if len(similar) >= 2:
                return {"approved": False, "reason": "Too many recent changes to same parameter"}

        if modification.level == 2:
            return {"approved": True, "reason": "Level 2: approved with monitoring"}

        return {"approved": True, "reason": "Modification validated"}

    def _adjust_parameter(self, name: str, new_value: float, reason: str = "") -> None:
        old = self._governance_parameters.get(name)
        self._governance_parameters[name] = new_value

        entry = {
            "parameter": name,
            "old_value": old,
            "new_value": new_value,
            "reason": reason,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        self._adaptation_history.append(entry)

        self.bus.publish(Event(
            type=EventType.PARAMETER_ADJUSTED,
            source="cognitive_governance",
            data=entry,
        ))

    def get_parameter(self, name: str) -> float:
        return self._governance_parameters.get(name, 0.0)

    def summary(self) -> dict:
        return {
            "mode": self.mode.value,
            "parameters": dict(self._governance_parameters),
            "adaptations": self._adaptation_history[-10:],
            "circuit_breakers": self._circuit_breaker_history[-5:],
            "cycles_reviewed": len(self._cycle_metrics),
            "modifications": len(self._modification_history),
        }
