import React, { useState } from "react";
import ReactDOM from "react-dom/client";


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


function App() {
  const [documentId, setDocumentId] = useState("1");
  const [processingStatus, setProcessingStatus] = useState("");
  const [fields, setFields] = useState([]);
  const [rulesFailed, setRulesFailed] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

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

  return (
    <main
      style={{
        fontFamily: "Arial, sans-serif",
        maxWidth: "1000px",
        margin: "0 auto",
        padding: "40px 24px",
      }}
    >
      <h1>PassportTwin</h1>
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
          <span>{processingStatus}</span>
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