import React, { useState } from "react";
import { Link } from "react-router-dom";
import { statusLabel } from "./presentation";

const TYPE_LABELS = {
  AUTO: "Automático (detecta el contenido)",
  CERTIFICATE: "Certificado de calibración",
  DATASHEET: "Ficha técnica de sensor",
};

const FINAL_STATES = ["REVIEW_REQUIRED", "ACCEPTED", "FAILED_EXTRACTION"];

export default function CertificateUpload({ apiBaseUrl, onUploaded }) {
  const base = apiBaseUrl.replace(/\/$/, "");
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("AUTO");
  const [phase, setPhase] = useState("idle"); // idle | uploading | processing
  const [error, setError] = useState("");
  const [uploaded, setUploaded] = useState(null);

  async function waitForProcessing(documentId) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 3000));
      try {
        const response = await fetch(`${base}/api/v1/documents/${documentId}/fields`);
        if (!response.ok) continue;
        const data = await response.json();
        if (FINAL_STATES.includes(data.processing_status)) {
          return data.processing_status;
        }
      } catch {
        // Reintento silencioso: el documento ya está guardado.
      }
    }
    return "PROCESSING";
  }

  async function upload(event) {
    event.preventDefault();
    if (!file || phase !== "idle") return;
    if (!file.name.toLowerCase().endsWith(".pdf") || !file.size) {
      setError("Selecciona un archivo PDF que no esté vacío.");
      return;
    }

    const form = event.currentTarget;
    const body = new FormData();
    body.append("file", file);
    body.append("doc_type", docType);
    setPhase("uploading");
    setError("");
    setUploaded(null);

    try {
      const response = await fetch(`${base}/api/v1/documents/upload?doc_type=${docType}`, {
        method: "POST",
        body,
      });
      if (response.status === 409) {
        setError("Este PDF ya está registrado. Búscalo por nombre en la lista de documentos.");
        return;
      }
      if (!response.ok) throw new Error();

      const result = await response.json();
      const name = file.name;
      setFile(null);
      form.reset();
      onUploaded();
      setPhase("processing");
      setUploaded({ id: result.document_id, name, sourceType: result.source_type, status: result.status });

      const finalStatus = await waitForProcessing(result.document_id);
      setUploaded({ id: result.document_id, name, sourceType: result.source_type, status: finalStatus });
      onUploaded();
    } catch {
      setError("No se pudo subir el documento. Vuelve a intentarlo.");
    } finally {
      setPhase("idle");
    }
  }

  const busy = phase !== "idle";

  return (
    <section className="workspace-panel" aria-labelledby="certificate-upload-heading">
      <h3 id="certificate-upload-heading">Subir documento PDF</h3>
      <form className="workspace-upload" onSubmit={upload}>
        <label htmlFor="certificate-file">Archivo PDF</label>{" "}
        <input
          id="certificate-file"
          type="file"
          accept=".pdf,application/pdf"
          disabled={busy}
          onChange={event => {
            setFile(event.target.files[0] ?? null);
            setError("");
          }}
        />
        <label htmlFor="document-type">Tipo de documento</label>{" "}
        <select
          id="document-type"
          value={docType}
          disabled={busy}
          onChange={event => setDocType(event.target.value)}
        >
          {Object.entries(TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <button type="submit" disabled={!file || busy}>Subir documento</button>
      </form>

      {phase === "uploading" && <p role="status">Subiendo documento…</p>}
      {phase === "processing" && (
        <p role="status">
          Procesando con el modelo local. Puede tardar hasta un minuto; puedes seguir usando la aplicación.
        </p>
      )}
      {error && <p role="alert">{error}</p>}

      {uploaded && (
        <p role="status">
          <Link to={`/?tab=review&documentId=${uploaded.id}#selected-document`}>Abrir {uploaded.name}</Link>
          {" · "}
          {statusLabel(uploaded.status)}
          {uploaded.status === "REVIEW_REQUIRED" && " · ya está en la cola de revisión"}
        </p>
      )}
    </section>
  );
}
