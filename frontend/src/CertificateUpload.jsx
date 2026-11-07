import React, { useState } from "react";
import { Link } from "react-router-dom";

export default function CertificateUpload({ apiBaseUrl, onUploaded }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [uploaded, setUploaded] = useState(null);

  async function upload(event) {
    event.preventDefault();
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith(".pdf") || !file.size) {
      setError("Selecciona un archivo PDF que no esté vacío.");
      return;
    }

    const form = event.currentTarget;
    const body = new FormData();
    body.append("file", file);
    setUploading(true);
    setError("");
    setUploaded(null);
    try {
      const response = await fetch(
        apiBaseUrl.replace(/\/$/, "") + "/api/v1/documents/upload?doc_type=CERTIFICATE",
        { method: "POST", body },
      );
      if (response.status === 409) {
        setError("Este PDF ya está registrado. Búscalo por nombre en la lista de documentos.");
        return;
      }
      if (!response.ok) throw new Error();
      const result = await response.json();
      setUploaded({ id: result.document_id, name: file.name });
      setFile(null);
      form.reset();
      onUploaded();
    } catch {
      setError("No se pudo subir el certificado. Vuelve a intentarlo.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <section aria-labelledby="certificate-upload-heading">
      <h3 id="certificate-upload-heading">Subir certificado PDF</h3>
      <form onSubmit={upload}>
        <label htmlFor="certificate-file">Archivo PDF</label>{" "}
        <input
          id="certificate-file"
          type="file"
          accept=".pdf,application/pdf"
          disabled={uploading}
          onChange={event => {
            setFile(event.target.files[0] ?? null);
            setError("");
          }}
        />
        <button type="submit" disabled={!file || uploading}>Subir certificado</button>
      </form>
      {uploading && <p role="status">Subiendo certificado…</p>}
      {error && <p role="alert">{error}</p>}
      {uploaded && (
        <p role="status">
          <Link to={"/?tab=review&documentId=" + uploaded.id}>{uploaded.name}</Link>
          {" · Recibido, pendiente de procesar."}
        </p>
      )}
    </section>
  );
}
