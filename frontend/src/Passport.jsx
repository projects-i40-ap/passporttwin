import React, { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import AppShell from "./AppShell";
import { demoInstrumentMedia, DemoLocationPlan } from "./DemoInstrumentMedia";
import "./passport.css";
import { statusLabel, dateTimeLabel, healthActions, riskAction } from "./presentation";

const text = (value) => value ?? "Sin datos";
const calendarDateFormat = new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeZone: "UTC" });
function calendarDate(value) {
  if (!value) return "Sin fecha disponible";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Sin fecha disponible" : calendarDateFormat.format(date);
}
const number = (value) => value == null ? "No estimable" : Number(value).toLocaleString("es-ES", { maximumFractionDigits: 3 });
const percentFormat = new Intl.NumberFormat("es-ES", {
  style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1,
});
const probability = (value) => value == null ? "No estimable" : percentFormat.format(value);
const sectionIcons = {
  summary: "M3 10 12 3l9 7M5 9v11h5v-6h4v6h5V9",
  identity: "M12 11v5m0-8h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  calibrations: "M7 3v4m10-4v4M4 9h16M4 5h16v16H4zM8 15l2 2 5-5",
  maintenance: "M14 6a4 4 0 0 0-5 5L3 17l4 4 6-6a4 4 0 0 0 5-5l-3 2-3-3z",
  documents: "M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6",
  audit: "M3 12a9 9 0 1 1 2.6 6.4M3 5v7h7m2-5v5l3 2",
  score: "M3 12h4l3-7 4 14 3-7h4",
};
const reasons = {
  INSUFFICIENT_POST_MAINTENANCE_HISTORY: "faltan calibraciones posteriores al último mantenimiento",
  INSUFFICIENT_HISTORY: "faltan calibraciones para estimar la incertidumbre",
  DUPLICATE_CALIBRATION_DATES: "hay calibraciones con fechas duplicadas",
  INVALID_CALIBRATION_VALUES: "hay errores o tolerancias no válidos",
  TOLERANCE_CHANGED: "la tolerancia ha cambiado y requiere revisión",
};

