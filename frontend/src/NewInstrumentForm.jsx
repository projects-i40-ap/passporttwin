import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const EMPTY = {
  instrument_type_id: "",
  serial_number: "",
  manufacturer: "",
  model: "",
  technical_name: "",
  plant_tag: "",
  location: "",
  criticality: "MEDIUM",
  installed_at: "",
};

export default function NewInstrumentForm({ apiBaseUrl }) {
  const base = apiBaseUrl.replace(/\/$/, "");
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [serialState, setSerialState] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [csv, setCsv] = useState({ file: null, result: null, error: "" });

  useEffect(() => {
    if (!open) return;
    fetch(`${base}/api/v1/instruments/types`)
      .then(response => (response.ok ? response.json() : []))
      .then(setTypes)
      .catch(() => setTypes([]));
  }, [open, base]);

  function update(name, value) {
    setForm(current => {
      const next = { ...current, [name]: value };
      if (name === "instrument_type_id") {
        const type = types.find(item => String(item.id) === String(value));
        if (type) {
          next.manufacturer = type.manufacturer || next.manufacturer;
          next.model = type.model || next.model;
          if (!next.technical_name) next.technical_name = type.model || "";
        }
      }
      return next;
    });
  }

  async function checkSerial(value) {
    if (!value.trim()) {
      setSerialState(null);
      return;
    }
    try {
      const response = await fetch(
        `${base}/api/v1/instruments/check-serial?serial=${encodeURIComponent(value.trim())}`,
      );
      setSerialState(await response.json());
    } catch {
      setSerialState(null);
    }
  }

  async function submit(event) {
    event.preventDefault();
    const serial = form.serial_number.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9_-]{1,39}$/.test(serial)) {
      setError("Número de serie no válido. Usa letras, números, guion y guion bajo (2–40).");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const body = { ...form, serial_number: serial, instrument_type_id: Number(form.instrument_type_id) };
      Object.keys(body).forEach(key => {
        if (body[key] === "" || body[key] === null) delete body[key];
      });
      const response = await fetch(`${base}/api/v1/instruments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "No se pudo crear el dispositivo.");
      setForm(EMPTY);
      setSerialState(null);
      navigate(`/passport/${data.public_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function importCsv(event) {
    event.preventDefault();
    if (!csv.file) return;
    const body = new FormData();
    body.append("file", csv.file);
    setCsv(current => ({ ...current, error: "" }));
    try {
      const response = await fetch(`${base}/api/v1/instruments/upload-csv`, { method: "POST", body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "No se pudo importar el CSV.");
      setCsv({ file: null, result: data, error: "" });
    } catch (err) {
      setCsv(current => ({ ...current, error: err.message }));
    }
  }

  return (
    <section className="workspace-panel" aria-labelledby="new-instrument-heading">
      <h2 id="new-instrument-heading">Nuevo dispositivo</h2>
      <p>
        Un dispositivo es un ejemplar físico con número de serie. Elige su modelo:
        la ficha técnica y los datos del modelo vienen de ahí.
      </p>

      <button type="button" onClick={() => setOpen(value => !value)} aria-expanded={open}>
        {open ? "Cerrar formulario" : "Añadir dispositivo"}
      </button>

      {open && (
        <form className="instrument-form" onSubmit={submit}>
          <label htmlFor="instrument-type">Modelo</label>
          <select
            id="instrument-type"
            required
            value={form.instrument_type_id}
            onChange={event => update("instrument_type_id", event.target.value)}
          >
            <option value="">Selecciona un modelo</option>
            {types.map(type => (
              <option key={type.id} value={type.id}>
                {[type.manufacturer, type.model].filter(Boolean).join(" ") || type.name}
              </option>
            ))}
          </select>

          <label htmlFor="instrument-serial">Número de serie</label>
          <input
            id="instrument-serial"
            required
            maxLength={40}
            pattern="[A-Za-z0-9][A-Za-z0-9_\-]{1,39}"
            title="Letras, números, guion y guion bajo (2–40 caracteres)"
            placeholder="DS18B20-001"
            value={form.serial_number}
            onChange={event => update("serial_number", event.target.value.toUpperCase())}
            onBlur={event => checkSerial(event.target.value)}
          />
          {serialState?.exists && (
            <p role="alert">
              Ese serial ya está registrado.{" "}
              <a href={`/passport/${serialState.public_id}`}>Abrir su pasaporte</a>
            </p>
          )}

          <label htmlFor="instrument-name">Nombre técnico</label>
          <input
            id="instrument-name"
            placeholder="Sensor de temperatura DS18B20"
            value={form.technical_name}
            onChange={event => update("technical_name", event.target.value)}
          />

          <label htmlFor="instrument-tag">Etiqueta de planta</label>
          <input
            id="instrument-tag"
            placeholder="PT-LAB-01"
            value={form.plant_tag}
            onChange={event => update("plant_tag", event.target.value)}
          />

          <label htmlFor="instrument-manufacturer">Fabricante</label>
          <input
            id="instrument-manufacturer"
            value={form.manufacturer}
            onChange={event => update("manufacturer", event.target.value)}
            placeholder="Se hereda del modelo"
          />

          <label htmlFor="instrument-model">Modelo (texto)</label>
          <input
            id="instrument-model"
            value={form.model}
            onChange={event => update("model", event.target.value)}
            placeholder="DS18B20"
          />

          <label htmlFor="instrument-location">Ubicación</label>
          <input
            id="instrument-location"
            value={form.location}
            onChange={event => update("location", event.target.value)}
            placeholder="Laboratorio Demo"
          />

          <label htmlFor="instrument-criticality">Criticidad</label>
          <select
            id="instrument-criticality"
            value={form.criticality}
            onChange={event => update("criticality", event.target.value)}
          >
            <option value="LOW">Baja</option>
            <option value="MEDIUM">Media</option>
            <option value="HIGH">Alta</option>
            <option value="CRITICAL">Crítica</option>
          </select>

          <label htmlFor="instrument-installed">Fecha de instalación</label>
          <input
            id="instrument-installed"
            type="date"
            value={form.installed_at}
            onChange={event => update("installed_at", event.target.value)}
          />

          {error && <p role="alert">{error}</p>}

          <div className="instrument-form-actions">
            <button type="submit" disabled={saving}>Crear dispositivo</button>
          </div>
        </form>
      )}

      <details className="workspace-advanced">
        <summary>Importar inventario desde CSV</summary>
        <form className="instrument-form" onSubmit={importCsv}>
          <p>
            Columnas mínimas: <code>serial_number</code>, <code>type_name</code>,{" "}
            <code>manufacturer</code>, <code>model</code>.
          </p>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={event => setCsv({ file: event.target.files[0] ?? null, result: null, error: "" })}
          />
          <div className="instrument-form-actions">
            <button type="submit" disabled={!csv.file}>Importar CSV</button>
          </div>
          {csv.error && <p role="alert">{csv.error}</p>}
          {csv.result && (
            <p role="status">
              {csv.result.total_created} dispositivos creados ·{" "}
              {csv.result.skipped_records?.length ?? 0} filas omitidas
            </p>
          )}
        </form>
      </details>
    </section>
  );
}
