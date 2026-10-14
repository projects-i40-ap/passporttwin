import json
import math
import os
from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(
    PROJECT_ROOT,
    "ai",
    "datasets",
    "drift_synthetic.csv",
)
OUTPUT_PATH = os.path.join(
    PROJECT_ROOT,
    "experiments",
    "results_exp04.json",
)


def mean_absolute_error(
    y_true: List[float],
    y_pred: List[float],
) -> float:
    if not y_true:
        return 0.0

    errors = [
        abs(true - pred)
        for true, pred in zip(y_true, y_pred)
    ]
    return sum(errors) / len(errors)


def root_mean_squared_error(
    y_true: List[float],
    y_pred: List[float],
) -> float:
    if not y_true:
        return 0.0

    squared_errors = [
        (true - pred) ** 2
        for true, pred in zip(y_true, y_pred)
    ]
    return math.sqrt(
        sum(squared_errors) / len(squared_errors)
    )


def fit_linear_regression(
    x_values: List[float],
    y_values: List[float],
) -> Tuple[float, float]:
    """
    Ajusta una regresión lineal simple:

        y = intercept + slope * x

    Implementada sin scikit-learn para mantener el MVP ligero
    y sin dependencias nuevas.
    """

    if len(x_values) != len(y_values):
        raise ValueError("x_values e y_values deben tener la misma longitud.")

    if len(x_values) < 2:
        raise ValueError("Se necesitan al menos 2 puntos para ajustar M1.")

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
        return y_mean, 0.0

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    return intercept, slope


