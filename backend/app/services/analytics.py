from typing import Any, Dict, List, Optional

from app.models.calibration import CalibrationEvent
from app.models.instrument import InstrumentUnit


class DriftAnalyticsService:
    @staticmethod
    def _fit_linear_regression(
        calibrations: List[CalibrationEvent],
    ) -> Dict[str, float]:
        """
        Ajusta una regresión lineal simple por mínimos cuadrados:

            error = intercept + slope * elapsed_days

        Requiere al menos dos calibraciones con fechas distintas.
        """

        sorted_cals = sorted(
            calibrations,
            key=lambda c: c.calibration_date,
        )

        if len(sorted_cals) < 2:
            return {
                "intercept": float(sorted_cals[0].error_value)
                if sorted_cals
                else 0.0,
                "slope_per_day": 0.0,
            }

        reference_date = sorted_cals[0].calibration_date

        x_values = [
            float(
                (calibration.calibration_date - reference_date).days
            )
            for calibration in sorted_cals
        ]

        y_values = [
            float(calibration.error_value)
            for calibration in sorted_cals
        ]

        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)

        numerator = sum(
            (x - x_mean) * (y - y_mean)
            for x, y in zip(x_values, y_values)
        )

        denominator = sum(
            (x - x_mean) ** 2
            for x in x_values
        )

        if denominator == 0:
            return {
                "intercept": y_mean,
                "slope_per_day": 0.0,
            }

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        return {
            "intercept": intercept,
            "slope_per_day": slope,
        }

    @staticmethod
    def _calculate_family_drift_rate(
        family_calibrations: List[CalibrationEvent],
    ) -> float:
        """
        Calcula B1 como pendiente media de deriva de la familia.

        Se agrupan las calibraciones por instrumento y, para cada activo
        con al menos dos calibraciones, se calcula:

            (último error - primer error) / días transcurridos

        B1 es la media de esas pendientes individuales.
        """

        calibrations_by_instrument: Dict[
            int,
            List[CalibrationEvent],
        ] = {}

        for calibration in family_calibrations:
            calibrations_by_instrument.setdefault(
                calibration.instrument_unit_id,
                [],
            ).append(calibration)

        instrument_slopes: List[float] = []

        for calibrations in calibrations_by_instrument.values():
            sorted_cals = sorted(
                calibrations,
                key=lambda c: c.calibration_date,
            )

            if len(sorted_cals) < 2:
                continue

            first_cal = sorted_cals[0]
            last_cal = sorted_cals[-1]

            delta_days = (
                last_cal.calibration_date
                - first_cal.calibration_date
            ).days

            if delta_days <= 0:
                continue

            delta_error = (
                float(last_cal.error_value)
                - float(first_cal.error_value)
            )

            instrument_slopes.append(
                delta_error / delta_days
            )

        if not instrument_slopes:
            return 0.0

        return (
            sum(instrument_slopes)
            / len(instrument_slopes)
        )

    @staticmethod
    def calculate_drift_and_risk(
        instrument: InstrumentUnit,
        calibrations: List[CalibrationEvent],
        family_calibrations: Optional[
            List[CalibrationEvent]
        ] = None,
    ) -> Dict[str, Any]:
        """
        Calcula B0, B1, M1 y conserva las salidas existentes
        de riesgo 30/60/90 y Health Score.

        B0:
            Persistencia del último error observado.

        B1:
            Tendencia media histórica de instrumentos de la misma familia.

        M1:
            Regresión lineal utilizando todo el historial disponible
            del activo.

        Nota:
            El riesgo y Health Score existentes se mantienen por
            compatibilidad y todavía utilizan la tendencia histórica
            de dos puntos que empleaba el servicio original.
        """

        if not calibrations:
            return {
                "instrument_id": instrument.id,
                "serial_number": instrument.serial_number,
                "status": "NO_CALIBRATION_DATA",
                "health_score": 50.0,
            }

        sorted_cals = sorted(
            calibrations,
            key=lambda c: c.calibration_date,
        )

        last_cal = sorted_cals[-1]
        last_error = float(last_cal.error_value)

        tolerance = (
            float(last_cal.tolerance)
            if last_cal.tolerance
            else 0.10
        )

        horizons = [30, 60, 90]

        # ---------------------------------------------------------
        # B0 — Persistencia
        # ---------------------------------------------------------
        b0_predictions = {
            f"{h}_days": round(last_error, 4)
            for h in horizons
        }

        # ---------------------------------------------------------
        # B1 — Baseline de familia
        # ---------------------------------------------------------
        family_history = (
            family_calibrations
            if family_calibrations is not None
            else []
        )

        b1_family_drift_rate = (
            DriftAnalyticsService._calculate_family_drift_rate(
                family_history
            )
        )

        b1_predictions = {
            f"{h}_days": round(
                last_error
                + b1_family_drift_rate * h,
                4,
            )
            for h in horizons
        }

        # ---------------------------------------------------------
        # M1 — Regresión lineal por activo
        # ---------------------------------------------------------
        m1_model = (
            DriftAnalyticsService._fit_linear_regression(
                sorted_cals
            )
        )

        m1_drift_rate = m1_model["slope_per_day"]

        first_calibration_date = (
            sorted_cals[0].calibration_date
        )

        last_elapsed_days = float(
            (
                last_cal.calibration_date
                - first_calibration_date
            ).days
        )

        m1_predictions = {}

        for horizon in horizons:
            future_elapsed_days = (
                last_elapsed_days
                + horizon
            )

            predicted_error = (
                m1_model["intercept"]
                + m1_drift_rate
                * future_elapsed_days
            )

            m1_predictions[
                f"{horizon}_days"
            ] = round(
                predicted_error,
                4,
            )

        # ---------------------------------------------------------
        # Compatibilidad con lógica previa de riesgo / Health Score
        # ---------------------------------------------------------
        legacy_drift_rate_per_day = 0.0

        if len(sorted_cals) >= 2:
            previous_cal = sorted_cals[-2]

            delta_days = (
                last_cal.calibration_date
                - previous_cal.calibration_date
            ).days

            if delta_days > 0:
                delta_error = (
                    last_error
                    - float(previous_cal.error_value)
                )

                legacy_drift_rate_per_day = (
                    delta_error
                    / delta_days
                )

        legacy_projections = {}
        risk_b1 = {}

        for horizon in horizons:
            projected_error = (
                last_error
                + legacy_drift_rate_per_day
                * horizon
            )

            legacy_projections[
                f"{horizon}_days"
            ] = round(
                projected_error,
                4,
            )

            risk_ratio = min(
                1.0,
                abs(projected_error)
                / tolerance,
            )

            risk_b1[
                f"{horizon}_days"
            ] = round(
                risk_ratio,
                2,
            )

        out_of_tol_penalty = (
            1.0
            if instrument.lifecycle_state
            == "out_of_tolerance"
            else 0.0
        )

        current_error_ratio = min(
            1.0,
            abs(last_error)
            / tolerance,
        )

        max_horizon_risk = risk_b1[
            "90_days"
        ]

        health_deduction = (
            0.40 * max_horizon_risk
            + 0.35 * current_error_ratio
            + 0.25 * out_of_tol_penalty
        )

        health_score = max(
            0.0,
            min(
                100.0,
                round(
                    (
                        1.0
                        - health_deduction
                    )
                    * 100,
                    1,
                ),
            ),
        )

        return {
            "instrument_id": instrument.id,
            "serial_number": instrument.serial_number,
            "last_calibration_date": (
                last_cal.calibration_date
            ),
            "last_observed_error": last_error,
            "tolerance": tolerance,

            # Salidas explícitas B0 / B1 / M1
            "drift_models": {
                "B0": {
                    "name": "persistence",
                    "predictions": b0_predictions,
                },
                "B1": {
                    "name": "family_baseline",
                    "drift_rate_per_day": round(
                        b1_family_drift_rate,
                        8,
                    ),
                    "predictions": b1_predictions,
                },
                "M1": {
                    "name": "linear_regression_per_asset",
                    "drift_rate_per_day": round(
                        m1_drift_rate,
                        8,
                    ),
                    "predictions": m1_predictions,
                    "calibrations_used": len(
                        sorted_cals
                    ),
                },
            },

            # Claves existentes preservadas por compatibilidad
            "drift_rate_per_day": round(
                legacy_drift_rate_per_day,
                6,
            ),
            "baseline_b0_persistence": round(
                last_error,
                4,
            ),
            "baseline_b1_projections": (
                legacy_projections
            ),
            "risk_out_of_tolerance": risk_b1,
            "health_score": health_score,
            "lifecycle_state": (
                instrument.lifecycle_state
            ),
        }
