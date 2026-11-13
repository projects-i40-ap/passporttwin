import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { statusLabel } from "./presentation";

const apiBaseOf = (apiBaseUrl) => apiBaseUrl.replace(/\/$/, "");

const sourceTypeLabel = (value) => value === "PDF_CERTIFICATE" ? "Certificado"
  : value === "PDF_DATASHEET" ? "Ficha técnica"
  : value === "CSV_MAINTENANCE" ? "Mantenimiento"
  : value || "Documento";

const suggestedQuestions = [
  "¿Qué tolerancia declara cada certificado?",
  "¿Qué documentos siguen pendientes de revisión?",
  "¿Cuál es el próximo vencimiento de calibración?",
  "Resume las especificaciones técnicas disponibles.",
];

function SourceCard({ source }) {
  const fields = Object.entries(source.matched_fields || {})
    .filter(([, value]) => value !== null && value !== "" && value !== undefined);

  return <article className="chat-source">
    <header className="chat-source-header">
      <strong>{source.original_filename || `Documento #${source.document_id}`}</strong>
      <span className="chat-source-meta">
        {sourceTypeLabel(source.source_type)} · #{source.document_id} · {statusLabel(source.processing_status)}
      </span>
    </header>
    {fields.length > 0 && <ul className="chat-source-fields">
      {fields.slice(0, 8).map(([name, value]) => <li key={name}><span>{name}</span> {String(value).slice(0, 80)}</li>)}
    </ul>}
    {source.snippet && <p className="chat-source-snippet">{source.snippet}</p>}
    <nav className="chat-source-links" aria-label={`Acciones del documento ${source.document_id}`}>
      <Link to={`/documents/${source.document_id}/original`}>Abrir original</Link>
      <Link to={`/?tab=review&documentId=${source.document_id}`}>Revisar campos</Link>
    </nav>
  </article>;
}

function Turn({ turn }) {
  const retrievalOnly = turn.retrievalOnly || turn.llm_status !== "ONLINE_GENERATED";

  return <div className="chat-turn">
    <p className="chat-question">{turn.question}</p>

    {turn.error ? <p className="chat-error" role="alert">{turn.error}</p> : <div className="chat-answer">
      <div className="chat-answer-heading">
        <span className="chat-answer-role">Respuesta</span>
        {retrievalOnly
          ? <span className="chat-answer-model" data-offline="true">
              {turn.retrievalOnly ? "Recuperación sin modelo" : "Modelo no disponible · evidencias recuperadas"}
            </span>
          : <span className="chat-answer-model">{turn.model_used || "modelo local"}</span>}
      </div>

      {turn.answer
        ? <p className="chat-answer-text">{turn.answer}</p>
        : <p className="chat-answer-text chat-answer-offline">
            {turn.retrievalOnly
              ? "Has pedido solo la recuperación: estas son las evidencias que PostgreSQL devuelve para la pregunta."
              : "No se ha podido generar texto con el modelo local. Estas son las evidencias que PostgreSQL ha recuperado para la pregunta:"}
            {" "}Revísalas en los documentos citados.
          </p>}

      {turn.sources?.length > 0
        ? <div className="chat-sources">
            <h3>Referencias ({turn.sources.length})</h3>
            {turn.sources.map((source) => <SourceCard key={`${source.document_id}-${source.score}`} source={source} />)}
          </div>
        : <p className="chat-answer-text">No se ha encontrado documentación relacionada con esta pregunta.</p>}
    </div>}
  </div>;
}

