import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import "./passport.css";

const text = (value) => value ?? "Sin datos";
const number = (value) => value == null ? "No estimable" : Number(value).toLocaleString("es-ES", { maximumFractionDigits: 3 });
const probability = (value) => value == null ? "No estimable" :
  value > 0 && value * 100 < 0.001 ? "< 0,001 %" : `${number(value * 100)} %`;
const reasons = {
  INSUFFICIENT_POST_MAINTENANCE_HISTORY: "faltan calibraciones posteriores al último mantenimiento",
  INSUFFICIENT_HISTORY: "faltan calibraciones para estimar la incertidumbre",
  DUPLICATE_CALIBRATION_DATES: "hay calibraciones con fechas duplicadas",
  INVALID_CALIBRATION_VALUES: "hay errores o tolerancias no válidos",
  TOLERANCE_CHANGED: "la tolerancia ha cambiado y requiere revisión",
};

export default function Passport({ apiBaseUrl }) {
  const { publicId } = useParams();
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    const controller = new AbortController();
    const base = apiBaseUrl.replace(/\/$/, "");
    async function get(path) {
      const response = await fetch(`${base}/api/v1/instruments/${path}`, { signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 404 ? "No se ha encontrado este instrumento." : "No se han podido cargar los datos.");
      return response.json();
    }
    async function load() {
      setState({ loading: true });
      try {
        const instrument = await get(`by-public-id/${encodeURIComponent(publicId)}`);
        const responses = await Promise.allSettled([
          get(`${instrument.id}/calibrations`), get(`${instrument.id}/health-score`),
          get(`${instrument.id}/tolerance-risk`),
        ]);
        if (!controller.signal.aborted) setState({ instrument,
          calibrations: responses[0].status === "fulfilled" ? responses[0].value : null,
          score: responses[1].status === "fulfilled" ? responses[1].value : null,
          risk: responses[2].status === "fulfilled" ? responses[2].value : null,
        });
      } catch (error) {
        if (!controller.signal.aborted) setState({ error: error.message });
      }
    }
    load();
    return () => controller.abort();
  }, [publicId, apiBaseUrl]);

  if (state.loading) return <main className="passport"><p role="status">Cargando pasaporte…</p></main>;
  if (state.error) return <main className="passport"><h1>Pasaporte digital</h1><p role="alert">{state.error}</p><Link to="/">Volver a PassportTwin</Link></main>;
  const { instrument, calibrations, score, risk } = state;
  return <main className="passport">
    <header><Link to="/">PassportTwin</Link><p>Pasaporte digital de instrumento</p>
      <h1>{instrument.serial_number}</h1><p>{instrument.manufacturer} · {instrument.model}</p>
      <small>Identidad estable: {instrument.public_id}</small>
    </header>
    <section aria-labelledby="identity"><h2 id="identity">Identidad y estado registrado</h2>
      <dl className="passport-grid">{[
        ["Ubicación", instrument.location], ["Criticidad", instrument.criticality],
        ["Estado operativo", instrument.lifecycle_state], ["Sincronización AAS", instrument.aas_sync_status],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{text(value)}</dd></div>)}</dl>
    </section>
    <section aria-labelledby="score"><h2 id="score">Health Score</h2>
      {!score ? <p role="status">Indicador no disponible. El resto del pasaporte sigue accesible.</p> : <>
        <p className="passport-score">{score.health_score == null ? "No calculado" : <>{number(score.health_score)} <small>/ 100</small></>}</p>
        {score.health_score == null && <p>Faltan componentes fiables para calcular el indicador; no equivale a salud media.</p>}
        {score.health_score_details?.fallback ? <p>Sin calibraciones: valor provisional, no calculado.</p> : <>
          <p>Indicador heurístico. Los pesos y la interpretación están pendientes de validación experimental.</p>
          <ul>{Object.entries(score.health_score_details?.components || {}).map(([name, component]) =>
            <li key={name}>{({risk_90_days: "Proyección histórica a 90 días", calibration_status: "Estado de calibración", predicted_risk: "Riesgo previsto", recent_incidents: "Incidencias recientes", data_quality: "Calidad de datos", current_error: "Error actual / tolerancia", out_of_tolerance: "Estado fuera de tolerancia"})[name] || name}: {component.penalty_points == null ? "No disponible" : `−${number(component.penalty_points)} puntos`} (peso {number(component.weight)})</li>)}</ul>
        </>}
      </>}
    </section>
    <section aria-labelledby="risk"><h2 id="risk">Riesgo experimental de salida de tolerancia</h2>
      <p>Estimación en cada fecha objetivo, no de cualquier cruce durante el intervalo. Este modelo aporta el componente de riesgo del Health Score de ciclo de vida.</p>
      {!risk ? <p role="status">Estimación no disponible.</p> : risk.status !== "ESTIMATED" ?
        <p>No estimable: {reasons[risk.reason] || "el historial requiere revisión"}. No equivale a riesgo cero.</p> : <>
          <p>Referencia: {risk.as_of} · {risk.calibrations_used} calibraciones · Probabilidades sin calibración experimental.</p>
          <div className="passport-grid">{Object.entries(risk.horizons).map(([key, value]) => <article key={key} className="passport-horizon">
            <h3>{key.split("_")[0]} días</h3><p>{value.target_date}</p>
            <strong>{probability(value.probability_out_of_tolerance)}</strong>
            <p>Error previsto: {number(value.predicted_error)}</p>
            {value.probability_out_of_tolerance == null && <small>Sin dispersión residual suficiente para asignar probabilidad.</small>}
          </article>)}</div>
        </>}
    </section>
    <section aria-labelledby="calibrations"><h2 id="calibrations">Historial de calibración</h2>
      {calibrations === null ? <p>No se ha podido cargar el historial.</p> : !calibrations.length ? <p>No hay calibraciones registradas.</p> :
        <div className="passport-table"><table><thead><tr><th>Fecha</th><th>Próximo vencimiento</th><th>Error</th><th>Tolerancia</th><th>Resultado</th></tr></thead>
          <tbody>{calibrations.map((item) => <tr key={item.id}><td>{item.calibration_date}</td><td>{text(item.next_due_date)}</td><td>{number(item.error_value)}</td><td>{number(item.tolerance)}</td><td>{item.result}</td></tr>)}</tbody>
        </table></div>}
    </section>
  </main>;
}
