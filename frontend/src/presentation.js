const statuses = {
  OPERATIONAL: "En servicio", PENDING: "Pendiente", OUT_OF_TOLERANCE: "Fuera de tolerancia",
  BLOCKED: "Bloqueado", RETIRED: "Retirado", SYNCED: "Sincronizado", ERROR: "Error de sincronización",
  HIGH: "Alta", MEDIUM: "Media", LOW: "Baja", CRITICAL: "Crítica", PASS: "Conforme", FAIL: "No conforme",
  ACCEPTED: "Aceptado", RECEIVED: "Recibido", EXTRACTED: "Extraído", VALIDATED: "Validado",
  REVIEW_REQUIRED: "Requiere revisión", FAILED_EXTRACTION: "Extracción fallida", STAGING: "Pendiente de validación",
  REJECTED: "Rechazado", CURRENT: "Vigente", MISSING: "Sin resultado guardado",
  STALE_DATE: "Desactualizado por fecha", STALE_INPUTS: "Desactualizado por cambios en los datos",
};
export const statusLabel = (value) => value ? statuses[String(value).toUpperCase()] || "Sin clasificar" : "Sin datos";
export const dateTimeLabel = (value) => {
  if (!value) return "Sin registro";
  const normalized = /(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(normalized).toLocaleString("es-ES");
};
export const riskAction = (reason) => ({
  INSUFFICIENT_POST_MAINTENANCE_HISTORY: "Registra al menos tres calibraciones con fechas distintas posteriores al último mantenimiento.",
  INSUFFICIENT_HISTORY: "Completa el historial con al menos tres calibraciones de fechas distintas.",
  DUPLICATE_CALIBRATION_DATES: "Revisa las calibraciones que comparten fecha y corrige su asignación.",
  INVALID_CALIBRATION_VALUES: "Revisa los errores y tolerancias: deben ser finitos y la tolerancia positiva.",
  TOLERANCE_CHANGED: "Revisa el cambio de tolerancia antes de comparar el historial.",
})[reason] || "Revisa el historial y el resultado de la validación.";
export function healthActions(details, risk) {
  const actions = [];
  for (const key of details?.missing_components || []) {
    if (key === "calibration_status") actions.push("Completa una calibración válida y su fecha de próximo vencimiento.");
    if (key === "predicted_risk") actions.push(risk?.reason ? riskAction(risk.reason) : "El historial no permite asignar una probabilidad fiable; revisa las calibraciones disponibles.");
    if (key === "recent_incidents") actions.push("Revisa la severidad de las incidencias: baja, media, alta o crítica.");
  }
  for (const [key, valid] of Object.entries(details?.quality_checks || {})) {
    if (valid) continue;
    const action = {serial_number: "Completa el número de serie.", manufacturer: "Completa el fabricante.", model: "Completa el modelo.",
      location: "Completa la ubicación.", valid_metrology: "Revisa los valores y fechas de la última calibración.",
      accepted_documentation: "Vincula documentación y revisa los documentos pendientes antes de aceptarlos."}[key];
    if (action) actions.push(action);
  }
  return [...new Set(actions)];
}
