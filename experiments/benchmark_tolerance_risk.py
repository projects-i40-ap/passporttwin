"""Deterministic synthetic smoke benchmark, not final research validation."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.services.tolerance_risk import estimate_tolerance_risk
from generators.generate_synthetic_drift_dataset import SEED, generate_dataset


def run():
    rows = generate_dataset(instruments_per_family=20, calibrations_per_instrument=19, interval_days=30)
    groups = defaultdict(list)
    for row in rows:
        groups[row["instrument_id"]].append(row)
    metrics = {h: {"brier": [], "b0_brier": [], "positives": 0} for h in (30, 60, 90)}
    for series in groups.values():
        # Train 16 points, keep the next 3 entirely outside model fitting.
        train = [SimpleNamespace(calibration_date=date.fromisoformat(r["calibration_date"]),
                                 error_value=r["error_value"], tolerance=r["tolerance"]) for r in series[:16]]
        forecast = estimate_tolerance_risk(train, train[-1].calibration_date)
        baseline = float(abs(train[-1].error_value) > train[-1].tolerance)
        for h, observed in zip((30, 60, 90), series[16:]):
            p = forecast["horizons"][f"{h}_days"]["probability_out_of_tolerance"]
            truth = int(abs(observed["error_value"]) > observed["tolerance"])
            assert forecast["horizons"][f"{h}_days"]["target_date"] == observed["calibration_date"]
            if p is not None:
                metrics[h]["brier"].append((p - truth) ** 2)
                metrics[h]["b0_brier"].append((baseline - truth) ** 2)
                metrics[h]["positives"] += truth
    return {
        "method_version": "ols_gaussian_predictive_v1", "seed": SEED,
        "dataset_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "instruments": len(groups), "training_points_per_instrument": 16,
        "validation_status": "SYNTHETIC_SMOKE_ONLY",
        "metrics": {str(h): {"n": len(v["brier"]), "positives": v["positives"],
                              "brier": sum(v["brier"]) / len(v["brier"]) if v["brier"] else None,
                              "b0_brier": sum(v["b0_brier"]) / len(v["b0_brier"]) if v["b0_brier"] else None}
                    for h, v in metrics.items()},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run(), indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(report)
    print(report)
