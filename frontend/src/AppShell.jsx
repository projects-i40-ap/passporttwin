import React from "react";
import { Link } from "react-router-dom";
import "./passport.css";

export default function AppShell({ active, auditHref = "/?tab=audit", children }) {
  const fleetUrl = import.meta.env.VITE_METABASE_DASHBOARD_URL;
  return <div className="passport-layout">
    <nav className="passport-sidebar" aria-label="Navegación general">
      <strong className="passport-brand">
        <span className="passport-brand-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <rect x="5" y="3" width="14" height="18" rx="2" />
            <path d="M3 8h4m-4 4h4m-4 4h4m3-3 2 2 4-4" />
          </svg>
        </span>
        PassportTwin
      </strong>
      <Link to="/" aria-current={active === "home" ? "page" : undefined}>Inicio</Link>
      <Link to="/?tab=inventory" aria-current={active === "inventory" ? "page" : undefined}>Inventario</Link>
      <Link to="/?tab=review" aria-current={active === "review" ? "page" : undefined}>Revisión documental</Link>
      <Link to="/?tab=documents" aria-current={active === "documents" ? "page" : undefined}>Documentos</Link>
      <Link to={auditHref} aria-current={active === "audit" ? "page" : undefined}>Auditoría</Link>
      {fleetUrl && <a href={fleetUrl}>Flota</a>}
    </nav>
    {children}
  </div>;
}
