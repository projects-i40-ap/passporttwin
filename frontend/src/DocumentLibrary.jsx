import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { statusLabel } from "./presentation";

const TYPE_LABELS = {
  PDF_CERTIFICATE: "Certificado",
  PDF_DATASHEET: "Ficha técnica",
  INVENTORY_CSV: "Inventario CSV",
  MAINTENANCE_CSV: "Mantenimiento CSV",
};

const PAGE_SIZE = 20;

function formatDate(value) {
  if (!value) return "—";
  const normalized = /(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
}

export default function DocumentLibrary({ apiBaseUrl }) {
  const base = apiBaseUrl.replace(/\/$/, "");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [items, setItems] = useState([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load(nextOffset, term, append) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        q: term,
        limit: String(PAGE_SIZE),
        offset: String(nextOffset),
      });
      const response = await fetch(`${base}/api/v1/documents?${params.toString()}`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      setItems(current => (append ? [...current, ...data.items] : data.items));
      setOffset(nextOffset + data.items.length);
      setHasMore(data.has_more);
    } catch {
      setError("No se pudo cargar la biblioteca de documentos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(0, "", false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function search(event) {
    event.preventDefault();
    setAppliedQuery(query);
    setNotice("");
    load(0, query, false);
  }

  async function remove(item) {
    const confirmed = window.confirm(
      `¿Eliminar "${item.original_filename}"?\n\nSe borrarán sus campos extraídos y el archivo original. ` +
      "Los documentos que sostienen una calibración no se pueden eliminar.",
    );
    if (!confirmed) return;

    setError("");
    setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/documents/${item.id}`, { method: "DELETE" });
      if (response.status === 409) {
        const data = await response.json().catch(() => ({}));
        setError(data.detail || "El documento no puede eliminarse.");
        return;
      }
      if (!response.ok) throw new Error();
      setItems(current => current.filter(row => row.id !== item.id));
      setNotice(`Documento «${item.original_filename}» eliminado.`);
    } catch {
      setError("No se pudo eliminar el documento.");
    }
  }

  return (
    <section className="workspace-panel" aria-labelledby="document-library-heading">
      <h2 id="document-library-heading">Todos los documentos</h2>
      <p>
        Todos los documentos registrados: certificados, fichas técnicas e inventarios.
        Desde aquí puedes abrir su revisión o eliminar los que aún no sostienen una calibración.
      </p>

      <form className="workspace-search" onSubmit={search}>
        <label htmlFor="document-search">Buscar por nombre, serie o ubicación</label>
        <input
          id="document-search"
          type="search"
          value={query}
          maxLength={200}
          onChange={event => setQuery(event.target.value)}
          placeholder="p. ej. wika, PTWIN-DEMO o Laboratorio Demo"
        />
        <button type="submit" disabled={loading}>Buscar</button>
      </form>

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading && <p role="status">Cargando documentos…</p>}

      {!loading && items.length === 0 && (
        <p>{appliedQuery ? "Ningún documento coincide con la búsqueda." : "Todavía no hay documentos registrados."}</p>
      )}

      {items.length > 0 && (
        <div className="document-library-table" role="region" aria-label="Documentos registrados" tabIndex={-1}>
          <table>
            <thead>
              <tr>
                <th scope="col">Archivo</th>
                <th scope="col">Tipo</th>
                <th scope="col">Estado</th>
                <th scope="col">Instrumento</th>
                <th scope="col">Subido</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id}>
                  <td>
                    <Link to={`/?tab=review&documentId=${item.id}#selected-document`}>
                      {item.original_filename}
                    </Link>
                  </td>
                  <td>{TYPE_LABELS[item.source_type] || item.source_type || "—"}</td>
                  <td>
                    <span
                      className="passport-detail-status"
                      data-status={String(item.processing_status).toLowerCase()}
                    >
                      {statusLabel(item.processing_status)}
                    </span>
                  </td>
                  <td>{item.instrument_serial || <span className="document-library-muted">Sin vincular</span>}</td>
                  <td>{formatDate(item.uploaded_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="document-delete"
                      onClick={() => remove(item)}
                      aria-label={`Eliminar ${item.original_filename}`}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && (
        <p>
          <button type="button" disabled={loading} onClick={() => load(offset, appliedQuery, true)}>
            Cargar más documentos
          </button>
        </p>
      )}
    </section>
  );
}
