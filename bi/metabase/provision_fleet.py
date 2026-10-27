"""Create a fresh reviewable dashboard in an existing Metabase collection.

Uses METABASE_SESSION_TOKEN or METABASE_API_KEY; never prints credentials.
Does not change existing dashboards. Re-running deliberately creates a new copy.
"""
import argparse
import os

import requests


BASE = "SELECT * FROM passporttwin_bi.fleet_analytics WHERE 1=1 [[AND family = {{family}}]] [[AND location = {{location}}]]"


def cards():
    return [
        ("Instrumentos activos", "scalar", "SELECT COUNT(*) AS instruments FROM fleet"),
        ("Calibraciones vencidas", "scalar", "SELECT COUNT(*) AS overdue FROM fleet WHERE days_to_due < 0"),
        ("Vencen en 30 días", "scalar", "SELECT COUNT(*) AS due_soon FROM fleet WHERE days_to_due BETWEEN 0 AND 30"),
        ("Documentos vinculados por revisar", "scalar", "SELECT COALESCE(SUM(documents_to_review),0) AS reviews FROM fleet"),
        ("Semáforo de flota", "bar", "SELECT traffic_light, COUNT(*) AS instruments FROM fleet GROUP BY traffic_light ORDER BY MIN(priority_rank)"),
        ("Prioridad de intervención", "table", "SELECT serial_number, family, location, traffic_light, primary_reason, days_to_due, observed_error_ratio, documents_to_review, criticality FROM fleet ORDER BY priority_rank, CASE UPPER(criticality) WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, days_to_due NULLS LAST, instrument_id LIMIT 50"),
        ("Próximos vencimientos", "table", "SELECT serial_number, family, location, next_due_date, days_to_due FROM fleet WHERE days_to_due BETWEEN 0 AND 90 ORDER BY days_to_due, instrument_id"),
        ("Estado de snapshots analíticos", "table", "SELECT analytics_status, COUNT(*) AS instruments FROM fleet GROUP BY analytics_status ORDER BY analytics_status"),
        ("Health Score · por versión y pesos", "table", "SELECT score_method_version, score_weights::jsonb::text AS weights, COUNT(current_health_score) AS instruments_with_score, AVG(current_health_score) AS mean_health_score FROM fleet WHERE current_health_score IS NOT NULL GROUP BY score_method_version, score_weights::jsonb::text ORDER BY score_method_version, score_weights::jsonb::text"),
        ("Riesgo experimental · snapshots vigentes", "table", "SELECT serial_number, family, location, analytics_status, analytics_as_of, analytics_computed_at, score_status, score_reason, current_health_score, risk_status, risk_reason, risk_uncertainty_90, current_probability_30, current_probability_60, current_probability_90, risk_method_version FROM fleet ORDER BY current_probability_90 DESC NULLS LAST, current_health_score ASC NULLS LAST, instrument_id LIMIT 50"),
    ]


def provision(url, database_id, collection_id, session):
    def post(path, payload):
        response = session.post(url.rstrip('/') + '/api/' + path, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    dashboard = post("dashboard", {
        "name": "PassportTwin · Flota operativa",
        "description": "Semáforo basado en datos observados; no equivale a probabilidad predictiva ni Health Score.",
        "collection_id": collection_id,
        "parameters": [{"id": key, "name": label, "slug": key, "type": "string/="}
                       for key, label in (("family", "Familia"), ("location", "Ubicación"))],
    })
    dashcards = []
    for index, (name, display, sql) in enumerate(cards()):
        card = post("card", {
            "name": name, "display": display, "collection_id": collection_id,
            "visualization_settings": {},
            "dataset_query": {"database": database_id, "type": "native", "native": {
                "query": "WITH fleet AS (" + BASE + ") " + sql,
                "template-tags": {key: {"id": key, "name": key, "display-name": key,
                                         "type": "text", "required": False}
                                  for key in ("family", "location")},
            }},
        })
        if index < 4:
            row, col, width, height = 0, index * 6, 6, 3
        else:
            row, col, width, height = 3 + (index - 4) * 6, 0, 24, 6
        dashcards.append({
            "id": -(index + 1), "card_id": card["id"], "row": row, "col": col,
            "size_x": width, "size_y": height,
            "parameter_mappings": [{"parameter_id": key, "card_id": card["id"],
                                    "target": ["variable", ["template-tag", key]]}
                                   for key in ("family", "location")],
        })
    response = session.put(url.rstrip('/') + f'/api/dashboard/{dashboard["id"]}',
                           json={"dashcards": dashcards}, timeout=60)
    response.raise_for_status()
    return url.rstrip('/') + f'/dashboard/{dashboard["id"]}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-id', type=int, required=True)
    parser.add_argument('--collection-id', type=int, required=True)
    args = parser.parse_args()
    url = os.environ['METABASE_URL']
    session = requests.Session()
    if os.getenv('METABASE_API_KEY'):
        session.headers['x-api-key'] = os.environ['METABASE_API_KEY']
    else:
        session.headers['X-Metabase-Session'] = os.environ['METABASE_SESSION_TOKEN']
    print(provision(url, args.database_id, args.collection_id, session))


if __name__ == '__main__':
    main()