export default function Passport({ apiBaseUrl, planOnly = false }) {
  const { publicId } = useParams();
  const { hash } = useLocation();
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
        if (planOnly) {
          if (!controller.signal.aborted) setState({ instrument });
          return;
        }
        const responses = await Promise.allSettled([
          get(`${instrument.id}/calibrations`), get(`${instrument.id}/health-score`),
          get(`${instrument.id}/tolerance-risk`),
          get(`${instrument.id}/passport-context`), get(`${instrument.id}/maintenance`),
        ]);
        if (!controller.signal.aborted) setState({ instrument,
          calibrations: responses[0].status === "fulfilled" ? responses[0].value : null,
          score: responses[1].status === "fulfilled" ? responses[1].value : null,
          risk: responses[2].status === "fulfilled" ? responses[2].value : null,
          context: responses[3].status === "fulfilled" ? responses[3].value : null,
          maintenance: responses[4].status === "fulfilled" ? responses[4].value : null,
        });
      } catch (error) {
        if (!controller.signal.aborted) setState({ error: error.message });
      }
    }
    load();
    return () => controller.abort();
  }, [publicId, apiBaseUrl, planOnly]);

  useEffect(() => {
    if (!planOnly && hash === "#location-plan" && state.instrument) {
      document.getElementById("location-plan")?.focus();
    }
  }, [hash, planOnly, state.instrument]);

  if (state.loading) return <main className="passport"><p role="status">Cargando pasaporte…</p></main>;
  if (state.error) return <main className="passport"><h1>Pasaporte digital</h1><p role="alert">{state.error}</p><Link to="/">Volver a PassportTwin</Link></main>;
  const { instrument, calibrations, score, risk, context, maintenance } = state;
  const fleetAnalytics = context?.saved_analytics;
  const fleetNotice = {
    STALE_DATE: "El cálculo guardado corresponde a una fecha anterior.",
    STALE_INPUTS: "Los datos del instrumento han cambiado desde el último cálculo guardado.",
  }[fleetAnalytics?.status];
  const fleetStatus = fleetNotice ? "Pendiente de actualizar"
    : fleetAnalytics?.status === "CURRENT" ? "Al día"
    : fleetAnalytics?.status === "MISSING" ? "Sin cálculo guardado"
    : "Estado no disponible";
  const calibrationHistory = calibrations?.slice().sort((a, b) =>
    b.calibration_date.localeCompare(a.calibration_date) || b.id - a.id);
  const demoMedia = demoInstrumentMedia(instrument);
  if (planOnly) return <AppShell>
    <main className="passport passport-redesign passport-plan-page">
      <header>
        <Link to={`/passport/${encodeURIComponent(publicId)}#location-plan`}>Volver al pasaporte</Link>
        <h1>Plano de ubicación</h1>
        <p>{text(instrument.location)} · {instrument.serial_number}</p>
      </header>
      {demoMedia ? <DemoLocationPlan media={demoMedia} /> : <p>No hay un plano asociado a este instrumento.</p>}
    </main>
  </AppShell>;
  const actions = healthActions(score?.health_score_details, risk);
  const unit = context?.unit || "unidad no definida";
  const auditUrl = `/?tab=audit&entity=instrument&id=${instrument.id}&passport=${instrument.public_id}`;
  const today = new Date().toLocaleDateString("sv-SE");
  const latest = calibrations?.reduce((current, item) => item.calibration_date <= today &&
    (!current || item.calibration_date > current.calibration_date ||
      (item.calibration_date === current.calibration_date && item.id > current.id)) ? item : current, null);
  const overdue = Boolean(latest?.next_due_date && latest.next_due_date < today);
  const health = score?.health_score_details?.fallback ? null : score?.health_score;
  const healthBand = health == null ? null : health < 50 ? "Bajo" : health < 75 ? "Intermedio" : "Alto";
  const count = (items) => items == null ? null : items.length;
  const dataThrough = score?.calibration_data_through || context?.calibration_data_through;
  const sections = [
    ["summary", "Resumen", "#summary"], ["identity", "Datos técnicos", "#identity"],
    ["calibrations", "Calibraciones", "#calibrations", count(calibrations)],
    ["maintenance", "Mantenimiento", "#maintenance", count(maintenance)],
    ["documents", "Documentos", "#documents", count(context?.documents)],
    ["audit", "Historial de eventos", "#events"],
    ["score", "Salud del instrumento", "#score", health == null ? null : number(health) + " / 100"],
  ];
  return <AppShell auditHref={auditUrl}>
    <main className="passport passport-redesign" id="summary">
      <div className="passport-overview">
        <header className="passport-identity-card">
          <div className="passport-identity-band">
            {demoMedia ? <figure className="passport-photo-placeholder passport-demo-photo">
              <img src={demoMedia.photo} alt={`Imagen de referencia · ${instrument.technical_name || instrument.model}`} />
              <figcaption>Imagen sintética</figcaption>
            </figure> : <span className="passport-photo-placeholder" aria-label="Foto no disponible">Sin foto</span>}
            <div><p>Pasaporte del instrumento</p>
              <h1>{instrument.technical_name || instrument.model || "Instrumento"}</h1>
              {instrument.plant_tag && <p>Etiqueta de planta · <strong>{instrument.plant_tag}</strong></p>}
              <p>Número de serie · <strong>{instrument.serial_number}</strong></p>
            </div>
          </div>
          <dl className="passport-id-summary">
            <div><dt><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21V10l6-4v5l6-5v5l6-4v14H3Zm5-5h1m3 0h1m3 0h1" /></svg>Fabricante</dt><dd>{text(instrument.manufacturer)}</dd></div>
            <div><dt><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 10c0 5-7 10-7 10s-7-5-7-10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></svg>Ubicación</dt><dd>{text(instrument.location)}
              {demoMedia && <><br /><Link className="passport-plan-link" to={`/passport/${encodeURIComponent(publicId)}/plano`}>Abrir plano</Link></>}
            </dd></div>
            <div className="passport-operating"><dt>Estado operativo</dt><dd><span data-operational={String(instrument.lifecycle_state).toLowerCase() === "operational"}>{statusLabel(instrument.lifecycle_state)}</span></dd></div>
          </dl>
          <nav className="passport-instrument-nav" aria-label="Secciones del instrumento">
            {sections.map(([icon, label, href, badge]) => {
              const content = <><span className="passport-nav-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d={sectionIcons[icon]} />
                </svg>
              </span><span>{label}</span>{badge != null && <small>{badge}</small>}<span aria-hidden="true">›</span></>;
              return href.startsWith("#") ? <a key={href} href={href}>{content}</a> : <Link key={href} to={href}>{content}</Link>;
            })}
          </nav>
        </header>
        <div className="passport-decision">
          <div className="passport-summary-card">
            <h2>Health Score</h2>
            {health == null ? <strong>{score ? "No calculado" : "No disponible"}</strong> :
              <div className="passport-score-summary" data-band={healthBand}>
                <div className="passport-score-value">
                  <strong>{number(health)} <small>/ 100</small></strong>
                  <span className="passport-score-band">{healthBand}</span>
                </div>
                <div className="passport-score-scale" aria-hidden="true">
                  <div className="passport-score-track">
                    <span className="passport-score-marker" style={{ left: `clamp(2px, ${Math.max(0, Math.min(100, health))}%, 100% - 2px)` }} />
                  </div>
                  <div className="passport-score-ticks"><span>0</span><span>50</span><span>75</span><span>100</span></div>
                </div>
              </div>}
            <p className="passport-data-caption">{health == null ? "Último intento de cálculo" : "Cálculo en esta consulta"} · {dateTimeLabel(score?.calculated_at)}</p>
            <p className="passport-data-caption">Datos de calibración hasta: {calendarDate(dataThrough)}</p>
          </div>
          <div className="passport-summary-card">
            <h2>Riesgo estimado de salir de tolerancia</h2>
            {risk?.status === "ESTIMATED" ? <dl className="passport-risk-summary">
              {[30, 60, 90].map(days => <div key={days}><dt>{days} días</dt>
                <dd>{probability(risk.horizons?.[`${days}_days`]?.probability_out_of_tolerance)}</dd></div>)}
            </dl> : <p>{risk ? "No estimable" : "No disponible"}</p>}
            {risk?.as_of && <p className="passport-data-caption">Fecha del cálculo en este pasaporte · {calendarDate(risk.as_of)}</p>}
            <div className="passport-fleet-status">
              <p><strong>Datos del panel de flota</strong></p>
              <p className="passport-data-caption">
                <strong data-pending={Boolean(fleetNotice)}>{fleetStatus}</strong>
                {fleetAnalytics?.as_of && ` · Cálculo del ${calendarDate(fleetAnalytics.as_of)}`}
              </p>
              {fleetNotice && <p className="passport-data-caption">{fleetNotice}</p>}
            </div>
          </div>
          <div className={`passport-summary-card passport-calibration-status${overdue ? " passport-overdue" : ""}`}>
            <h2>Estado de la calibración</h2>
            <strong>{calibrations == null ? "Historial no disponible" : !latest ? "Sin historial de calibración" : overdue ? "Calibración vencida" : !latest.next_due_date ? "Sin fecha de vencimiento" : "Calibración en plazo"}</strong>
            {overdue && <p>Programa una nueva calibración y revisa el último certificado.</p>}
            <dl className="passport-calibration-dates"><div><dt>Última calibración</dt><dd>{calendarDate(latest?.calibration_date)}</dd></div>
              <div><dt>Próximo vencimiento</dt><dd>{calendarDate(latest?.next_due_date)}</dd></div></dl>
            <a className="passport-primary-action" href={calibrations != null && !latest ? "#documents" : "#calibrations"}>
              {calibrations != null && !latest ? "Ver documentación de calibración" : "Ver historial de calibraciones"}
            </a>
          </div>
        </div>
      </div>
    <section aria-labelledby="identity"><h2 id="identity">Datos técnicos</h2>
      <div className="passport-technical-grid">
        {[
          ["Identificación", [
            ["Fabricante", instrument.manufacturer], ["Modelo", instrument.model],
            ...(instrument.technical_name ? [["Nombre técnico", instrument.technical_name]] : []),
            ...(instrument.plant_tag ? [["Etiqueta de planta", instrument.plant_tag]] : []),
            ["Número de serie", instrument.serial_number], ["Identificador del pasaporte", instrument.public_id],
          ]],
          ["Medida y operación", [
            ["Familia", context?.family], ["Unidad de medida", unit],
            ["Criticidad operativa", statusLabel(instrument.criticality)],
            ["Sincronización AAS", statusLabel(instrument.aas_sync_status)],
          ]],
        ].map(([heading, fields]) => <article key={heading} className="passport-summary-card">
          <h3>{heading}</h3>
          <dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{text(value)}</dd></div>)}</dl>
        </article>)}
        <article id="location-plan" className="passport-summary-card passport-location-plan" tabIndex={-1}>
          <h3>Ubicación y plano</h3>
          <dl><div><dt>Ubicación registrada</dt><dd>{text(instrument.location)}</dd></div></dl>
          {demoMedia ? <DemoLocationPlan media={demoMedia} /> :
            <p className="passport-data-caption">No hay un plano asociado a este instrumento.</p>}
        </article>
      </div>
    </section>
    <section aria-labelledby="freshness"><h2 id="freshness">Actualización de la información</h2>
      <div className="passport-technical-grid">
        <article className="passport-summary-card"><h3>Cálculo del pasaporte</h3>
          <dl><div><dt>{health == null ? "Último intento de cálculo" : "Último cálculo en esta consulta"}</dt><dd>{dateTimeLabel(score?.calculated_at)}</dd></div>
            <div><dt>Datos de calibración hasta</dt><dd>{calendarDate(dataThrough)}</dd></div></dl>
        </article>
        <article className="passport-summary-card"><h3>Datos del panel de flota</h3>
          <p><strong>{fleetStatus}</strong></p>
          {fleetAnalytics?.computed_at && <p>Última actualización · {dateTimeLabel(fleetAnalytics.computed_at)}</p>}
          {fleetNotice && <p>{fleetNotice}</p>}
        </article>
      </div>
    </section>
    <section aria-labelledby="score"><h2 id="score">Salud del instrumento</h2>
      <article className="passport-summary-card passport-detail-card">
      <h3>Detalle del Health Score</h3>
      {!score ? <p role="status">Indicador no disponible. El resto del pasaporte sigue accesible.</p> : <>
        <p className="passport-score">{health == null ? "No calculado" : <>{number(health)} <small>/ 100</small></>}</p>
        {health == null && <p>Faltan componentes fiables para calcular el indicador.</p>}
        {score.health_score_details?.fallback ? <p>Sin calibraciones: valor provisional, no calculado.</p> : <>
          <p>Indicador heurístico. Los pesos y la interpretación están pendientes de validación experimental.</p>
          <dl className="passport-detail-list">{Object.entries(score.health_score_details?.components || {}).map(([name, component]) =>
            <div key={name}><dt>{({risk_90_days: "Proyección histórica a 90 días", calibration_status: "Estado de calibración", predicted_risk: "Riesgo previsto", recent_incidents: "Incidencias recientes", data_quality: "Calidad de datos", current_error: "Error actual / tolerancia", out_of_tolerance: "Estado fuera de tolerancia"})[name] || name}</dt>
              <dd>{component.penalty_points == null ? "No disponible" : `−${number(component.penalty_points)} puntos`} · Peso {number(component.weight)}</dd></div>)}</dl>
        </>}
      </>}
      {actions.length > 0 && <aside><h3>Qué falta revisar</h3><ul>{actions.map(action => <li key={action}>{action}</li>)}</ul><a href="#documents">Abrir documentación vinculada</a></aside>}
      <p><a href="#risk">Ver detalle del riesgo estimado</a></p>
      </article>
    </section>
    <section aria-labelledby="risk"><h2 id="risk">Riesgo experimental de salida de tolerancia</h2>
      <p>Estimación en cada fecha objetivo, no de cualquier cruce durante el intervalo. Este modelo aporta el componente de riesgo del Health Score de ciclo de vida.</p>
      {!risk ? <p role="status">Estimación no disponible.</p> : risk.status !== "ESTIMATED" ?
        <p>No estimable: {reasons[risk.reason] || "el historial requiere revisión"}. {riskAction(risk.reason)} No equivale a riesgo cero.</p> : <>
          <p>Referencia: {calendarDate(risk.as_of)} · {risk.calibrations_used} calibraciones · Probabilidades sin calibración experimental.</p>
          <div className="passport-grid">{Object.entries(risk.horizons).map(([key, value]) => <article key={key} className="passport-horizon">
            <h3>{key.split("_")[0]} días</h3><p>{calendarDate(value.target_date)}</p>
            <strong>{probability(value.probability_out_of_tolerance)}</strong>
            <p>Error previsto: {number(value.predicted_error)} {unit}</p>
            <small>Tolerancia: {number(risk.tolerance)} {unit}</small>
            {value.probability_out_of_tolerance == null && <small>Sin dispersión residual suficiente para asignar probabilidad.</small>}
          </article>)}</div>
        </>}
    </section>
    <section aria-labelledby="calibrations"><h2 id="calibrations">Calibraciones</h2>
      {latest && <article className="passport-summary-card passport-latest-calibration">
        <h3>Última calibración registrada</h3>
        <dl>
          <div><dt>Fecha</dt><dd>{calendarDate(latest.calibration_date)}</dd></div>
          <div><dt>Resultado</dt><dd><span className="passport-detail-status" data-status={String(latest.result).toLowerCase()}>{statusLabel(latest.result)}</span></dd></div>
          <div><dt>Error</dt><dd>{latest.error_value == null ? "Sin datos" : `${number(latest.error_value)} ${unit}`}</dd></div>
          <div><dt>Tolerancia</dt><dd>{latest.tolerance == null ? "Sin datos" : `${number(latest.tolerance)} ${unit}`}</dd></div>
          <div><dt>Próximo vencimiento</dt><dd>{calendarDate(latest.next_due_date)}</dd></div>
        </dl>
      </article>}
      {calibrations === null ? <p>No se ha podido cargar el historial.</p> : !calibrations.length ? <p>No hay calibraciones registradas.</p> :
        <>
          <h3 id="calibration-history">Historial completo</h3>
          <div className="passport-table passport-calibration-history" role="region" aria-labelledby="calibration-history" tabIndex={0}>
            <table><thead><tr><th scope="col">Fecha</th><th scope="col">Próximo vencimiento</th><th scope="col">Error ({unit})</th><th scope="col">Tolerancia ({unit})</th><th scope="col">Resultado</th></tr></thead>
              <tbody>{calibrationHistory.map((item) => <tr key={item.id}><td>{calendarDate(item.calibration_date)}</td><td>{calendarDate(item.next_due_date)}</td><td>{number(item.error_value)}</td><td>{number(item.tolerance)}</td><td><span className="passport-detail-status" data-status={String(item.result).toLowerCase()}>{statusLabel(item.result)}</span></td></tr>)}</tbody>
            </table>
          </div>
        </>}
    </section>
    <section aria-labelledby="maintenance"><h2 id="maintenance">Mantenimiento</h2>
      {maintenance?.length ? <>
        <article className="passport-summary-card passport-detail-card">
          <h3>Última intervención registrada</h3>
          <p><strong>{calendarDate(maintenance[0].event_date)}</strong> · {maintenance[0].description}</p>
        </article>
        <h3>Historial completo</h3>
        <ul className="passport-records">{maintenance.map(event => <li key={event.id} className="passport-summary-card">
          <strong>{calendarDate(event.event_date)}</strong><p>{event.description}</p>
        </li>)}</ul>
      </> : <div className="passport-summary-card"><p>{maintenance == null ? "No se ha podido cargar el mantenimiento." : "No hay intervenciones registradas."}</p></div>}
    </section>
    <section id="documents" aria-labelledby="documents-heading"><h2 id="documents-heading">Documentación vinculada</h2>
      {context?.documents.length ? <ul className="passport-records">{context.documents.map(document => <li key={document.id} className="passport-summary-card">
          <div className="passport-record-header"><strong>{document.original_filename}</strong><span className="passport-detail-status" data-status={String(document.processing_status).toLowerCase()}>{statusLabel(document.processing_status)}</span></div>
          <nav className="passport-links" aria-label={`Acciones de ${document.original_filename}`}>
            <Link to={`/documents/${document.id}/original?passport=${instrument.public_id}`}>Abrir original</Link>
            <Link to={`/?tab=review&documentId=${document.id}&passport=${instrument.public_id}`}>Revisar campos</Link>
          </nav>
        </li>)}</ul> : <div className="passport-summary-card"><p>{context ? "No hay documentos vinculados." : "No se ha podido consultar la documentación."}</p></div>}
    </section>
    <section aria-labelledby="events"><h2 id="events">Historial de eventos</h2>
      <article className="passport-summary-card passport-detail-card">
        <h3>Auditoría del instrumento</h3>
        <p>Consulta los eventos registrados del instrumento, sus documentos y sus calibraciones.</p>
        <p><Link to={auditUrl}>Abrir historial de eventos</Link></p>
      </article>
    </section>
    </main>
  </AppShell>;
}
