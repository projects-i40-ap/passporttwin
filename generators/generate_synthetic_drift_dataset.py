import csv
import os
import random
from datetime import date, timedelta
from typing import Dict, List


SEED = 42
random.seed(SEED)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_PATH = os.path.join(
    PROJECT_ROOT,
    "ai",
    "datasets",
    "drift_synthetic.csv",
)

INSTRUMENT_FAMILIES = {
    "pressure_transmitter": {
        "prefix": "PT",
        "tolerance": 0.10,
        "base_offset_range": (-0.020, 0.020),
        "drift_rate_range": (-0.00015, 0.00035),
        "noise_std": 0.004,
    },
    "temperature_sensor": {
        "prefix": "TT",
        "tolerance": 0.50,
        "base_offset_range": (-0.080, 0.080),
        "drift_rate_range": (-0.00050, 0.00150),
        "noise_std": 0.020,
    },
    "ph_sensor": {
        "prefix": "PH",
        "tolerance": 0.20,
        "base_offset_range": (-0.040, 0.040),
        "drift_rate_range": (-0.00030, 0.00080),
        "noise_std": 0.010,
    },
}


def generate_instrument_series(
    instrument_id: int,
    serial_number: str,
    instrument_type: str,
    num_calibrations: int,
    start_date: date,
    interval_days: int,
) -> List[Dict]:
    """
    Genera una serie temporal sintética de calibraciones para un instrumento.

    Modelo generativo:
        error(t) = offset + drift_rate * elapsed_days + noise

    El drift_rate real se conserva como ground truth experimental.
    """

    config = INSTRUMENT_FAMILIES[instrument_type]

    tolerance = config["tolerance"]
    offset = random.uniform(*config["base_offset_range"])
    true_drift_rate = random.uniform(*config["drift_rate_range"])
    noise_std = config["noise_std"]

    rows = []

    for calibration_index in range(num_calibrations):
        elapsed_days = calibration_index * interval_days
        calibration_date = start_date + timedelta(days=elapsed_days)

        noise = random.gauss(0.0, noise_std)

        error_value = (
            offset
            + true_drift_rate * elapsed_days
            + noise
        )

        result = (
            "out_of_tolerance"
            if abs(error_value) > tolerance
            else "pass"
        )

        rows.append(
            {
                "instrument_id": instrument_id,
                "serial_number": serial_number,
                "instrument_type": instrument_type,
                "calibration_index": calibration_index + 1,
                "calibration_date": calibration_date.isoformat(),
                "elapsed_days": elapsed_days,
                "error_value": round(error_value, 6),
                "tolerance": tolerance,
                "result": result,
                "true_offset": round(offset, 6),
                "true_drift_rate_per_day": round(true_drift_rate, 8),
            }
        )

    return rows


def generate_dataset(
    instruments_per_family: int = 20,
    calibrations_per_instrument: int = 8,
    interval_days: int = 90,
) -> List[Dict]:
    """
    Genera un dataset reproducible con varias familias e instrumentos.

    Por defecto:
    - 3 familias
    - 20 instrumentos por familia
    - 8 calibraciones por instrumento
    - 90 días entre calibraciones

    Total por defecto: 480 observaciones.
    """

    random.seed(SEED)

    dataset = []
    instrument_id = 1

    base_start_date = date(2023, 1, 1)

    for instrument_type, config in INSTRUMENT_FAMILIES.items():
        for family_index in range(1, instruments_per_family + 1):
            serial_number = (
                f"{config['prefix']}-SYN-{family_index:03d}"
            )

            # Pequeña variación en la fecha inicial entre activos,
            # manteniendo determinismo mediante la semilla fija.
            start_offset_days = random.randint(0, 60)
            start_date = base_start_date + timedelta(
                days=start_offset_days
            )

            series = generate_instrument_series(
                instrument_id=instrument_id,
                serial_number=serial_number,
                instrument_type=instrument_type,
                num_calibrations=calibrations_per_instrument,
                start_date=start_date,
                interval_days=interval_days,
            )

            dataset.extend(series)
            instrument_id += 1

    return dataset


def save_dataset(rows: List[Dict], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = [
        "instrument_id",
        "serial_number",
        "instrument_type",
        "calibration_index",
        "calibration_date",
        "elapsed_days",
        "error_value",
        "tolerance",
        "result",
        "true_offset",
        "true_drift_rate_per_day",
    ]

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    dataset = generate_dataset()

    save_dataset(
        rows=dataset,
        output_path=OUTPUT_PATH,
    )

    instrument_count = len(
        {
            row["instrument_id"]
            for row in dataset
        }
    )

    print("============================================================")
    print("SYNTHETIC DRIFT DATASET GENERATED")
    print("============================================================")
    print(f"Random seed              : {SEED}")
    print(f"Instrument families      : {len(INSTRUMENT_FAMILIES)}")
    print(f"Total instruments        : {instrument_count}")
    print(f"Total calibration events : {len(dataset)}")
    print(f"Output                    : {OUTPUT_PATH}")
    print("============================================================")


if __name__ == "__main__":
    main()