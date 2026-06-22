from __future__ import annotations
import math
import json
from datetime import datetime
from collections import defaultdict
from typing import Any

from .bus import MessageBus, Event, EventType, EventPriority


class CalibrationTracker:
    def __init__(self, bus: MessageBus, storage_path: str = ".saecs/calibration"):
        self.bus = bus
        self._path = storage_path
        self._predictions: list[dict] = []
        self._calibration_buckets: dict[float, list[float]] = defaultdict(list)
        self._component_calibration: dict[str, list[dict]] = defaultdict(list)
        self._load()

        bus.subscribe(EventType.HYPOTHESIS_CONFIRMED, self._on_outcome)
        bus.subscribe(EventType.HYPOTHESIS_FALSIFIED, self._on_outcome)
        bus.subscribe(EventType.EXECUTION_SUCCESS, self._on_execution_outcome)
        bus.subscribe(EventType.EXECUTION_FAILED, self._on_execution_outcome)

    def _load(self) -> None:
        import os
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    d = json.load(f)
                    self._predictions = d.get("predictions", [])
                    self._calibration_buckets = defaultdict(
                        list, {float(k): v for k, v in d.get("buckets", {}).items()}
                    )
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    def _save(self) -> None:
        import os
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({
                "predictions": self._predictions[-1000:],
                "buckets": {str(k): v for k, v in self._calibration_buckets.items()},
            }, f, indent=2, default=str)

    def record_prediction(
        self,
        predicted_confidence: float,
        component: str = "auditor",
        context: dict | None = None,
        prediction_id: str | None = None,
    ) -> str:
        pid = prediction_id or f"pred_{len(self._predictions)}"
        self._predictions.append({
            "id": pid,
            "component": component,
            "predicted": predicted_confidence,
            "actual": None,
            "error": None,
            "timestamp": datetime.now().isoformat(),
            "context": context or {},
        })
        bucket = round(predicted_confidence * 10) / 10
        self._calibration_buckets[bucket]
        return pid

    def record_outcome(
        self,
        prediction_id: str,
        success: bool,
    ) -> dict:
        for pred in self._predictions:
            if pred["id"] == prediction_id and pred["actual"] is None:
                pred["actual"] = 1.0 if success else 0.0
                pred["error"] = abs(pred["predicted"] - pred["actual"])
                bucket = round(pred["predicted"] * 10) / 10
                self._calibration_buckets[bucket].append(pred["actual"])
                self._component_calibration[pred["component"]].append(pred)
                self._save()
                return pred
        return {}

    def _on_outcome(self, event: Event) -> None:
        data = event.data
        confidence_before = data.get("confidence_before")
        falsified = event.type == EventType.HYPOTHESIS_FALSIFIED
        if confidence_before is not None:
            self.record_prediction(confidence_before, component="auditor")
            pid = self._predictions[-1]["id"]
            self.record_outcome(pid, success=not falsified)

    def _on_execution_outcome(self, event: Event) -> None:
        data = event.data
        confidence = data.get("confidence", 0.5)
        success = event.type == EventType.EXECUTION_SUCCESS
        self.record_prediction(confidence, component="executor")
        pid = self._predictions[-1]["id"]
        self.record_outcome(pid, success=success)

    def compute_ece(self, n_buckets: int = 10) -> float:
        if not self._predictions:
            return 0.0
        ece = 0.0
        total = 0
        for bucket in range(n_buckets):
            bin_min = bucket / n_buckets
            bin_max = (bucket + 1) / n_buckets
            bin_preds = [
                p for p in self._predictions
                if p["actual"] is not None
                and bin_min <= p["predicted"] < bin_max
            ]
            if not bin_preds:
                continue
            avg_pred = sum(p["predicted"] for p in bin_preds) / len(bin_preds)
            avg_actual = sum(p["actual"] for p in bin_preds) / len(bin_preds)
            ece += abs(avg_pred - avg_actual) * len(bin_preds)
            total += len(bin_preds)
        return ece / max(total, 1)

    def calibrate_confidence(self, raw_confidence: float, component: str = "auditor") -> float:
        ece = self.compute_ece()
        if ece > 0.1:
            comp_preds = self._component_calibration.get(component, [])
            if len(comp_preds) >= 5:
                recent = comp_preds[-20:]
                avg_error = sum(
                    abs(p["predicted"] - p["actual"])
                    for p in recent if p["actual"] is not None
                ) / max(len([p for p in recent if p["actual"] is not None]), 1)
                adjusted = raw_confidence - avg_error * 0.5
                return max(0.01, min(adjusted, 0.99))
        return raw_confidence

    def component_mse(self, component: str) -> float:
        preds = self._component_calibration.get(component, [])
        if not preds:
            return 0.0
        errors = [
            (p["predicted"] - p["actual"]) ** 2
            for p in preds if p["actual"] is not None
        ]
        return sum(errors) / max(len(errors), 1)

    def summary(self) -> dict:
        ece = self.compute_ece()
        total = len([p for p in self._predictions if p["actual"] is not None])
        return {
            "total_predictions": len(self._predictions),
            "calibrated": total,
            "ece": round(ece, 4),
            "component_mse": {
                comp: round(self.component_mse(comp), 4)
                for comp in self._component_calibration
            },
            "buckets": {
                str(k): {
                    "count": len(v),
                    "mean": sum(v) / max(len(v), 1),
                }
                for k, v in self._calibration_buckets.items()
            },
        }
