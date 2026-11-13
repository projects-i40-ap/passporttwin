import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Link, useBlocker, useSearchParams, useLocation } from "react-router-dom";
import Passport from "./Passport";
import AppShell from "./AppShell";
import DocumentOriginal from "./DocumentOriginal";
import InstrumentFinder from "./InstrumentFinder";
import DocumentFinder from "./DocumentFinder";
import DocumentLibrary from "./DocumentLibrary";
import DocumentChat from "./DocumentChat";
import DocumentTypeLink from "./DocumentTypeLink";
import NewInstrumentForm from "./NewInstrumentForm";
import CertificateUpload from "./CertificateUpload";
import "./workspace.css";
import { auditKeyLabel, documentFieldLabel, statusLabel } from "./presentation";


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

  if (Array.isArray(value)) {
    return value.length
      ? value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join(" · ")
      : "—";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return value === "" ? "«vacío»" : String(value);
}


/** Convierte `before`/`after` en filas legibles por clave, sin JSON en una línea. */
function diffRows(before, after) {
  const asObject = (value) =>
    value && typeof value === "object" && !Array.isArray(value) ? value : null;

  const beforeObject = asObject(before);
  const afterObject = asObject(after);

  if (!beforeObject && !afterObject) {
    return JSON.stringify(before) === JSON.stringify(after)
      ? []
      : [{ key: "valor", before, after }];
  }

  const keys = [
    ...new Set([...Object.keys(beforeObject || {}), ...Object.keys(afterObject || {})]),
  ];

  return keys
    .map((key) => ({ key, before: beforeObject?.[key], after: afterObject?.[key] }))
    .filter(({ before: oldValue, after: newValue }) =>
      JSON.stringify(oldValue) !== JSON.stringify(newValue));
}


