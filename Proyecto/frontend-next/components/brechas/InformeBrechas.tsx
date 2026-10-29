import { ETIQUETA_ESTADO_LARGA } from "@/lib/exportar";
import { describirFiltros, type FiltrosBrechas } from "@/lib/filtrosBrechas";
import { formatoPuntaje, NIVELES } from "@/lib/madurez";
import { contarPorSeveridad, SEVERIDAD_TONO, SEVERIDADES } from "@/lib/severidad";
import type { BrechaVista, PanelVista } from "@/lib/types";

/**
 * HU-11 · Informe de brechas para PDF. Solo se ve al imprimir (clase print-only):
 * fondo blanco, colores de severidad para papel y encabezados repetidos en cada página.
 * Recibe las brechas YA filtradas: el PDF exporta exactamente lo que se está viendo.
 */
export function InformeBrechas({
  panel,
  brechas,
  filtros,
  emitido,
}: {
  panel: PanelVista;
  brechas: BrechaVista[];
  filtros: FiltrosBrechas;
  emitido: Date;
}) {
  const conteo = contarPorSeveridad(brechas);
  const niveles = SEVERIDADES.filter((s) => s !== "Sin clasificar" || conteo[s] > 0);
  const fecha = new Intl.DateTimeFormat("es-CL", { dateStyle: "long", timeStyle: "short" }).format(emitido);

  return (
    <article className="print-only" aria-hidden="true">
      <header className="informe-head">
        <div>
          <p className="informe-marca">
            Therion<span>Labs</span> · ComplianceAI
          </p>
          <h1 className="informe-titulo">Informe de brechas normativas priorizadas</h1>
        </div>
        <div className="informe-meta">
          <span>
            Evaluación <strong>#{panel.evaluacionId}</strong>
          </span>
          <span>
            Madurez general <strong>{formatoPuntaje(panel.puntajeGeneral)} / 100</strong> · {NIVELES[panel.nivelGeneral].etiqueta}
          </span>
          <span>Emitido el {fecha}</span>
        </div>
      </header>

      <div className="informe-resumen">
        {niveles.map((s) => (
          <div key={s} className={`sev-${SEVERIDAD_TONO[s]}`}>
            <b>{conteo[s]}</b>
            <span>{s}</span>
          </div>
        ))}
      </div>

      <p className="informe-filtros">
        <strong>Alcance:</strong> {describirFiltros(filtros)} · {brechas.length} de {panel.brechas.length} brechas abiertas ·{" "}
        {panel.controlesEvaluados} preguntas evaluadas
      </p>

      <table className="informe-tabla">
        <thead>
          <tr>
            <th>#</th>
            <th>Severidad</th>
            <th>Brecha detectada</th>
            <th>Dominio</th>
            <th>Estado</th>
            <th>Acción sugerida y ruta formativa</th>
          </tr>
        </thead>
        <tbody>
          {brechas.map((b) => (
            <tr key={b.respuestaId} className={`sev-${SEVERIDAD_TONO[b.severidad]}`}>
              <td>{b.prioridad}</td>
              <td className="informe-sev">{b.severidad}</td>
              <td>{b.descripcion}</td>
              <td>{b.dominio}</td>
              <td>{ETIQUETA_ESTADO_LARGA[b.estado]}</td>
              <td>
                {b.accion ?? "—"}
                {b.rutaFormativa ? <><br />Ruta: {b.rutaFormativa}</> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="informe-pie">
        Severidad = impacto de la brecha × estado de cumplimiento: una práctica de impacto alto no cumplida es
        crítica. Orden dentro de cada severidad: no cumplidas primero, mayor impacto, dominio menos maduro.
        Informe generado automáticamente a partir del autodiagnóstico; no constituye asesoría legal.
      </p>
    </article>
  );
}
