import React, { useEffect, useState } from "react";

export default function DocumentTypeLink({ documentId, apiBaseUrl, linkedTypeId, onLinked }) {
  const base = apiBaseUrl.replace(/\/$/, "");
  const [types, setTypes] = useState([]);
  const [selected, setSelected] = useState(linkedTypeId ? String(linkedTypeId) : "");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadTypes() {
    try {
      const response = await fetch(`${base}/api/v1/instruments/types`);
      const data = response.ok ? await response.json() : [];
      setTypes(data);
    } catch {
      setTypes([]);
    }
  }

  useEffect(() => {
    loadTypes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setSelected(linkedTypeId ? String(linkedTypeId) : "");
  }, [linkedTypeId]);

  const linked = types.find(type => String(type.id) === String(selected));

  async function link() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/documents/${documentId}/link-type`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instrument_type_id: Number(selected) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "No se pudo asociar el modelo.");
      setNotice(`Ficha asociada a «${data.instrument_type_name}».`);
      onLinked();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function createFromDocument() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/documents/${documentId}/create-type`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "No se pudo crear el modelo.");
      setNotice(
        data.created
          ? `Modelo «${data.instrument_type.name}» creado y asociado.`
          : `Ya existía el modelo «${data.instrument_type.name}»; se ha asociado.`,
      );
      await loadTypes();
      setSelected(String(data.instrument_type.id));
      onLinked();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="workspace-panel" aria-labelledby="document-type-heading">
      <h3 id="document-type-heading">Modelo del instrumento</h3>
      <p>
        Esta ficha describe un modelo, no un ejemplar. Asígnala a su modelo para que
        todos los dispositivos de ese modelo compartan la documentación.
      </p>

      <div className="document-review-controls">
        <label htmlFor="document-type-select">Modelo</label>
        <select
          id="document-type-select"
          value={selected}
          onChange={event => setSelected(event.target.value)}
          disabled={busy}
        >
          <option value="">Sin asociar</option>
          {types.map(type => (
            <option key={type.id} value={type.id}>
              {[type.manufacturer, type.model].filter(Boolean).join(" ") || type.name}
            </option>
          ))}
        </select>
        <button type="button" onClick={link} disabled={busy || !selected}>
          Asociar
        </button>
        <button type="button" onClick={createFromDocument} disabled={busy}>
          Crear modelo desde esta ficha
        </button>
      </div>

      {linked && (
        <p className="workspace-hint">
          Modelo actual: {linked.magnitude} · {linked.unit}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