function DiffValue({ value }) {
  const text = formatDiffValue(value);

  if (text.length <= 80) {
    return <span className="audit-diff-value">{text}</span>;
  }

  return (
    <details className="audit-diff-value audit-diff-long">
      <summary>{text.slice(0, 60)}…</summary>
      <pre>{text}</pre>
    </details>
  );
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


function DiffCell({ before, after }) {
  const rows = diffRows(before, after);

  if (rows.length === 0) {
    return <span className="audit-cell-muted">—</span>;
  }

  return (
    <div className="audit-diff">
      {rows.map(({ key, before: oldValue, after: newValue }) => (
        <div className="audit-diff-row" key={key}>
          <span className="audit-diff-key">{auditKeyLabel(key)}</span>
          <div className="audit-diff-values">
            <DiffValue value={oldValue} />
            <span className="audit-diff-arrow" aria-hidden="true">→</span>
            <DiffValue value={newValue} />
          </div>
        </div>
      ))}
    </div>
  );
}


function AuditSummary({ entityType, trace }) {
  if (!trace) {
    return null;
  }

  return (
    <section className="audit-summary">
      {entityType === "instrument" ? (
        <>
          <div>
            <strong>ID de instrumento</strong>
            {trace.instrument_id}
          </div>

          <div>
            <strong>Número de serie</strong>
            {trace.serial_number || "—"}
          </div>
        </>
      ) : (
        <>
          <div>
            <strong>ID de documento</strong>
            {trace.document_id}
          </div>

          <div>
            <strong>Archivo</strong>
            {trace.original_filename || "—"}
          </div>

          <div>
            <strong>Estado de procesamiento</strong>
            {statusLabel(trace.processing_status)}
          </div>

          <div className="audit-mono">
            <strong>SHA-256</strong>
            {trace.sha256_hash || "—"}
          </div>
        </>
      )}

      <div>
        <strong>Total de eventos</strong>
        {trace.total_events}
      </div>
    </section>
  );
}


function AuditTrailTable({ events }) {
  if (!events || events.length === 0) {
    return (
      <p className="audit-empty">
        No hay eventos de auditoría registrados para esta entidad.
      </p>
    );
  }

  return (
    <div className="audit-table-wrap">
      <table className="audit-table">
        <thead>
          <tr>
            <th scope="col">Fecha y hora UTC</th>
            <th scope="col">Acción</th>
            <th scope="col">Entidad</th>
            <th scope="col">Actor / proceso</th>
            <th scope="col">Antes → Después</th>
            <th scope="col">Reglas</th>
            <th scope="col">Evidencia SHA-256</th>
          </tr>
        </thead>

        <tbody>
          {events.map((log) => {
            const tone = getEventTone(log);

            return (
              <tr
                key={log.id}
                style={{
                  "--tone-fill": tone.background,
                  "--tone-text": tone.color,
                  "--tone-border": tone.border,
                }}
              >
                <td className="audit-cell-time">
                  {formatTimestamp(log.created_at)}
                </td>

                <td>
                  <span className="audit-badge">{log.action}</span>

                  <div className="audit-badge-label">{tone.label}</div>
                </td>

                <td>
                  <div>{log.entity_name}</div>
                  <div className="audit-cell-muted">#{log.entity_id}</div>
                </td>

                <td>
                  {log.actor || log.details?.actor || "—"}
                  <div className="audit-cell-muted">
                    {log.source || log.details?.source || ""}
                  </div>
                </td>

                <td>
                  <DiffCell before={log.before} after={log.after} />
                </td>

                <td className="audit-cell-rules">{getRulesLabel(log)}</td>

                <td className="audit-cell-mono">{getEvidenceHash(log)}</td>
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
  const { hash } = useLocation();
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const requestedTab = params.get("tab");
  const initialTab = requestedTab === "audit" ? "audit"
    : requestedTab === "documents" ? "documents"
    : requestedTab === "chat" ? "chat"
    : requestedTab === "review" || params.has("documentId") ? "review"
    : requestedTab === "inventory" || hash === "#inventory" ? "inventory"
    : "home";
  const hasDocument = /^\d+$/.test(params.get("documentId") || "");
  const hasAudit = /^\d+$/.test(params.get("id") || "");
  const reviewingDocument = initialTab === "review" && hasDocument;
  const auditingDocument = initialTab === "audit" && hasAudit && params.get("entity") !== "instrument";
  const passportId = params.get("passport");
  const hasPassport = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(passportId || "");
  const auditingPassport = initialTab === "audit" && hasAudit && params.get("entity") === "instrument" && hasPassport;
  const initialDocument = hasDocument ? params.get("documentId") : "";
  const initialAudit = hasAudit ? params.get("id") : "";
  const passportQuery = params.get("passport") ? `&passport=${encodeURIComponent(params.get("passport"))}` : "";
  const originalQuery = passportQuery.replace(/^&/, "?");
  React.useEffect(() => {
    if (initialTab === "review" && hasDocument) loadDocument();
    if (initialTab === "audit" && hasAudit) queryAudit({ preventDefault() {} });
  }, []);

  /* Estado de la vista de revisión documental (pestaña "review"). */
  const activeTab = initialTab;
  const [documentId, setDocumentId] = useState(initialDocument);
  const [loadedDocumentId, setLoadedDocumentId] = useState(null);
  React.useEffect(() => {
    if ((reviewingDocument || hash === "#selected-document") && loadedDocumentId != null) {
      document.getElementById("selected-document")?.focus();
    }
  }, [hash, loadedDocumentId, reviewingDocument]);
  React.useEffect(() => {
    if (auditingDocument || auditingPassport) document.getElementById("workspace-title")?.focus();
  }, [auditingDocument, auditingPassport]);
  const [loadedDocumentName, setLoadedDocumentName] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [linkedTypeId, setLinkedTypeId] = useState(null);
  const canProcessCertificate = documentType === "PDF_CERTIFICATE" &&
    ["RECEIVED", "FAILED_EXTRACTION"].includes(processingStatus);
  const [fields, setFields] = useState([]);
  const [missingFields, setMissingFields] = useState([]);
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
  const navigation = useBlocker(({ currentLocation, nextLocation }) => hasUnsavedChanges &&
    (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));
  const navigationWarning = React.useRef(null);
  const previousFocus = React.useRef(null);
  React.useEffect(() => {
    if (navigation.state !== "blocked") return;
    previousFocus.current = document.activeElement;
    navigationWarning.current?.focus();
  }, [navigation.state]);
  React.useEffect(() => {
    if (!hasUnsavedChanges && navigation.state === "blocked") navigation.reset();
  }, [hasUnsavedChanges, navigation]);

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
    setLinkedTypeId(data.instrument_type_id ?? null);
    setLoadedDocumentName(data.original_filename || "");
    setFields(data.fields);
    setMissingFields(data.missing_fields || []);
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
      setProcessingStatus(""); setLoadedDocumentId(null); setLoadedDocumentName(""); setFields([]); setMissingFields([]); setMaterialization(null);
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
        `${API_BASE_URL}/api/v1/documents/${id}/process?extractor=auto`,
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

      if (data.processing_status !== "ACCEPTED") {
        setMessage("El documento todavía requiere revisión.");
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
    <AppShell active={activeTab}>
    <main className="passport workspace-page" data-view={activeTab}>
      <header className="workspace-heading">
      <p>Espacio de trabajo</p>
      <h1 id="workspace-title" tabIndex={-1}>{auditingPassport ? "Historial de eventos" : { home: "Inicio", inventory: "Inventario", review: "Revisión documental", documents: "Biblioteca documental", chat: "Consulta documental", audit: "Auditoría y trazabilidad" }[activeTab]}</h1>
      {activeTab === "home" && <p>Pasaportes digitales y trazabilidad de instrumentos.</p>}
      {(reviewingDocument || auditingDocument) && <p>
        <Link to={`/?tab=${activeTab}${passportQuery}`}>Volver a buscar documentos</Link>
      </p>}
      {hasPassport && <Link className={auditingPassport ? "passport-primary-action" : "workspace-back"} to={`/passport/${passportId}`}>Volver al pasaporte</Link>}
      </header>
      {navigation.state === "blocked" && <div className="workspace-panel document-review-actions">
        <p ref={navigationWarning} tabIndex={-1} role="alert">Tienes correcciones sin guardar. Si sales, perderás esos cambios.</p>
        <div className="workspace-pages">
          <button type="button" onClick={() => {
            navigation.reset();
            previousFocus.current?.focus();
          }}>Seguir editando</button>
          <button type="button" onClick={navigation.proceed}>Descartar cambios y salir</button>
        </div>
      </div>}

      {activeTab === "home" && <nav className="workspace-tasks" aria-label="Accesos de inicio">
        <Link className="workspace-task-primary" to="/?tab=inventory">
          <strong>Inventario</strong><span>Busca un instrumento por nombre, etiqueta, número de serie o ubicación.</span>
        </Link>
        <Link to="/?tab=review"><strong>Revisión documental</strong><span>Sube un certificado o revisa sus campos.</span></Link>
        <Link to="/?tab=chat"><strong>Consulta documental</strong><span>Pregunta en lenguaje natural y comprueba las referencias citadas.</span></Link>
        <Link to="/?tab=audit"><strong>Auditoría</strong><span>Consulta eventos y correcciones.</span></Link>
      </nav>}

      {activeTab === "inventory" && <>
        <div id="inventory"><InstrumentFinder apiBaseUrl={API_BASE_URL} /></div>
        <NewInstrumentForm apiBaseUrl={API_BASE_URL} />
      </>}

      {activeTab === "documents" && (
        <div id="document-library">
          <DocumentLibrary apiBaseUrl={API_BASE_URL} />
        </div>
      )}

      {activeTab === "chat" && (
        <div id="document-chat">
          <DocumentChat apiBaseUrl={API_BASE_URL} />
        </div>
      )}

      {activeTab === "review" && (
        <section>
          {!reviewingDocument && <>
          <p>
            Sube y procesa un certificado nuevo o busca uno existente. Revisa los campos, guarda las correcciones, valida e incorpora la calibración al historial.
          </p>

          <CertificateUpload apiBaseUrl={API_BASE_URL} onUploaded={() => setDocumentRefresh(value => value + 1)} />
          <DocumentFinder apiBaseUrl={API_BASE_URL} mode="review" refresh={documentRefresh} />
          <details className="workspace-advanced">
            <summary>Buscar por ID de documento (avanzado)</summary>
          <section className="workspace-inline-form">
            <label htmlFor="document-id" className="workspace-form-label">
              ID de documento
            </label>

            <div className="workspace-form-row">
              <input
                id="document-id"
                type="number"
                min="1"
                value={documentId}
                onChange={(event) =>
                  setDocumentId(event.target.value)
                }
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
          </>}

          {reviewingDocument && loading && !loadedDocumentId && <p role="status">Cargando documento…</p>}

          {loadedDocumentId && (
            <section aria-labelledby="selected-document"><h3 id="selected-document" tabIndex={-1}>{loadedDocumentName || `Documento ${loadedDocumentId}`}</h3>
            <nav className="document-review-controls" aria-label="Acciones del documento">
              <Link to={`/documents/${loadedDocumentId}/original${originalQuery}`}>Abrir original</Link>
              {fields.length > 0 && <a href="#extracted-fields">{isMaterialized ? "Ver campos extraídos" : "Revisar y corregir campos"}</a>}
              <Link to={`/?tab=audit&entity=document&id=${loadedDocumentId}${passportQuery}`}>Ver auditoría del documento</Link>
            </nav>
            {canProcessCertificate && <button type="button" onClick={processCertificate} disabled={loading || hasUnsavedChanges}>
              {processingStatus === "FAILED_EXTRACTION" ? "Reintentar extracción" : "Procesar documento"}
            </button>}
            </section>
          )}

          {loadedDocumentId && documentType === "PDF_DATASHEET" && (
            <DocumentTypeLink
              documentId={loadedDocumentId}
              apiBaseUrl={API_BASE_URL}
              linkedTypeId={linkedTypeId}
              onLinked={() => refreshDocument(loadedDocumentId)}
            />
          )}

          {processingStatus && (
            <section className="workspace-status-line">
              <strong>Estado del documento:</strong>{" "}
              <span
                className="passport-detail-status"
                data-status={String(processingStatus).toLowerCase()}
              >
                {isMaterialized ? "Incorporado al historial" : processingStatus === "ACCEPTED" ? (needsFieldValidation ? "Pendiente de registrar comprobaciones" : documentType === "PDF_DATASHEET" ? "Ficha revisada" : "Validado para incorporación") : statusLabel(processingStatus)}
              </span>
            </section>
          )}

          {loadedDocumentId && materialization && <section aria-labelledby="materialization-heading" className="document-review-actions">
            <h3 id="materialization-heading">Revisión e incorporación</h3>
            <p role="status">{!isMaterialized && needsFieldValidation ? "Valida los campos guardados para registrar las comprobaciones antes de incorporar." : materialization.message}</p>
            {hasUnsavedChanges && <p>Hay cambios sin guardar. Guarda las correcciones y vuelve a validar antes de continuar.</p>}
            {isMaterialized ? <>
              <p>La consulta es de solo lectura: editar estos campos no actualizaría la calibración ya incorporada.</p>
              {materialization.instrument_public_id && <Link to={`/passport/${encodeURIComponent(materialization.instrument_public_id)}`}>Ver historial en el pasaporte</Link>}
            </> : <div className="document-review-controls">
              {fields.length > 0 && (needsFieldValidation || !materialization.can_materialize) ? (
                <button type="button" onClick={revalidateDocument} disabled={loading || hasUnsavedChanges}>
                  Validar campos guardados
                </button>
              ) : (
                <button type="button" onClick={materializeDocument}
                  disabled={loading || hasUnsavedChanges || !materialization.can_materialize}>
                  Incorporar calibración al historial
                </button>
              )}
            </div>}
            {projectionWarning && <p role="alert">{projectionWarning}</p>}
          </section>}

          {hasUnsavedChanges && <p><button type="button" disabled={loading} onClick={() => {
            setFields(current => current.map(field => ({ ...field, normalized_value: savedValues[field.field_id] })));
            setMessage("Cambios locales descartados. Los valores guardados no se han modificado.");
          }}>Descartar cambios sin guardar</button></p>}

          {message && (
            <p role="status">
              {message}
            </p>
          )}

          {rulesFailed.length > 0 && (
            <section className="workspace-panel">
              <h3>Reglas de validación pendientes</h3>

              <ul>
                {rulesFailed.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </section>
          )}

          {missingFields.length > 0 && (
            <section className="workspace-panel" aria-labelledby="missing-fields">
              <h3 id="missing-fields" tabIndex={-1}>Campos no encontrados en el documento</h3>

              <p>
                El extractor no ha localizado estos datos en el texto del PDF: puede que el certificado no los incluya
                o que la etiqueta no esté reconocida. Compáralo con el original antes de continuar.
              </p>

              <ul>
                {missingFields.map(({ field_name, required }) => (
                  <li key={field_name}>
                    <strong>{documentFieldLabel(field_name)}</strong>
                    {": "}
                    {required
                      ? "obligatorio, bloquea la validación (R-MISSING-01)."
                      : "opcional, no bloquea la validación."}
                  </li>
                ))}
              </ul>

              <p>
                Esta pantalla solo permite corregir los campos ya extraídos. Si el dato sí aparece en el original,
                el fallo está en la extracción y debe resolverse antes de incorporar la calibración.
              </p>
            </section>
          )}

          {fields.length > 0 && (
            <section>
              <h3 id="extracted-fields" tabIndex={-1}>Campos extraídos</h3>
              <p>Los estados reflejan las reglas documentales disponibles, no una certificación metrológica. Error y tolerancia no se comprueban en esta fase.</p>

              <div className="workspace-field-grid">
                {fields.map((field) => (
                  field.field_name === "serial_candidates" ? (
                    <article key={field.field_id} className="workspace-panel">
                      <h4>Series detectadas en el documento</h4>
                      <ul>{candidateSerials(field.raw_value).map((serial) => <li key={serial}>{serial}</li>)}</ul>
                      <p>Comprueba el certificado, elige una serie en el campo de vinculación, guarda la corrección y vuelve a validar. Esta evidencia es de solo lectura.</p>
                    </article>
                  ) : <article
                    key={field.field_id}
                    className="workspace-panel"
                  >
                    <div className="workspace-field-title">
                      {field.field_name === "serial_number" && serialCandidates.length > 1 ? "Serie para vincular" : documentFieldLabel(field.field_name)}
                    </div>

                    <div className="workspace-field-original">
                      <div>
                        <strong>Valor original:</strong>
                      </div>

                      <div>{field.raw_value}</div>
                    </div>

                    <label
                      htmlFor={`field-${field.field_id}`}
                      className="workspace-form-label"
                    >
                      Valor revisado · {documentFieldLabel(field.field_name)}
                    </label>

                    <div className="workspace-field-controls">
                      {field.field_name === "serial_number" && serialCandidates.length > 1 ? (
                        <select id={`field-${field.field_id}`} value={field.normalized_value ?? ""}
                          onChange={(event) => updateNormalizedValue(field.field_id, event.target.value)}
                          disabled={loading || isMaterialized}>
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
                      />}

                      <button
                        type="button"
                        onClick={() => saveField(field)}
                        disabled={loading || isMaterialized}
                      >
                        Guardar corrección
                      </button>
                    </div>

                    <div className="workspace-field-check">
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
            </section>
          )}
        </section>
      )}

      {activeTab === "audit" && (
        <section>

          {auditingDocument ? <>
            <nav className="document-review-controls" aria-label="Acciones del documento">
              <Link to={`/documents/${initialAudit}/original${originalQuery}`}>Abrir original</Link>
              <Link to={`/?tab=review&documentId=${initialAudit}${passportQuery}`}>Revisar campos</Link>
            </nav>
          </> : !auditingPassport && <>
          <p>
            Consulta el historial de eventos y correcciones, ordenado del más reciente al más antiguo.
          </p>

          <InstrumentFinder apiBaseUrl={API_BASE_URL} mode="audit" />
          <DocumentFinder apiBaseUrl={API_BASE_URL} mode="audit" />
          <details className="workspace-advanced">
            <summary>Consultar por ID (avanzado)</summary>
          <form
            onSubmit={queryAudit}
            className="workspace-inline-form"
          >
            <div className="workspace-form-field">
              <label
                htmlFor="audit-entity-type"
                className="workspace-form-label"
              >
                Buscar por
              </label>

              <select
                id="audit-entity-type"
                value={auditEntityType}
                onChange={(event) =>
                  setAuditEntityType(event.target.value)
                }
              >
                <option value="document">ID de documento</option>
                <option value="instrument">ID de instrumento</option>
              </select>
            </div>

            <div className="workspace-form-field">
              <label
                htmlFor="audit-entity-id"
                className="workspace-form-label"
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
          </>}

          {auditMessage && (
            <p className="workspace-note">{auditMessage}</p>
          )}
          {(auditingDocument || auditingPassport) && auditLoading && <p role="status">Cargando auditoría…</p>}

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
    </AppShell>
  );
}


function Workspace() {
  const location = useLocation();
  return <App key={location.pathname + location.search} />;
}

const router = createBrowserRouter([
  { path: "/documents/:documentId/original", element: <DocumentOriginal apiBaseUrl={API_BASE_URL} /> },
  { path: "/passport/:publicId", element: <Passport key="passport" apiBaseUrl={API_BASE_URL} /> },
  { path: "/passport/:publicId/plano", element: <Passport key="location-plan" apiBaseUrl={API_BASE_URL} planOnly /> },
  { path: "*", element: <Workspace /> },
]);

ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
