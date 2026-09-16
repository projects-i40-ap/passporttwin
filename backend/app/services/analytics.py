from datetime import date
from typing import List, Dict, Any
from app.models.calibration import CalibrationEvent
from app.models.instrument import InstrumentUnit

class DriftAnalyticsService:
    @staticmethod
    def calculate_drift_and_risk(
        instrument: InstrumentUnit, 
        calibrations: List[CalibrationEvent]
    ) -> Dict[str, Any]:
        """Calcula baselines B0, B1, proyecciones de riesgo a 30/60/90 días y Health Score."""
        if not calibrations:
            return {
                "instrument_id": instrument.id,
                "serial_number": instrument.serial_number,
                "status": "NO_CALIBRATION_DATA",
                "health_score": 50.0
            }

        # Ordenar eventos cronológicamente
        sorted_cals = sorted(calibrations, key=lambda c: c.calibration_date)
        last_cal = sorted_cals[-1]
        last_error = float(last_cal.error_value)
        tolerance = float(last_cal.tolerance) if last_cal.tolerance else 0.10

        # 1. Baseline B0: Persistencia
        b0_prediction = last_error

        # 2. Baseline B1: Tendencia Lineal por activo
        drift_rate_per_day = 0.0
        if len(sorted_cals) >= 2:
            prev_cal = sorted_cals[-2]
            delta_days = (last_cal.calibration_date - prev_cal.calibration_date).days
            if delta_days > 0:
                delta_error = last_error - float(prev_cal.error_value)
                drift_rate_per_day = delta_error / delta_days

        # Proyecciones a horizontes 30, 60 y 90 días
        horizons = [30, 60, 90]
        projections_b1 = {}
        risk_b1 = {}

        for h in horizons:
            proj_error = last_error + (drift_rate_per_day * h)
            projections_b1[f"{h}_days"] = round(proj_error, 4)
            # Riesgo normalizado frente a tolerancia
            risk_ratio = min(1.0, abs(proj_error) / tolerance)
            risk_b1[f"{h}_days"] = round(risk_ratio, 2)

        # 3. Health Score Explicable (0..100)
        out_of_tol_penalty = 1.0 if instrument.lifecycle_state == "out_of_tolerance" else 0.0
        current_error_ratio = min(1.0, abs(last_error) / tolerance)
        max_horizon_risk = risk_b1["90_days"]

        health_deduction = (
            0.40 * max_horizon_risk +
            0.35 * current_error_ratio +
            0.25 * out_of_tol_penalty
        )
        health_score = max(0.0, min(100.0, round((1.0 - health_deduction) * 100, 1)))

        return {
            "instrument_id": instrument.id,
            "serial_number": instrument.serial_number,
            "last_calibration_date": last_cal.calibration_date,
            "last_observed_error": last_error,
            "tolerance": tolerance,
            "drift_rate_per_day": round(drift_rate_per_day, 6),
            "baseline_b0_persistence": round(b0_prediction, 4),
            "baseline_b1_projections": projections_b1,
            "risk_out_of_tolerance": risk_b1,
            "health_score": health_score,
            "lifecycle_state": instrument.lifecycle_state
        }