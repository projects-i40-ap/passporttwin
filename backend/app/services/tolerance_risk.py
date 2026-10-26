"""Experimental point-in-time out-of-tolerance forecasts; no Health Score coupling."""

import math
from datetime import date, timedelta
from statistics import NormalDist


def estimate_tolerance_risk(calibrations, as_of: date) -> dict:
    """Fit only observations available at as_of; forecast exceedance at each date.

    Conditional Gaussian approximation with OLS residual variance. This is not
    the probability of any crossing during the interval, nor a calibrated model.
    """
    history = sorted(
        (c for c in calibrations if c.calibration_date <= as_of),
        key=lambda c: c.calibration_date,
    )
    result = {
        "method_version": "ols_gaussian_predictive_v1",
        "validation_status": "EXPERIMENTAL_UNCALIBRATED",
        "as_of": as_of.isoformat(),
        "calibrations_used": len(history),
        "horizons": {},
    }

    def unavailable(reason):
        result.update(status="NOT_ESTIMABLE", reason=reason)
        return result

    if len(history) < 3:
        return unavailable("INSUFFICIENT_HISTORY")

    # Same-day events cannot be silently ordered or treated as independent samples.
    if len({c.calibration_date for c in history}) != len(history):
        return unavailable("DUPLICATE_CALIBRATION_DATES")
    try:
        errors = [float(c.error_value) for c in history]
        tolerances = [float(c.tolerance) for c in history]
    except (TypeError, ValueError, OverflowError):
        return unavailable("INVALID_CALIBRATION_VALUES")
    if not all(math.isfinite(e) for e in errors) or not all(
        math.isfinite(t) and t > 0 for t in tolerances
    ):
        return unavailable("INVALID_CALIBRATION_VALUES")
    tolerance = tolerances[-1]
    if any(not math.isclose(t, tolerance, rel_tol=1e-9) for t in tolerances):
        return unavailable("TOLERANCE_CHANGED")

    reference = history[0].calibration_date
    xs = [(c.calibration_date - reference).days for c in history]
    n = len(xs)
    x_mean, y_mean = sum(xs) / n, sum(errors) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, errors)) / sxx
    intercept = y_mean - slope * x_mean
    residual_variance = sum(
        (y - intercept - slope * x) ** 2 for x, y in zip(xs, errors)
    ) / (n - 2)
    result.update(
        status="ESTIMATED", last_calibration_date=history[-1].calibration_date.isoformat(),
        tolerance=tolerance, slope_per_day=slope,
        residual_std=math.sqrt(residual_variance),
    )
    for horizon in (30, 60, 90):
        target = as_of + timedelta(days=horizon)
        x = (target - reference).days
        predicted_error = intercept + slope * x
        # Includes observation noise and uncertainty in the fitted mean.
        std = math.sqrt(residual_variance * (1 + 1 / n + (x - x_mean) ** 2 / sxx))
        if std <= 1e-12 * max(tolerance, abs(predicted_error)):
            # Perfect synthetic lines do not establish zero uncertainty in reality.
            probability = None
            uncertainty_status = "ZERO_RESIDUAL_VARIANCE"
        else:
            normal = NormalDist(mu=predicted_error, sigma=std)
            probability = max(0.0, min(1.0, normal.cdf(-tolerance) + 1 - normal.cdf(tolerance)))
            uncertainty_status = "GAUSSIAN_APPROXIMATION"
        result["horizons"][f"{horizon}_days"] = {
            "target_date": target.isoformat(), "predicted_error": predicted_error,
            "predictive_std": std, "probability_out_of_tolerance": probability,
            "projected_out_of_tolerance": abs(predicted_error) > tolerance,
            "uncertainty_status": uncertainty_status,
        }
    return result
