import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link, useSearchParams, useLocation } from "react-router-dom";
import Passport from "./Passport";
import DocumentOriginal from "./DocumentOriginal";
import InstrumentFinder from "./InstrumentFinder";
import DocumentFinder from "./DocumentFinder";
import CertificateUpload from "./CertificateUpload";
import "./workspace.css";
import { statusLabel } from "./presentation";


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


/* -------------------------------------------------------------------------
 * Helpers de presentación de la línea temporal de auditoría (RF-AUDIT-08).
 * ---------------------------------------------------------------------- */

function candidateSerials(value) {
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function formatTimestamp(value) {
  if (!value) {
    return "—";
  }

  // El backend persiste `created_at` en UTC. Si la cadena no declara zona,
  // se asume UTC para que el navegador no aplique una conversión local.
  const hasTimezone = /(Z|[+-]\d{2}:\d{2})$/.test(value);
  const parsed = new Date(hasTimezone ? value : `${value}Z`);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return `${parsed.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}


function formatDiffValue(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}


function getEvidenceHash(log) {
  const details = log.details || {};
  const metadata = details.metadata || {};

  return (
    metadata.sha256 ||
    details.certificate_sha256 ||
    details.sha256 ||
    "—"
  );
}


function getRulesLabel(log) {
  if (log.rule_or_model) {
    return log.rule_or_model;
  }

  const afterRules = log.after?.rules_failed;
  const beforeRules = log.before?.rules_failed;

  if (Array.isArray(afterRules)) {
    return afterRules.length > 0 ? afterRules.join(", ") : "Sin reglas incumplidas";
  }

  if (Array.isArray(beforeRules)) {
    return beforeRules.length > 0 ? beforeRules.join(", ") : "Sin reglas incumplidas";
  }

  return "—";
}


function getEventTone(log) {
  const afterStatus = log.after?.processing_status;

  if (log.action === "FIELD_CORRECTED") {
    return {
      label: "Corrección",
      color: "#1d4ed8",
      background: "#eff6ff",
      border: "#bfdbfe",
    };
  }

  if (
    afterStatus === "ACCEPTED" ||
    log.action === "CALIBRATION_INGESTED"
  ) {
    return {
      label: log.action === "CALIBRATION_INGESTED" ? "Incorporación al historial" : "Validación documental",
      color: "#15803d",
      background: "#f0fdf4",
      border: "#bbf7d0",
    };
  }

  if (afterStatus === "REVIEW_REQUIRED") {
    return {
      label: "Requiere revisión",
      color: "#b45309",
      background: "#fffbeb",
      border: "#fde68a",
    };
  }

  return {
    label: "Evento",
    color: "#334155",
    background: "#f8fafc",
    border: "#e2e8f0",
  };
}


const cellStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #e2e8f0",
  verticalAlign: "top",
  fontSize: "0.9rem",
};

const headerCellStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #cbd5e1",
  textAlign: "left",
  fontSize: "0.8rem",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#475569",
  whiteSpace: "nowrap",
};


function DiffCell({ before, after }) {
  if (before === null && after === null) {
    return <span style={{ color: "#64748b" }}>—</span>;
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        fontFamily: "monospace",
        fontSize: "0.85rem",
        maxWidth: "320px",
      }}
    >
      <span style={{ color: "#b91c1c", wordBreak: "break-word" }}>
        {formatDiffValue(before)}
      </span>

      <span style={{ color: "#64748b" }} aria-hidden="true">
        ↓
      </span>

      <span style={{ color: "#15803d", wordBreak: "break-word" }}>
        {formatDiffValue(after)}
      </span>
    </div>
  );
}


function AuditSummary({ entityType, trace }) {
  if (!trace) {
    return null;
  }

  return (
    <section
      style={{
        marginTop: "24px",
        padding: "16px 20px",
        border: "1px solid #cbd5e1",
        borderRadius: "8px",
        background: "#f8fafc",
        display: "flex",
        flexWrap: "wrap",
        gap: "24px",
      }}
    >
      {entityType === "instrument" ? (
        <>
          <div>
            <strong>ID de instrumento:</strong> {trace.instrument_id}
          </div>

          <div>
            <strong>Número de serie:</strong>{" "}
            {trace.serial_number || "—"}
          </div>
        </>
      ) : (
        <>
          <div>
            <strong>ID de documento:</strong> {trace.document_id}
          </div>

          <div>
            <strong>Archivo:</strong>{" "}
            {trace.original_filename || "—"}
          </div>

          <div>
            <strong>Estado de procesamiento:</strong>{" "}
            {statusLabel(trace.processing_status)}
          </div>

          <div style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
            <strong>SHA-256:</strong> {trace.sha256_hash || "—"}
          </div>
        </>
      )}

      <div>
        <strong>Total de eventos:</strong> {trace.total_events}
      </div>
    </section>
  );
}


function AuditTrailTable({ events }) {
  if (!events || events.length === 0) {
    return (
      <p style={{ marginTop: "24px", color: "#64748b" }}>
        No hay eventos de auditoría registrados para esta entidad.
      </p>
    );
  }

  return (
    <div
      style={{
        marginTop: "24px",
        overflowX: "auto",
        border: "1px solid #cbd5e1",
        borderRadius: "8px",
      }}
    >
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          minWidth: "980px",
        }}
      >
        <thead>
          <tr style={{ background: "#f1f5f9" }}>
            <th style={headerCellStyle}>Fecha y hora UTC</th>
            <th style={headerCellStyle}>Acción</th>
            <th style={headerCellStyle}>Entidad</th>
            <th style={headerCellStyle}>Actor / proceso</th>
            <th style={headerCellStyle}>Antes → Después</th>
            <th style={headerCellStyle}>Reglas</th>
            <th style={headerCellStyle}>Evidencia SHA-256</th>
          </tr>
        </thead>

        <tbody>
          {events.map((log) => {
            const tone = getEventTone(log);

            return (
              <tr
                key={log.id}
                style={{ background: tone.background }}
              >
                <td
                  style={{
                    ...cellStyle,
                    whiteSpace: "nowrap",
                    fontFamily: "monospace",
                    fontSize: "0.82rem",
                  }}
                >
                  {formatTimestamp(log.created_at)}
                </td>

                <td style={cellStyle}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 8px",
                      borderRadius: "999px",
                      border: `1px solid ${tone.border}`,
                      color: tone.color,
                      fontWeight: "bold",
                      fontSize: "0.78rem",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {log.action}
                  </span>

                  <div
                    style={{
                      marginTop: "4px",
                      fontSize: "0.72rem",
                      color: tone.color,
                      textTransform: "uppercase",
                    }}
                  >
                    {tone.label}
                  </div>
                </td>

                <td style={cellStyle}>
                  <div>{log.entity_name}</div>
                  <div style={{ color: "#64748b" }}>
                    #{log.entity_id}
                  </div>
                </td>

                <td style={cellStyle}>
                  {log.actor || log.details?.actor || "—"}
                  <div style={{ color: "#64748b" }}>{log.source || log.details?.source || ""}</div>
                </td>

                <td style={cellStyle}>
                  <DiffCell before={log.before} after={log.after} />
                </td>

                <td style={{ ...cellStyle, maxWidth: "180px" }}>
                  {getRulesLabel(log)}
                </td>

                <td
                  style={{
                    ...cellStyle,
                    fontFamily: "monospace",
                    fontSize: "0.78rem",
                    wordBreak: "break-all",
                    maxWidth: "220px",
                  }}
                >
                  {getEvidenceHash(log)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


function App() {
  const [params] = useSearchParams();
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const initialTab = params.get("tab") === "audit" ? "audit" : (params.get("tab") === "review" || params.has("documentId")) ? "review" : "home";
  const hasDocument = /^\d+$/.test(params.get("documentId") || "");
  const hasAudit = /^\d+$/.test(params.get("id") || "");
  const initialDocument = hasDocument ? params.get("documentId") : "";
  const initialAudit = hasAudit ? params.get("id") : "";
  React.useEffect(() => {
    if (initialTab === "review" && hasDocument) loadDocument();
    if (initialTab === "audit" && hasAudit) queryAudit({ preventDefault() {} });
  }, []);

  /* Estado de la vista de revisión documental (pestaña "review"). */
  const activeTab = initialTab;
  const [documentId, setDocumentId] = useState(initialDocument);
  const [loadedDocumentId, setLoadedDocumentId] = useState(null);
  const [loadedDocumentName, setLoadedDocumentName] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const [documentType, setDocumentType] = useState("");
  const canProcessCertificate = documentType === "PDF_CERTIFICATE" &&
    ["RECEIVED", "FAILED_EXTRACTION"].includes(processingStatus);
  const [fields, setFields] = useState([]);
  const serialCandidates = candidateSerials(fields.find((field) => field.field_name === "serial_candidates")?.raw_value);
  const [materialization, setMaterialization] = useState(null);
  const [savedValues, setSavedValues] = useState({});
  const [projectionWarning, setProjectionWarning] = useState("");
  const hasUnsavedChanges = fields.some(field => field.normalized_value !== savedValues[field.field_id]);
  const isMaterialized = materialization?.status === "MATERIALIZED";
  const needsFieldValidation = fields.some(field => ["STAGING", "ACCEPTED"].includes(field.validation_status));
  const [rulesFailed, setRulesFailed] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  React.useEffect(() => {
    if (!hasUnsavedChanges) return;
    const warn = event => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedChanges]);
  function guardNavigation(event) {
    const link = event.target.closest?.("a");
    if (hasUnsavedChanges && link && link.target !== "_blank") {
      const destination = new URL(link.href, window.location.href);
      if (destination.pathname + destination.search !== window.location.pathname + window.location.search) {
        event.preventDefault(); event.stopPropagation();
        setMessage("Guarda o descarta los cambios locales antes de cambiar de vista.");
      }
    }
  }

  /* Estado de la vista de auditoría (pestaña "audit"). */
  const [auditEntityType, setAuditEntityType] = useState(params.get("entity") === "instrument" ? "instrument" : "document");
  const [auditEntityId, setAuditEntityId] = useState(initialAudit);
  const [auditTrace, setAuditTrace] = useState(null);
  const [auditMessage, setAuditMessage] = useState("");
  const [auditLoading, setAuditLoading] = useState(false);

  async function refreshDocument(id) {
    const response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/fields`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se han podido cargar los campos del documento.");
    setProcessingStatus(data.processing_status);
    setDocumentType(data.source_type);
    setLoadedDocumentId(data.document_id);
    setLoadedDocumentName(data.original_filename || "");
    setFields(data.fields);
    setSavedValues(Object.fromEntries(data.fields.map(field => [field.field_id, field.normalized_value])));
    setMaterialization(data.materialization);
    return data;
  }

  async function loadDocument() {
    if (hasUnsavedChanges) { setMessage("Guarda o descarta los cambios locales antes de cargar otro documento."); return; }
    setLoading(true);
    setMessage("");
    setRulesFailed([]);
    setProjectionWarning("");
    try {
      await refreshDocument(documentId);
      setMessage("Documento cargado.");
    } catch (error) {
      setProcessingStatus(""); setLoadedDocumentId(null); setLoadedDocumentName(""); setFields([]); setMaterialization(null);
      setMessage(error.message);
    } finally { setLoading(false); }
  }

  async function processCertificate() {
    if (!loadedDocumentId || !canProcessCertificate || loading || hasUnsavedChanges) return;
    const id = loadedDocumentId;
    setLoading(true);
    setMessage("Procesando certificado…");
    setRulesFailed([]);
    let processed = false;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/documents/${id}/process?extractor=deterministic`,
        { method: "POST" },
      );
      // The API persists FAILED_EXTRACTION before returning 422.
      if (!response.ok && response.status !== 422) throw new Error();
      const result = await response.json();
      const status = response.status === 422 ? "FAILED_EXTRACTION" : result.processing_status;
      processed = true;
      setProcessingStatus(status);
      setDocumentRefresh(value => value + 1);
      await refreshDocument(id);
      setRulesFailed(result.rules_failed || []);
      setMessage(status === "FAILED_EXTRACTION"
        ? "No se pudieron extraer los campos del PDF."
        : "Certificado procesado. Comprueba los campos extraídos.");
    } catch {
      setMessage(processed
        ? "El certificado se procesó, pero no se pudieron cargar los campos. Recarga la página."
        : "No se pudo confirmar el procesado. Recarga el documento antes de volver a intentarlo.");
    } finally {
      setLoading(false);
    }
  }

  function updateNormalizedValue(fieldId, value) {
    setFields((currentFields) =>
      currentFields.map((field) =>
        field.field_id === fieldId
          ? {
              ...field,
              normalized_value: value,
            }
          : field
      )
    );
  }

  async function saveField(field) {
    setLoading(true);
    setMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/documents/${loadedDocumentId}/fields/${field.field_id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            normalized_value: field.normalized_value,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "No se ha podido guardar la corrección."
        );
      }

      setFields(currentFields => currentFields.map(currentField => ({
        ...currentField,
        ...(currentField.field_id === data.field_id ? { normalized_value: data.normalized_value } : {}),
        validation_status: data.field_validation?.find(item => item.field_id === currentField.field_id)?.validation_status || currentField.validation_status,
      })));

      setSavedValues(current => ({ ...current, [data.field_id]: data.normalized_value }));
      setProcessingStatus("REVIEW_REQUIRED");
      setMaterialization({ status: "NOT_MATERIALIZED", can_materialize: false, message: "Corrección guardada. Vuelve a validar los campos." });
      setMessage("Corrección guardada. Vuelve a validar los campos antes de incorporar la calibración.");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function revalidateDocument() {
    setLoading(true);
    setMessage("");
    setRulesFailed([]);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/documents/${loadedDocumentId}/revalidate`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "No se ha podido volver a validar el documento."
        );
      }

      await refreshDocument(loadedDocumentId);
      setRulesFailed(data.rules_failed || []);

      if (data.processing_status === "ACCEPTED") {
        setMessage("Campos validados. La calibración todavía no se ha incorporado al historial.");
      } else {
        setMessage(
          "El documento todavía requiere revisión."
        );
      }
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function materializeDocument() {
    if (!loadedDocumentId || loading || hasUnsavedChanges || needsFieldValidation || !materialization?.can_materialize) return;
    const id = loadedDocumentId;
    setLoading(true); setMessage(""); setProjectionWarning("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/accept`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        // A previous request may have committed while its response was lost.
        // Only canonical evidence from the refreshed server state can confirm it.
        await refreshDocument(id);
        throw new Error(data.detail || "No se ha podido incorporar la calibración.");
      }
      if (data.status !== "CANONICAL_COMMITTED") throw new Error("No se ha podido confirmar la incorporación al historial.");
      setMessage("Calibración incorporada al historial canónico.");
      if (data.aas_projection?.status === "ERROR") setProjectionWarning("La calibración está guardada en PostgreSQL, pero la actualización AAS no se ha completado. Revisa la sincronización del instrumento.");
      try { await refreshDocument(id); }
      catch { setMaterialization({ status: "MATERIALIZED", can_materialize: false, instrument_id: data.instrument_id, calibration_event_id: data.calibration_event_id, message: "Incorporación confirmada. Recarga el documento para consultar su estado actualizado." }); }
    } catch (error) {
      setMessage(error.message);
    } finally { setLoading(false); }
  }

  async function queryAudit(event) {
    event.preventDefault();

    if (!auditEntityId) {
      return;
    }

    setAuditLoading(true);
    setAuditMessage("");

    try {
      const resource =
        auditEntityType === "instrument"
          ? "instruments"
          : "documents";

      const response = await fetch(
        `${API_BASE_URL}/api/v1/${resource}/${auditEntityId}/audit`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "No se ha podido cargar la auditoría."
        );
      }

      setAuditTrace(data);
      setAuditMessage(
        `${data.total_events} eventos de auditoría encontrados.`
      );
    } catch (error) {
      setAuditTrace(null);
      setAuditMessage(error.message);
    } finally {
      setAuditLoading(false);
    }
  }

  return (
    <main
      onClickCapture={guardNavigation}
      style={{
        fontFamily: "Arial, sans-serif",
        maxWidth: "1280px",
        margin: "0 auto",
        padding: "40px 24px",
      }}
    >
      <h1>PassportTwin</h1>
      {/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(params.get("passport") || "") &&
        <Link to={`/passport/${params.get("passport")}`}>Volver al pasaporte</Link>}
      <nav aria-label="Vistas de la aplicación" className="workspace-nav">
        <Link to="/" aria-current={activeTab === "home" ? "page" : undefined}>Inicio</Link>
        <Link to="/?tab=review" aria-current={activeTab === "review" ? "page" : undefined}>Revisión documental</Link>
        <Link to="/?tab=audit" aria-current={activeTab === "audit" ? "page" : undefined}>Auditoría y trazabilidad</Link>
      </nav>

      {activeTab === "home" && <>
        <section aria-labelledby="tasks-heading">
          <h2 id="tasks-heading">¿Qué necesitas hacer?</h2>
          <div className="workspace-tasks">
            <a href="#inventory"><strong>Consultar un pasaporte</strong><span>Busca un instrumento por serie o ubicación y consulta su historial.</span></a>
            <Link to="/?tab=review"><strong>Revisar un documento</strong><span>Encuentra el certificado por nombre o instrumento, revisa sus campos e incorpóralo al historial.</span></Link>
            <Link to="/?tab=audit"><strong>Consultar trazabilidad</strong><span>Selecciona un documento o instrumento para ver sus eventos y correcciones.</span></Link>
          </div>
        </section>
        <div id="inventory"><InstrumentFinder apiBaseUrl={API_BASE_URL} /></div>
      </>}

      {activeTab === "review" && (
        <section>
          <h2>Revisión documental</h2>

          <p>
            Busca el documento, comprueba su original y revisa los campos antes de incorporar una calibración al historial.
          </p>

          <CertificateUpload apiBaseUrl={API_BASE_URL} onUploaded={() => setDocumentRefresh(value => value + 1)} />
          <DocumentFinder apiBaseUrl={API_BASE_URL} mode="review" refresh={documentRefresh} />
          <details className="workspace-advanced">
            <summary>Buscar por ID de documento (avanzado)</summary>
          <section
            style={{
              marginTop: "32px",
              padding: "20px",
              border: "1px solid #ccc",
              borderRadius: "8px",
            }}
          >
            <label
              htmlFor="document-id"
              style={{
                display: "block",
                marginBottom: "8px",
                fontWeight: "bold",
              }}
            >
              ID de documento
            </label>

            <div
              style={{
                display: "flex",
                gap: "12px",
                alignItems: "center",
              }}
            >
              <input
                id="document-id"
                type="number"
                min="1"
                value={documentId}
                onChange={(event) =>
                  setDocumentId(event.target.value)
                }
                style={{
                  padding: "8px",
                  width: "140px",
                }}
              />

              <button
                type="button"
                onClick={loadDocument}
                disabled={loading || !documentId}
              >
                Cargar documento
              </button>
            </div>
          </section>

          </details>

          {loadedDocumentId && (
            <section aria-label="Documento seleccionado"><h3>{loadedDocumentName || `Documento ${loadedDocumentId}`}</h3>
            <p><Link to={`/documents/${loadedDocumentId}/original${params.get("passport") ? `?passport=${encodeURIComponent(params.get("passport"))}` : ""}`}>Abrir original</Link></p>
            {canProcessCertificate && <button type="button" onClick={processCertificate} disabled={loading || hasUnsavedChanges}>
              {processingStatus === "FAILED_EXTRACTION" ? "Reintentar extracción" : "Procesar certificado"}
            </button>}
            </section>
          )}

          {processingStatus && (
            <section style={{ marginTop: "24px" }}>
              <strong>Estado de los campos del documento:</strong>{" "}
              <span
                style={{
                  color:
                    processingStatus === "ACCEPTED"
                      ? "#15803d"
                      : processingStatus === "REVIEW_REQUIRED"
                        ? "#b45309"
                        : "#334155",
                  fontWeight: "bold",
                }}
              >
                {processingStatus === "ACCEPTED" ? (needsFieldValidation ? "Aceptado en staging; comprobaciones sin registrar" : "Validado para incorporación") : statusLabel(processingStatus)}
              </span>
            </section>
          )}

          {loadedDocumentId && materialization && <section aria-labelledby="materialization-heading" style={{ marginTop: "24px" }}>
            <h3 id="materialization-heading">Incorporación al historial</h3>
            <p role="status">{!isMaterialized && needsFieldValidation ? "Valida los campos guardados para registrar las comprobaciones antes de incorporar." : materialization.message}</p>
            {hasUnsavedChanges && <p>Hay cambios sin guardar. Guarda las correcciones y vuelve a validar antes de continuar.</p>}
            {isMaterialized ? <>
              <p>La consulta es de solo lectura: editar estos campos no actualizaría la calibración ya incorporada.</p>
              {materialization.instrument_public_id && <Link to={`/passport/${encodeURIComponent(materialization.instrument_public_id)}`}>Ver historial en el pasaporte</Link>}
            </> : <button type="button" onClick={materializeDocument}
              disabled={loading || hasUnsavedChanges || needsFieldValidation || !materialization.can_materialize}>
              Incorporar calibración al historial
            </button>}
            {projectionWarning && <p role="alert">{projectionWarning}</p>}
          </section>}

          {hasUnsavedChanges && <p><button type="button" disabled={loading} onClick={() => {
            setFields(current => current.map(field => ({ ...field, normalized_value: savedValues[field.field_id] })));
            setMessage("Cambios locales descartados. Los valores guardados no se han modificado.");
          }}>Descartar cambios sin guardar</button></p>}

          {message && (
            <p role="status" style={{ marginTop: "20px" }}>
              {message}
            </p>
          )}

          {rulesFailed.length > 0 && (
            <section style={{ marginTop: "24px" }}>
              <h3>Reglas de validación pendientes</h3>

              <ul>
                {rulesFailed.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </section>
          )}

          {fields.length > 0 && (
            <section style={{ marginTop: "32px" }}>
              <h3>Campos extraídos</h3>
              <p>Los estados reflejan las reglas documentales disponibles, no una certificación metrológica. Error y tolerancia no se comprueban en esta fase.</p>

              <div
                style={{
                  display: "grid",
                  gap: "16px",
                }}
              >
                {fields.map((field) => (
                  field.field_name === "serial_candidates" ? (
                    <article key={field.field_id} style={{ padding: "16px", border: "1px solid #ddd", borderRadius: "8px" }}>
                      <h4>Series detectadas en el documento</h4>
                      <ul>{candidateSerials(field.raw_value).map((serial) => <li key={serial}>{serial}</li>)}</ul>
                      <p>Comprueba el certificado, elige una serie en el campo de vinculación, guarda la corrección y vuelve a validar. Esta evidencia es de solo lectura.</p>
                    </article>
                  ) : <article
                    key={field.field_id}
                    style={{
                      padding: "16px",
                      border: "1px solid #ddd",
                      borderRadius: "8px",
                    }}
                  >
                    <div
                      style={{
                        marginBottom: "12px",
                        fontWeight: "bold",
                      }}
                    >
                      {field.field_name === "serial_number" && serialCandidates.length > 1 ? "Serie para vincular" : field.field_name}
                    </div>

                    <div style={{ marginBottom: "12px" }}>
                      <div>
                        <strong>Valor original:</strong>
                      </div>

                      <div>{field.raw_value}</div>
                    </div>

                    <label
                      htmlFor={`field-${field.field_id}`}
                      style={{
                        display: "block",
                        marginBottom: "6px",
                        fontWeight: "bold",
                      }}
                    >
                      Valor normalizado
                    </label>

                    <div
                      style={{
                        display: "flex",
                        gap: "12px",
                        alignItems: "center",
                        flexWrap: "wrap",
                      }}
                    >
                      {field.field_name === "serial_number" && serialCandidates.length > 1 ? (
                        <select id={`field-${field.field_id}`} value={field.normalized_value ?? ""}
                          onChange={(event) => updateNormalizedValue(field.field_id, event.target.value)}
                          disabled={loading || isMaterialized} style={{ flex: 1, padding: "8px", minWidth: 0 }}>
                          <option value="">Selecciona una serie tras revisar el certificado</option>
                          {serialCandidates.map((serial) => <option key={serial} value={serial}>{serial}</option>)}
                        </select>
                      ) : <input
                        id={`field-${field.field_id}`}
                        type="text"
                        disabled={loading || isMaterialized}
                        value={field.normalized_value ?? ""}
                        onChange={(event) =>
                          updateNormalizedValue(
                            field.field_id,
                            event.target.value
                          )
                        }
                        style={{
                          flex: 1,
                          minWidth: 0,
                          padding: "8px",
                        }}
                      />}

                      <button
                        type="button"
                        onClick={() => saveField(field)}
                        disabled={loading || isMaterialized}
                      >
                        Guardar corrección
                      </button>
                    </div>

                    <div
                      style={{
                        marginTop: "10px",
                        fontSize: "0.9rem",
                      }}
                    >
                      Comprobación del campo:{" "}
                      {field.normalized_value !== savedValues[field.field_id] ? "Cambio sin guardar" : ({
                        STAGING: "Sin comprobación vigente registrada",
                        ACCEPTED: "Sin comprobación vigente registrada",
                        VALIDATED: "Comprobado por las reglas documentales",
                        REVIEW_REQUIRED: "Requiere revisión",
                        NOT_EVALUATED: "No evaluado por las reglas documentales",
                        EVIDENCE: "Evidencia de solo lectura",
                      })[field.validation_status] || statusLabel(field.validation_status)}
                    </div>
                  </article>
                ))}
              </div>

              <button
                type="button"
                onClick={revalidateDocument}
                disabled={loading || isMaterialized || hasUnsavedChanges}
                style={{
                  marginTop: "24px",
                  padding: "10px 16px",
                }}
              >
                Validar campos guardados
              </button>
            </section>
          )}
        </section>
      )}

      {activeTab === "audit" && (
        <section>
          <h2>Auditoría y trazabilidad</h2>

          <p>
            Consulta el historial de eventos y correcciones, ordenado del más reciente al más antiguo.
          </p>

          <InstrumentFinder apiBaseUrl={API_BASE_URL} mode="audit" />
          <DocumentFinder apiBaseUrl={API_BASE_URL} mode="audit" />
          <details className="workspace-advanced">
            <summary>Consultar por ID (avanzado)</summary>
          <form
            onSubmit={queryAudit}
            style={{
              marginTop: "32px",
              padding: "20px",
              border: "1px solid #ccc",
              borderRadius: "8px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-end",
              flexWrap: "wrap",
            }}
          >
            <div>
              <label
                htmlFor="audit-entity-type"
                style={{
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold",
                }}
              >
                Buscar por
              </label>

              <select
                id="audit-entity-type"
                value={auditEntityType}
                onChange={(event) =>
                  setAuditEntityType(event.target.value)
                }
                style={{ padding: "8px", minWidth: "170px" }}
              >
                <option value="document">ID de documento</option>
                <option value="instrument">ID de instrumento</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="audit-entity-id"
                style={{
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold",
                }}
              >
                {auditEntityType === "instrument"
                  ? "ID de instrumento"
                  : "ID de documento"}
              </label>

              <input
                id="audit-entity-id"
                type="number"
                min="1"
                value={auditEntityId}
                onChange={(event) =>
                  setAuditEntityId(event.target.value)
                }
                style={{ padding: "8px", width: "140px" }}
              />
            </div>

            <button
              type="submit"
              disabled={auditLoading || !auditEntityId}
            >
              {auditLoading ? "Consultando..." : "Consultar auditoría"}
            </button>
          </form>

          </details>

          {auditMessage && (
            <p style={{ marginTop: "20px" }}>{auditMessage}</p>
          )}

          <AuditSummary
            entityType={auditEntityType}
            trace={auditTrace}
          />

          {auditTrace && (
            <AuditTrailTable events={auditTrace.events} />
          )}
        </section>
      )}
    </main>
  );
}


function Workspace() {
  const location = useLocation();
  return <App key={location.pathname + location.search} />;
}

ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/documents/:documentId/original" element={<DocumentOriginal apiBaseUrl={API_BASE_URL} />} />
        <Route path="/passport/:publicId" element={<Passport apiBaseUrl={API_BASE_URL} />} />
        <Route path="*" element={<Workspace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
