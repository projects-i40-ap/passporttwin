import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link, useSearchParams } from "react-router-dom";
import Passport from "./Passport";
import DocumentOriginal from "./DocumentOriginal";
import InstrumentFinder from "./InstrumentFinder";
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
    return afterRules.length > 0 ? afterRules.join(", ") : "none";
  }

  if (Array.isArray(beforeRules)) {
    return beforeRules.length > 0 ? beforeRules.join(", ") : "none";
  }

  return "—";
}


function getEventTone(log) {
  const afterStatus = log.after?.processing_status;

  if (log.action === "FIELD_CORRECTED") {
    return {
      label: "correction",
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
      label: "accepted",
      color: "#15803d",
      background: "#f0fdf4",
      border: "#bbf7d0",
    };
  }

  if (afterStatus === "REVIEW_REQUIRED") {
    return {
      label: "review required",
      color: "#b45309",
      background: "#fffbeb",
      border: "#fde68a",
    };
  }

  return {
    label: "event",
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
        No audit events recorded for this entity.
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
            <th style={headerCellStyle}>Timestamp UTC</th>
            <th style={headerCellStyle}>Action</th>
            <th style={headerCellStyle}>Entity</th>
            <th style={headerCellStyle}>Actor</th>
            <th style={headerCellStyle}>Before → After</th>
            <th style={headerCellStyle}>Rules</th>
            <th style={headerCellStyle}>SHA-256 evidence</th>
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


function tabStyle(isActive) {
  return {
    padding: "10px 18px",
    border: "1px solid #cbd5e1",
    borderRadius: "999px",
    background: isActive ? "#1d4ed8" : "#ffffff",
    color: isActive ? "#ffffff" : "#334155",
    fontWeight: "bold",
    cursor: "pointer",
  };
}


function App() {
  const [params] = useSearchParams();
  const initialTab = params.get("tab") === "audit" ? "audit" : "review";
  const hasDocument = /^\d+$/.test(params.get("documentId") || "");
  const hasAudit = /^\d+$/.test(params.get("id") || "");
  const initialDocument = hasDocument ? params.get("documentId") : "1";
  const initialAudit = hasAudit ? params.get("id") : "1";
  React.useEffect(() => {
    if (initialTab === "review" && hasDocument) loadDocument();
    if (initialTab === "audit" && hasAudit) queryAudit({ preventDefault() {} });
  }, []);

  /* Estado de la vista de revisión documental (pestaña "review"). */
  const [activeTab, setActiveTab] = useState(initialTab);
  const [documentId, setDocumentId] = useState(initialDocument);
  const [loadedDocumentId, setLoadedDocumentId] = useState(null);
  const [processingStatus, setProcessingStatus] = useState("");
  const [fields, setFields] = useState([]);
  const serialCandidates = candidateSerials(fields.find((field) => field.field_name === "serial_candidates")?.raw_value);
  const [materialization, setMaterialization] = useState(null);
  const [savedValues, setSavedValues] = useState({});
  const [projectionWarning, setProjectionWarning] = useState("");
  const hasUnsavedChanges = fields.some(field => field.normalized_value !== savedValues[field.field_id]);
  const isMaterialized = materialization?.status === "MATERIALIZED";
  const [rulesFailed, setRulesFailed] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

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
    setLoadedDocumentId(data.document_id);
    setFields(data.fields);
    setSavedValues(Object.fromEntries(data.fields.map(field => [field.field_id, field.normalized_value])));
    setMaterialization(data.materialization);
    return data;
  }

  async function loadDocument() {
    setLoading(true);
    setMessage("");
    setRulesFailed([]);
    setProjectionWarning("");
    try {
      await refreshDocument(documentId);
      setMessage("Documento cargado.");
    } catch (error) {
      setProcessingStatus(""); setLoadedDocumentId(null); setFields([]); setMaterialization(null);
      setMessage(error.message);
    } finally { setLoading(false); }
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

      setFields((currentFields) =>
        currentFields.map((currentField) =>
          currentField.field_id === data.field_id
            ? {
                ...currentField,
                normalized_value: data.normalized_value,
              }
            : currentField
        )
      );

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
    if (!loadedDocumentId || loading || hasUnsavedChanges || !materialization?.can_materialize) return;
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
        `${data.total_events} audit event(s) retrieved.`
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
      <InstrumentFinder apiBaseUrl={API_BASE_URL} />

      <nav
        aria-label="Vistas de la aplicación"
        style={{
          display: "flex",
          gap: "10px",
          marginTop: "20px",
          marginBottom: "12px",
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={() => setActiveTab("review")}
          aria-pressed={activeTab === "review"}
          style={tabStyle(activeTab === "review")}
        >
          Revisión documental
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("audit")}
          aria-pressed={activeTab === "audit"}
          style={tabStyle(activeTab === "audit")}
        >
          Auditoría y trazabilidad
        </button>
      </nav>

      {activeTab === "review" && (
        <section>
          <h2>Revisión documental</h2>

          <p>
            Revisa y corrige los campos extraídos antes de aceptar el documento.
          </p>

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

          {loadedDocumentId && (
            <p><Link to={`/documents/${loadedDocumentId}/original${params.get("passport") ? `?passport=${encodeURIComponent(params.get("passport"))}` : ""}`}>Abrir original</Link></p>
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
                {processingStatus === "ACCEPTED" ? "Validado para incorporación" : statusLabel(processingStatus)}
              </span>
            </section>
          )}

          {loadedDocumentId && materialization && <section aria-labelledby="materialization-heading" style={{ marginTop: "24px" }}>
            <h3 id="materialization-heading">Incorporación al historial</h3>
            <p role="status">{materialization.message}</p>
            {hasUnsavedChanges && <p>Hay cambios sin guardar. Guarda las correcciones y vuelve a validar antes de continuar.</p>}
            {isMaterialized ? <>
              <p>La consulta es de solo lectura: editar estos campos no actualizaría la calibración ya incorporada.</p>
              {materialization.instrument_public_id && <Link to={`/passport/${encodeURIComponent(materialization.instrument_public_id)}`}>Ver historial en el pasaporte</Link>}
            </> : <button type="button" onClick={materializeDocument}
              disabled={loading || hasUnsavedChanges || !materialization.can_materialize}>
              Incorporar calibración al historial
            </button>}
            {projectionWarning && <p role="alert">{projectionWarning}</p>}
          </section>}

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
                      Estado de validación:{" "}
                      {statusLabel(field.validation_status)}
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
            Immutable, chronologically descending history of every
            change applied to a document or an instrument.
          </p>

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


ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/documents/:documentId/original" element={<DocumentOriginal apiBaseUrl={API_BASE_URL} />} />
        <Route path="/passport/:publicId" element={<Passport apiBaseUrl={API_BASE_URL} />} />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
