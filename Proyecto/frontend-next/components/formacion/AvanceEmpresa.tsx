"use client";

/**
 * HU-26 criterio 2 · Avance formativo de la empresa en el panel de Capacitación.
 *
 * Una fila por dimensión con un medidor SEGMENTADO: cada segmento es un módulo del plan
 * (relleno = completado, rayado = en curso, contorno = sin empezar), así el estado se lee por
 * la forma y no solo por el color. Debajo, el mismo avance por nivel de aprendizaje y cuántas
 * brechas ya tienen la formación hecha (que no es lo mismo que cerradas: eso pide evidencia).
 */
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { ESTADO_MODULO, hrefModulo, hrefRemediacion, porcentajeTexto, resumenAvanceTexto, segmentos } from "@/lib/formacion";
import { slug } from "@/lib/slug";
import type { AvanceFormativoApi, EstadoModulo } from "@/lib/types";

export function MedidorSegmentado({ estados, etiqueta }: { estados: EstadoModulo[]; etiqueta: string }) {
  const hechos = estados.filter((e) => e === "completado").length;
  const enCurso = estados.filter((e) => e === "en_curso").length;
  return (
    <span
      className="segmentos"
      role="img"
      aria-label={`${etiqueta}: ${hechos} de ${estados.length} módulos completados${enCurso ? `, ${enCurso} en curso` : ""}`}
    >
      {estados.map((e, i) => (
        <i key={i} data-estado={e} />
      ))}
    </span>
  );
}

export function AvanceEmpresa({ avance, evaluacionId }: { avance: AvanceFormativoApi; evaluacionId: number | null }) {
  const r = avance.resumen;
  const porDim = avance.por_dimension;
  const pendientesEvidencia = avance.brechas.filter((b) => b.formacion_completada).length;
  // Crítica de diseño: el siguiente paso no puede quedar enterrado en una página larga
  const siguiente =
    avance.modulos.find((m) => m.en_plan && m.estado === "en_curso") ??
    avance.modulos.find((m) => m.en_plan && m.estado === "no_iniciado");

  return (
    <section className="card avance" aria-labelledby="avance-titulo">
      <div className="avance-cabeza">
        <div>
          <h2 className="card-title" id="avance-titulo">Avance de {avance.empresa.razon_social}</h2>
          <p className="avance-frase">{resumenAvanceTexto(r)}</p>
          {siguiente ? (
            <p className="avance-siguiente">
              <Link href={hrefModulo(siguiente.ruta_id, evaluacionId)} className="btn btn-primary btn-sm">
                <Icon name="play" />
                {siguiente.estado === "en_curso" ? "Continúa con" : "Empieza por"} {siguiente.nombre}
              </Link>
              <span className="card-sub">
                {siguiente.estado === "en_curso"
                  ? `${siguiente.lecciones_vistas} de ${siguiente.lecciones_total} lecciones vistas`
                  : "El módulo más urgente que aún no empiezas"}
              </span>
            </p>
          ) : null}
        </div>
        <dl className="avance-cifras">
          <div>
            <dt>Horas completadas</dt>
            <dd>
              {r.horas_completadas}
              <small> de {r.horas_total} h</small>
            </dd>
          </div>
          <div>
            <dt>Brechas con formación hecha</dt>
            <dd>
              {r.brechas_con_formacion}
              <small> de {r.brechas_total}</small>
            </dd>
          </div>
        </dl>
      </div>

      <table className="avance-tabla">
        <caption className="sr-only">Avance por dimensión normativa</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Dimensión</th>
            <th scope="col">Módulos</th>
            <th scope="col">Completados</th>
          </tr>
        </thead>
        <tbody>
          {porDim.map((d) => {
            const estados = segmentos(avance.modulos.filter((m) => m.dominio === d.dominio));
            return (
              <tr key={d.dominio}>
                <th scope="row" className="avance-dim">
                  <a href={`#cap-${slug(d.dominio)}`}>{d.dominio}</a>
                </th>
                <td>
                  <MedidorSegmentado estados={estados} etiqueta={d.dominio} />
                </td>
                <td className="avance-num">
                  <strong>{d.completados}</strong>/{d.total}
                  <span className="avance-pct">{porcentajeTexto(d.porcentaje)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="avance-pie">
        <ul className="avance-niveles" aria-label="Avance por nivel">
          {avance.por_nivel.map((n) => (
            <li key={n.nivel}>
              <span className="nivel-chip" data-nivel={n.nivel}>{n.nivel}</span>
              <span>
                <strong>{n.completados}</strong> de {n.total} · {porcentajeTexto(n.porcentaje)}
              </span>
            </li>
          ))}
        </ul>
        <p className="avance-leyenda" aria-hidden="true">
          {(["completado", "en_curso", "no_iniciado"] as const).map((e) => (
            <span key={e}>
              <i data-estado={e} />
              {ESTADO_MODULO[e].etiqueta}
            </span>
          ))}
        </p>
      </div>

      {pendientesEvidencia > 0 ? (
        <p className="callout">
          <Icon name="subir" />
          <span>
            <strong>
              {pendientesEvidencia} {pendientesEvidencia === 1 ? "brecha tiene" : "brechas tienen"} la formación hecha.
            </strong>{" "}
            El puntaje no cambia por completar módulos: para cerrarlas, sube la evidencia de que el control ya se aplica.{" "}
            <Link href={hrefRemediacion(evaluacionId)}>Cerrar brechas con evidencia</Link>
          </span>
        </p>
      ) : null}
    </section>
  );
}