def prepare_temporal_split(
    dataframe: pd.DataFrame,
    train_calibrations: int = 6,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split temporal por instrumento.

    Con 8 calibraciones por activo:
    - primeras 6 -> entrenamiento
    - últimas 2 -> test

    No se realiza shuffle para evitar leakage temporal.
    """

    train_frames = []
    test_frames = []

    for _, instrument_df in dataframe.groupby("instrument_id"):
        ordered = instrument_df.sort_values("calibration_date")

        if len(ordered) <= train_calibrations:
            raise ValueError(
                "Cada instrumento debe tener más calibraciones "
                "que las reservadas para entrenamiento."
            )

        train_frames.append(
            ordered.iloc[:train_calibrations]
        )

        test_frames.append(
            ordered.iloc[train_calibrations:]
        )

    train_df = pd.concat(
        train_frames,
        ignore_index=True,
    )

    test_df = pd.concat(
        test_frames,
        ignore_index=True,
    )

    return train_df, test_df


def calculate_family_baseline(
    train_df: pd.DataFrame,
) -> Dict[str, float]:
    """
    B1: baseline agregado por familia.

    Para cada familia se calcula el cambio medio diario observado
    entre la primera y la última calibración de entrenamiento
    de cada instrumento.

    El resultado representa una pendiente media de deriva
    de la familia.
    """

    family_slopes: Dict[str, List[float]] = defaultdict(list)

    for _, instrument_df in train_df.groupby("instrument_id"):
        ordered = instrument_df.sort_values("elapsed_days")

        first_row = ordered.iloc[0]
        last_row = ordered.iloc[-1]

        delta_days = (
            float(last_row["elapsed_days"])
            - float(first_row["elapsed_days"])
        )

        if delta_days <= 0:
            continue

        delta_error = (
            float(last_row["error_value"])
            - float(first_row["error_value"])
        )

        slope = delta_error / delta_days

        family = str(first_row["instrument_type"])
        family_slopes[family].append(slope)

    return {
        family: sum(values) / len(values)
        for family, values in family_slopes.items()
        if values
    }


def evaluate_models(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> Dict:
    family_baselines = calculate_family_baseline(train_df)

    all_true = []
    predictions_b0 = []
    predictions_b1 = []
    predictions_m1 = []

    details = []

    for instrument_id, instrument_test in test_df.groupby("instrument_id"):
        instrument_train = train_df[
            train_df["instrument_id"] == instrument_id
        ].sort_values("elapsed_days")

        instrument_test = instrument_test.sort_values("elapsed_days")

        last_train_row = instrument_train.iloc[-1]

        last_train_error = float(
            last_train_row["error_value"]
        )
        last_train_day = float(
            last_train_row["elapsed_days"]
        )

        instrument_type = str(
            last_train_row["instrument_type"]
        )

        serial_number = str(
            last_train_row["serial_number"]
        )

        # ---------------------------------------------------------
        # B0: persistencia
        # ---------------------------------------------------------
        # Predice siempre el último error conocido.
        #
        # y_hat(t+h) = error(t)
        # ---------------------------------------------------------

        # ---------------------------------------------------------
        # B1: tendencia media de familia
        # ---------------------------------------------------------
        family_slope = family_baselines.get(
            instrument_type,
            0.0,
        )

        # ---------------------------------------------------------
        # M1: regresión lineal por activo
        # ---------------------------------------------------------
        train_x = [
            float(value)
            for value in instrument_train["elapsed_days"].tolist()
        ]

        train_y = [
            float(value)
            for value in instrument_train["error_value"].tolist()
        ]

        intercept_m1, slope_m1 = fit_linear_regression(
            train_x,
            train_y,
        )

        true_slope = float(
            last_train_row["true_drift_rate_per_day"]
        )

        instrument_predictions = []

        for _, test_row in instrument_test.iterrows():
            target_day = float(
                test_row["elapsed_days"]
            )

            true_error = float(
                test_row["error_value"]
            )

            horizon_days = (
                target_day
                - last_train_day
            )

            pred_b0 = last_train_error

            pred_b1 = (
                last_train_error
                + family_slope * horizon_days
            )

            pred_m1 = (
                intercept_m1
                + slope_m1 * target_day
            )

            all_true.append(true_error)
            predictions_b0.append(pred_b0)
            predictions_b1.append(pred_b1)
            predictions_m1.append(pred_m1)

            instrument_predictions.append(
                {
                    "calibration_date": str(
                        test_row["calibration_date"]
                    ),
                    "elapsed_days": target_day,
                    "horizon_days": horizon_days,
                    "true_error": round(
                        true_error,
                        6,
                    ),
                    "prediction_b0": round(
                        pred_b0,
                        6,
                    ),
                    "prediction_b1": round(
                        pred_b1,
                        6,
                    ),
                    "prediction_m1": round(
                        pred_m1,
                        6,
                    ),
                }
            )

        details.append(
            {
                "instrument_id": int(instrument_id),
                "serial_number": serial_number,
                "instrument_type": instrument_type,
                "true_drift_rate_per_day": round(
                    true_slope,
                    8,
                ),
                "b1_family_drift_rate_per_day": round(
                    family_slope,
                    8,
                ),
                "m1_estimated_drift_rate_per_day": round(
                    slope_m1,
                    8,
                ),
                "predictions": instrument_predictions,
            }
        )

    metrics = {
        "B0_persistence": {
            "mae": round(
                mean_absolute_error(
                    all_true,
                    predictions_b0,
                ),
                6,
            ),
            "rmse": round(
                root_mean_squared_error(
                    all_true,
                    predictions_b0,
                ),
                6,
            ),
        },
        "B1_family_baseline": {
            "mae": round(
                mean_absolute_error(
                    all_true,
                    predictions_b1,
                ),
                6,
            ),
            "rmse": round(
                root_mean_squared_error(
                    all_true,
                    predictions_b1,
                ),
                6,
            ),
        },
        "M1_linear_regression": {
            "mae": round(
                mean_absolute_error(
                    all_true,
                    predictions_m1,
                ),
                6,
            ),
            "rmse": round(
                root_mean_squared_error(
                    all_true,
                    predictions_m1,
                ),
                6,
            ),
        },
    }

    return {
        "metrics": metrics,
        "family_baselines": {
            family: round(
                slope,
                8,
            )
            for family, slope in family_baselines.items()
        },
        "details": details,
    }


def determine_best_model(metrics: Dict) -> str:
    """
    Selecciona el modelo con menor RMSE global.
    """

    return min(
        metrics,
        key=lambda model_name: metrics[model_name]["rmse"],
    )


def run_experiment_04() -> None:
    print(
        "=================================================================="
    )
    print(
        "EJECUTANDO EXP-04: ESTIMACIÓN DE DERIVA B0 / B1 / M1"
    )
    print(
        "=================================================================="
    )

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"No se encontró el dataset en: {DATASET_PATH}"
        )

    dataframe = pd.read_csv(
        DATASET_PATH,
        parse_dates=["calibration_date"],
    )

    train_df, test_df = prepare_temporal_split(
        dataframe=dataframe,
        train_calibrations=6,
    )

    evaluation = evaluate_models(
        train_df=train_df,
        test_df=test_df,
    )

    metrics = evaluation["metrics"]
    best_model = determine_best_model(metrics)

    total_instruments = int(
        dataframe["instrument_id"].nunique()
    )

    print(f"Dataset            : {DATASET_PATH}")
    print(f"Instrumentos       : {total_instruments}")
    print(f"Registros totales  : {len(dataframe)}")
    print(f"Registros train    : {len(train_df)}")
    print(f"Registros test     : {len(test_df)}")
    print("Split temporal     : 6 calibraciones train / 2 test")
    print()

    print(
        "------------------------------------------------------------------"
    )
    print(
        "RESULTADOS GLOBALES"
    )
    print(
        "------------------------------------------------------------------"
    )

    for model_name, model_metrics in metrics.items():
        print(
            f"{model_name:24s} "
            f"MAE={model_metrics['mae']:.6f} "
            f"RMSE={model_metrics['rmse']:.6f}"
        )

    print(
        "------------------------------------------------------------------"
    )
    print(f"Mejor modelo por RMSE: {best_model}")
    print(
        "=================================================================="
    )

    report = {
        "experiment": "EXP-04",
        "description": (
            "Evaluación reproducible de estimación de deriva "
            "mediante B0 persistencia, B1 baseline de familia "
            "y M1 regresión lineal por activo."
        ),
        "dataset": "ai/datasets/drift_synthetic.csv",
        "dataset_type": "synthetic",
        "random_seed": 42,
        "validation_scope": (
            "Validación experimental sobre datos sintéticos controlados. "
            "No constituye validación industrial sobre datos reales."
        ),
        "split": {
            "method": "temporal_per_instrument",
            "train_calibrations_per_instrument": 6,
            "test_calibrations_per_instrument": 2,
            "shuffle": False,
        },
        "dataset_summary": {
            "total_instruments": total_instruments,
            "total_records": int(len(dataframe)),
            "train_records": int(len(train_df)),
            "test_records": int(len(test_df)),
        },
        "models": {
            "B0": (
                "Persistencia: último error observado."
            ),
            "B1": (
                "Baseline de familia: último error observado "
                "+ pendiente media histórica de la familia."
            ),
            "M1": (
                "Regresión lineal por activo utilizando todas "
                "las calibraciones disponibles en entrenamiento."
            ),
        },
        "metrics": metrics,
        "best_model_by_rmse": best_model,
        "family_baselines": evaluation["family_baselines"],
        "details": evaluation["details"],
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            report,
            output_file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"[OK] Evidencia experimental guardada en: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    run_experiment_04()