export default function DocumentChat({ apiBaseUrl }) {
  const [params] = useSearchParams();
  const apiBase = apiBaseOf(apiBaseUrl);
  const [instruments, setInstruments] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [scope, setScope] = useState(params.get("serial") ? "instrument" : params.get("documentId") ? "document" : "all");
  const [serial, setSerial] = useState(params.get("serial") || "");
  const [documentId, setDocumentId] = useState(params.get("documentId") || "");
  const [question, setQuestion] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loadNote, setLoadNote] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [instrumentsResponse, documentsResponse] = await Promise.all([
          fetch(`${apiBase}/api/v1/instruments`),
          fetch(`${apiBase}/api/v1/documents?q=`),
        ]);
        if (!instrumentsResponse.ok || !documentsResponse.ok) throw new Error();
        const instrumentList = await instrumentsResponse.json();
        const documentPage = await documentsResponse.json();
        if (!active) return;
        setInstruments(Array.isArray(instrumentList) ? instrumentList : []);
        setDocuments(Array.isArray(documentPage?.items) ? documentPage.items : []);
      } catch {
        if (active) setLoadNote("No se han podido cargar los instrumentos o documentos disponibles.");
      }
    }
    load();
    return () => { active = false; };
  }, [apiBase]);

  async function ask(event) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || busy) return;

    const payload = { question: text, top_k: 4, use_llm: useLlm };
    if (scope === "instrument" && serial) payload.serial_number = serial;
    if (scope === "document" && documentId) payload.document_id = Number(documentId);
    const retrievalOnly = !useLlm;

    setBusy(true);
    setQuestion("");

    try {
      const response = await fetch(`${apiBase}/api/v1/documents/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se ha podido consultar la documentación.");
      setTurns((current) => [...current, { id: `${Date.now()}`, question: text, retrievalOnly, ...data }]);
    } catch (error) {
      setTurns((current) => [...current, { id: `${Date.now()}`, question: text, error: error.message }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function askSuggestion(text) {
    setQuestion(text);
    inputRef.current?.focus();
  }

  return <section className="document-chat" aria-labelledby="document-chat-title">
    <p className="document-chat-intro">
      Pregunta en lenguaje natural sobre los documentos ingeridos (certificados, fichas y sus campos extraídos).
      La recuperación se hace sobre PostgreSQL; el modelo local solo redacta la respuesta cuando está disponible y
      siempre se muestran las referencias para que puedas comprobarlas.
    </p>

    <form className="chat-scope" onSubmit={ask}>
      <label>
        Alcance
        <select value={scope} onChange={(event) => setScope(event.target.value)}>
          <option value="all">Toda la documentación</option>
          <option value="instrument">Un instrumento (por número de serie)</option>
          <option value="document">Un documento concreto</option>
        </select>
      </label>

      {scope === "instrument" && <label>
        Instrumento
        <select value={serial} onChange={(event) => setSerial(event.target.value)}>
          <option value="">Selecciona un instrumento…</option>
          {instruments.map((instrument) => <option key={instrument.id} value={instrument.serial_number}>
            {instrument.serial_number} · {instrument.technical_name || instrument.model}
          </option>)}
        </select>
      </label>}

      {scope === "document" && <label>
        Documento
        <select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
          <option value="">Selecciona un documento…</option>
          {documents.map((document) => <option key={document.id} value={document.id}>
            #{document.id} · {document.original_filename} ({statusLabel(document.processing_status)})
          </option>)}
        </select>
      </label>}

      <label className="chat-llm">
        <input type="checkbox" checked={useLlm} onChange={(event) => setUseLlm(event.target.checked)} />
        Redactar con el modelo local (si no responde, se muestran solo las evidencias)
      </label>

      <div className="chat-compose">
        <label htmlFor="chat-question" className="workspace-form-label">Pregunta</label>
        <div className="chat-compose-row">
          <input
            id="chat-question"
            ref={inputRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ej.: ¿qué tolerancia tiene el certificado del DS18B20-001?"
            maxLength={500}
            disabled={busy}
          />
          <button type="submit" disabled={busy || !question.trim()}>Consultar</button>
        </div>
      </div>
    </form>

    <div className="chat-suggestions" aria-label="Preguntas sugeridas">
      {suggestedQuestions.map((text) => <button key={text} type="button" onClick={() => askSuggestion(text)} disabled={busy}>
        {text}
      </button>)}
    </div>

    {loadNote && <p className="chat-error" role="status">{loadNote}</p>}
    {busy && <p role="status">Consultando documentos y evidencias…</p>}

    <div className="chat-log" role="log" aria-live="polite" aria-label="Conversación con la documentación">
      {turns.length === 0 && !busy && <p className="chat-empty">
        Todavía no hay preguntas. Empieza con una sugerencia o escribe la tuya.
      </p>}
      {turns.map((turn) => <Turn key={turn.id} turn={turn} />)}
    </div>

    {turns.length > 0 && <p className="chat-note">
      Cada pregunta se responde con la evidencia vigente en PostgreSQL; el modelo no conserva los turnos anteriores.
    </p>}
  </section>;
}
