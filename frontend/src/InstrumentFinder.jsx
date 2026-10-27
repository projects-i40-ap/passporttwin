import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export default function InstrumentFinder({ apiBaseUrl }) {
  const [instruments, setInstruments] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/v1/instruments`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(setInstruments).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [apiBaseUrl]);
  const matches = instruments.filter(i => `${i.serial_number} ${i.location || ""}`.toLowerCase().includes(query.toLowerCase()));
  return <section aria-labelledby="finder"><h2 id="finder">Buscar un pasaporte</h2>
    <label htmlFor="passport-search">Número de serie o ubicación</label>{" "}
    <input id="passport-search" value={query} onChange={event => setQuery(event.target.value)} />
    {error ? <p>No se ha podido cargar el inventario.</p> : <ul>{matches.slice(0, 20).map(i =>
      <li key={i.public_id}><Link to={`/passport/${i.public_id}`}>{i.serial_number}</Link> · {i.location || "Sin ubicación"}</li>)}</ul>}
    {!error && !matches.length && <p>No hay instrumentos que coincidan.</p>}
    {matches.length > 20 && <p>Se muestran 20 resultados. Afina la búsqueda para encontrar el instrumento.</p>}
    {import.meta.env.VITE_METABASE_DASHBOARD_URL && <a href={import.meta.env.VITE_METABASE_DASHBOARD_URL}>Abrir dashboard de flota</a>}
  </section>;
}
