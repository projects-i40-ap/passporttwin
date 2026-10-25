import React, { useState } from "react";
import ReactDOM from "react-dom/client";


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


/* -------------------------------------------------------------------------
 * Helpers de presentación de la línea temporal de auditoría (RF-AUDIT-08).
 * ---------------------------------------------------------------------- */

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
            <strong>Instrument ID:</strong> {trace.instrument_id}
          </div>

          <div>
            <strong>Serial number:</strong>{" "}
            {trace.serial_number || "—"}
          </div>
        </>
      ) : (
        <>
          <div>
            <strong>Document ID:</strong> {trace.document_id}
          </div>

          <div>
            <strong>Filename:</strong>{" "}
            {trace.original_filename || "—"}
          </div>

          <div>
            <strong>Processing status:</strong>{" "}
            {trace.processing_status || "—"}
          </div>

          <div style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
            <strong>SHA-256:</strong> {trace.sha256_hash || "—"}
          </div>
        </>
      )}

      <div>
        <strong>Total events:</strong> {trace.total_events}
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
  /* Estado de la vista de revisión documental (pestaña "review"). */
  const [activeTab, setActiveTab] = useState("review");
  const [documentId, setDocumentId] = useState("1");
  const [processingStatus, setProcessingStatus] = useState("");
  const [fields, setFields] = useState([]);
  const [rulesFailed, setRulesFailed] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  /* Estado de la vista de auditoría (pestaña "audit"). */
  const [auditEntityType, setAuditEntityType] = useState("document");
  const [auditEntityId, setAuditEntityId] = useState("1");
  const [auditTrace, setAuditTrace] = useState(null);
  const [auditMessage, setAuditMessage] = useState("");
  const [auditLoading, setAuditLoading] = useState(false);

  async function loadDocument() {
    setLoading(true);
    setMessage("");
    setRulesFailed([]);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/documents/${documentId}/fields`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to load document fields."
        );
      }

      setProcessingStatus(data.processing_status);
      setFields(data.fields);
      setMessage("Document loaded.");
    } catch (error) {
      setProcessingStatus("");
      setFields([]);
      setMessage(error.message);
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
        `${API_BASE_URL}/api/v1/documents/${documentId}/fields/${field.field_id}`,
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
          data.detail || "Unable to save field correction."
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

      setMessage(
        `Field "${data.field_name}" saved successfully.`
      );
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
        `${API_BASE_URL}/api/v1/documents/${documentId}/revalidate`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to revalidate document."
        );
      }

      setProcessingStatus(data.processing_status);
      setRulesFailed(data.rules_failed || []);

      if (data.processing_status === "ACCEPTED") {
        setMessage("Document revalidated and accepted.");
      } else {
        setMessage(
          "Document still requires human review."
        );
      }
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
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
          data.detail || "Unable to load the audit trail."
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

      <nav
        aria-label="Application views"
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
          Document Review
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("audit")}
          aria-pressed={activeTab === "audit"}
          style={tabStyle(activeTab === "audit")}
        >
          Audit &amp; Traceability Trail
        </button>
      </nav>

      {activeTab === "review" && (
        <section>
          <h2>Document Review</h2>

          <p>
            Human-in-the-loop review of extracted document fields.
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
              Document ID
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
                Load document
              </button>
            </div>
          </section>

          {processingStatus && (
            <section style={{ marginTop: "24px" }}>
              <strong>Status:</strong>{" "}
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
                {processingStatus}
              </span>
            </section>
          )}

          {message && (
            <p style={{ marginTop: "20px" }}>
              {message}
            </p>
          )}

          {rulesFailed.length > 0 && (
            <section style={{ marginTop: "24px" }}>
              <h3>Validation rules failed</h3>

              <ul>
                {rulesFailed.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </section>
          )}

          {fields.length > 0 && (
            <section style={{ marginTop: "32px" }}>
              <h3>Extracted fields</h3>

              <div
                style={{
                  display: "grid",
                  gap: "16px",
                }}
              >
                {fields.map((field) => (
                  <article
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
                      {field.field_name}
                    </div>

                    <div style={{ marginBottom: "12px" }}>
                      <div>
                        <strong>Raw value:</strong>
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
                      Normalized value
                    </label>

                    <div
                      style={{
                        display: "flex",
                        gap: "12px",
                        alignItems: "center",
                      }}
                    >
                      <input
                        id={`field-${field.field_id}`}
                        type="text"
                        value={field.normalized_value ?? ""}
                        onChange={(event) =>
                          updateNormalizedValue(
                            field.field_id,
                            event.target.value
                          )
                        }
                        style={{
                          flex: 1,
                          padding: "8px",
                        }}
                      />

                      <button
                        type="button"
                        onClick={() => saveField(field)}
                        disabled={loading}
                      >
                        Save correction
                      </button>
                    </div>

                    <div
                      style={{
                        marginTop: "10px",
                        fontSize: "0.9rem",
                      }}
                    >
                      Validation status:{" "}
                      {field.validation_status}
                    </div>
                  </article>
                ))}
              </div>

              <button
                type="button"
                onClick={revalidateDocument}
                disabled={loading}
                style={{
                  marginTop: "24px",
                  padding: "10px 16px",
                }}
              >
                Revalidate document
              </button>
            </section>
          )}
        </section>
      )}

      {activeTab === "audit" && (
        <section>
          <h2>Audit &amp; Traceability Trail</h2>

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
                Search by
              </label>

              <select
                id="audit-entity-type"
                value={auditEntityType}
                onChange={(event) =>
                  setAuditEntityType(event.target.value)
                }
                style={{ padding: "8px", minWidth: "170px" }}
              >
                <option value="document">Document ID</option>
                <option value="instrument">Instrument ID</option>
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
                  ? "Instrument ID"
                  : "Document ID"}
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
              {auditLoading ? "Querying..." : "Query audit trail"}
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
    <App />
  </React.StrictMode>
);
