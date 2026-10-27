"""Create a fresh reviewable dashboard in an existing Metabase collection.

Uses METABASE_SESSION_TOKEN or METABASE_API_KEY; never prints credentials.
Does not change existing dashboards. Re-running deliberately creates a new copy.
"""
import argparse
import os
from urllib.parse import urlsplit

import requests


BASE = "SELECT f.*, t.unit AS measurement_unit FROM passporttwin_bi.fleet_analytics f JOIN instrument_unit i ON i.id=f.instrument_id JOIN instrument_type t ON t.id=i.instrument_type_id WHERE 1=1 [[AND f.family = {{family}}]] [[AND f.location = {{location}}]]"


def translated(column, mapping, alias):
    return 'CASE '+column+' '+''.join("WHEN '"+key+"' THEN '"+value+"' " for key,value in mapping.items())+"ELSE 'Sin clasificar' END AS "+alias


def cards(passport_base_url="http://localhost:5173"):
    parsed=urlsplit(passport_base_url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Passport URL must be an HTTP(S) origin without credentials or query')
    literal="'"+passport_base_url.rstrip('/').replace("'", "''")+"'"
    definitions = [
        ("Instrumentos activos", "scalar", "SELECT COUNT(*) AS instruments FROM fleet"),
        ("Calibraciones vencidas", "scalar", "SELECT COUNT(*) AS overdue FROM fleet WHERE days_to_due < 0"),
        ("Vencen en 30 días", "scalar", "SELECT COUNT(*) AS due_soon FROM fleet WHERE days_to_due BETWEEN 0 AND 30"),
        ("Documentos vinculados por revisar", "scalar", "SELECT COALESCE(SUM(documents_to_review),0) AS reviews FROM fleet"),
        ("Semáforo de flota", "bar", "SELECT traffic_light, COUNT(*) AS instruments FROM fleet GROUP BY traffic_light ORDER BY MIN(priority_rank)"),
        ("Prioridad de intervención", "table", "SELECT serial_number, family, location, traffic_light, primary_reason, days_to_due, observed_error_ratio, measurement_unit, documents_to_review, criticality FROM fleet ORDER BY priority_rank, CASE UPPER(criticality) WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, days_to_due NULLS LAST, instrument_id LIMIT 50"),
        ("Próximos vencimientos", "table", "SELECT serial_number, family, location, next_due_date, days_to_due FROM fleet WHERE days_to_due BETWEEN 0 AND 90 ORDER BY days_to_due, instrument_id"),
        ("Estado de snapshots analíticos", "table", "SELECT analytics_status, COUNT(*) AS instruments FROM fleet GROUP BY analytics_status ORDER BY analytics_status"),
        ("Health Score · por versión y pesos", "table", "SELECT score_method_version, score_weights::jsonb::text AS weights, COUNT(current_health_score) AS instruments_with_score, AVG(current_health_score) AS mean_health_score FROM fleet WHERE current_health_score IS NOT NULL GROUP BY score_method_version, score_weights::jsonb::text ORDER BY score_method_version, score_weights::jsonb::text"),
        ("Riesgo experimental · snapshots vigentes", "table", "SELECT serial_number, family, location, analytics_status, analytics_as_of, analytics_computed_at, score_status, score_reason, current_health_score, risk_status, risk_reason, risk_uncertainty_90, current_probability_30, current_probability_60, current_probability_90, risk_method_version, measurement_unit FROM fleet ORDER BY current_probability_90 DESC NULLS LAST, current_health_score ASC NULLS LAST, instrument_id LIMIT 50"),
    ]
    traffic=translated('traffic_light',{'red':'Rojo','yellow':'Amarillo','gray':'Gris','green':'Verde'},'estado')
    freshness=translated('analytics_status',{'CURRENT':'Vigente','MISSING':'Sin resultado guardado','STALE_DATE':'Desactualizado por fecha','STALE_INPUTS':'Desactualizado por cambios'},'estado_resultado')
    name,display,query=definitions[4];definitions[4]=(name,display,query.replace('SELECT traffic_light,','SELECT '+traffic+','))
    name,display,query=definitions[7];definitions[7]=(name,display,query.replace('SELECT analytics_status,','SELECT '+freshness+','))
    reasons=translated('primary_reason',{'LIFECYCLE_ALERT':'Alerta de estado','OUT_OF_TOLERANCE':'Fuera de tolerancia',
        'CALIBRATION_OVERDUE':'Calibración vencida','NO_CALIBRATION':'Sin calibración','INVALID_METROLOGY':'Valores por revisar',
        'MISSING_DUE_DATE':'Falta próximo vencimiento','DUE_WITHIN_30_DAYS':'Vence en 30 días','DOCUMENT_REVIEW':'Revisión documental',
        'NEAR_TOLERANCE':'Próximo a tolerancia','AAS_SYNC_ERROR':'Error de sincronización','NO_ALERT':'Sin alertas'},'motivo')
    name,display,query=definitions[5];definitions[5]=(name,display,query.replace('traffic_light, primary_reason,',traffic+', '+reasons+','))
    name,display,query=definitions[5]
    query=query.replace(', criticality FROM', ', '+translated('UPPER(criticality)',{'HIGH':'Alta','MEDIUM':'Media','LOW':'Baja','CRITICAL':'Crítica'},'criticidad')+' FROM')
    definitions[5]=(name,display,query)
    name,display,query=definitions[9]
    query=query.replace('analytics_status,',freshness+',',1)
    query=query.replace('score_status,',translated('score_status',{'CALCULATED':'Calculado','NOT_CALCULATED':'No calculado'},'estado_score')+',',1)
    query=query.replace('risk_status,',translated('risk_status',{'ESTIMATED':'Estimación experimental','NOT_ESTIMABLE':'No estimable'},'estado_riesgo')+',',1)
    definitions[9]=(name,display,query)
    for index in (5,9):
        name,display,query=definitions[index]
        query=query.replace('SELECT serial_number,', "SELECT "+literal+" || '/passport/' || public_id::text AS passport_url, serial_number,",1)
        definitions[index]=(name,display,query)
    return definitions



def provision(url, database_id, collection_id, session, passport_base_url="http://localhost:5173"):
    definitions=cards(passport_base_url)  # Validate before creating remote objects.
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
    for index, (name, display, sql) in enumerate(definitions):
        card = post("card", {
            "name": name, "display": display, "collection_id": collection_id,
            "visualization_settings": {"column_settings": {
                '["name","passport_url"]': {"view_as":"link", "link_text":"Abrir pasaporte", "column_title":"Pasaporte"},
                '["name","measurement_unit"]': {"column_title":"Unidad del instrumento"}
            }} if "passport_url" in sql else {},
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
    parser.add_argument('--passport-base-url', default=os.getenv("PASSPORT_FRONTEND_BASE_URL", "http://localhost:5173"))
    args = parser.parse_args()
    url = os.environ['METABASE_URL']
    session = requests.Session()
    if os.getenv('METABASE_API_KEY'):
        session.headers['x-api-key'] = os.environ['METABASE_API_KEY']
    else:
        session.headers['X-Metabase-Session'] = os.environ['METABASE_SESSION_TOKEN']
    print(provision(url, args.database_id, args.collection_id, session, args.passport_base_url))


if __name__ == '__main__':
    main()
