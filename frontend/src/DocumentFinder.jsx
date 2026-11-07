import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { statusLabel } from "./presentation";

export default function DocumentFinder({ apiBaseUrl, mode, refresh }) {
  const [query, setQuery] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [retry, setRetry] = useState(0);
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState({ loading: true, items: [] });
  const prefix = `document-${mode}`;
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, items: [] });
    const params = new URLSearchParams({ q: query, review_only: reviewOnly, offset, limit: 20 });
    fetch(`${apiBaseUrl.replace(/\/$/, "")}/api/v1/documents?${params}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("No se han podido cargar los documentos. Vuelve a intentarlo.");
        return response.json();
      }).then(data => { if (!controller.signal.aborted) setState(data); })
      .catch(error => { if (!controller.signal.aborted) setState({ items: [], error: "No se han podido cargar los documentos. Vuelve a intentarlo." }); });
    return () => controller.abort();
  }, [apiBaseUrl, query, reviewOnly, offset, retry, refresh]);
  return <section aria-labelledby={`${prefix}-heading`}>
    <h3 id={`${prefix}-heading`}>Buscar un documento</h3>
    <label htmlFor={`${prefix}-search`}>Nombre del documento, serie o ubicación</label>{" "}
    <input id={`${prefix}-search`} maxLength={200} value={query} onChange={event => { setQuery(event.target.value); setOffset(0); }} />
    <p><label><input type="checkbox" checked={reviewOnly} onChange={event => { setReviewOnly(event.target.checked); setOffset(0); }} /> Solo documentos por revisar o con extracción fallida</label></p>
    {state.loading ? <p role="status">Cargando documentos…</p> : state.error ? <div><p role="alert">{state.error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Volver a intentar</button></div> : <>
      {!state.items.length ? <p>No hay documentos que coincidan.</p> : <ul className="document-results">{state.items.map(item => {
        const target = new URLSearchParams(mode === "audit" ? { tab: "audit", entity: "document", id: item.id } : { tab: "review", documentId: item.id });
        if (item.instrument_public_id) target.set("passport", item.instrument_public_id);
        return <li key={item.id}><Link to={`/?${target}`}>{item.original_filename}</Link>
          <span>{item.instrument_serial || "Sin instrumento vinculado"} · {statusLabel(item.processing_status)}</span>
        </li>;
      })}</ul>}
      <div className="workspace-pages">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Documentos anteriores</button>
        <button type="button" disabled={!state.has_more} onClick={() => setOffset(value => value + 20)}>Más documentos</button>
      </div>
    </>}
  </section>;
}
