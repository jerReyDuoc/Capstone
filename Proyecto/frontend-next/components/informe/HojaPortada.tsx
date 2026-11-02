import s from "./informe.module.css";
import {
  anchoBarra,
  fechaEvaluacion,
  formatoFechaInforme,
  formatoPuntajeInforme,
  META_INFORME_POR_DEFECTO,
  type FichaInformeApi,
} from "@/lib/informe";

/**
 * HU-21 · Facsímil de la página 1 del PDF, con los colores del papel (no los del panel).
 * Todo sale de la ficha del servidor: es lo que el directorio tendrá en la mano.
 *
 * Accesibilidad: es una <figure> con su leyenda. El texto se puede leer con lector de
 * pantalla, pero las barras son decorativas (el número va al lado), por eso aria-hidden.
 */
export function HojaPortada({ ficha }: { ficha: FichaInformeApi }) {
  const meta = ficha.meta ?? META_INFORME_POR_DEFECTO;
  return (
    <div className={s.hoja} lang="es">
      <div className={s.hojaCuerpo}>
        <p className={s.hojaMarca}>ComplianceIA de Therion Labs</p>
        <p className={s.hojaTitulo}>Informe de autodiagnóstico</p>
        <p className={s.hojaBajada}>
          Puntajes por dimensión, brechas priorizadas y rutas recomendadas
          {ficha.rubro ? ` para una organización del rubro ${ficha.rubro}` : ""}
        </p>

        <dl className={s.hojaFicha}>
          <div>
            <dt>Código de evaluación</dt>
            <dd>{ficha.codigo}</dd>
          </div>
          <div>
            <dt>Fecha de la evaluación</dt>
            <dd>{fechaEvaluacion(ficha)}</dd>
          </div>
          <div>
            <dt>Versión de la matriz</dt>
            <dd>{ficha.version_matriz}</dd>
          </div>
        </dl>

        <div className={s.hojaAviso}>
          <p className={s.hojaAvisoTitulo}>{ficha.aviso_legal.titulo}</p>
          {ficha.aviso_legal.parrafos.map((t) => (
            <p key={t}>{t}</p>
          ))}
          {ficha.aviso_legal.aceptado_version ? (
            <p className={s.hojaGris}>
              El encuestado aceptó el aviso legal versión {ficha.aviso_legal.aceptado_version}
              {ficha.aviso_legal.aceptado_fecha ? ` el ${formatoFechaInforme(ficha.aviso_legal.aceptado_fecha)}` : ""} antes de
              responder.
            </p>
          ) : null}
        </div>

        <p className={s.hojaSeccion}>Puntajes de madurez</p>
        <table className={s.hojaTabla}>
          <caption className="sr-only">Los cinco puntajes de madurez, de 0 a 100. La meta es {meta} puntos.</caption>
          <thead>
            <tr>
              <th scope="col">Dimensión</th>
              <th scope="col">Puntaje</th>
              <th scope="col">Nivel</th>
              <th scope="col" aria-hidden="true">
                <span className="sr-only">Barra</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {ficha.puntajes.map((p) => (
              <tr key={p.nombre} className={p.global ? s.hojaGlobal : undefined}>
                <th scope="row">{p.global ? "Puntaje global" : p.nombre}</th>
                <td className={s.hojaNum}>{formatoPuntajeInforme(p.puntaje)}</td>
                <td>{p.nivel}</td>
                <td aria-hidden="true" className={s.hojaCeldaBarra}>
                  <span className={s.hojaPista}>
                    <span className={s.hojaRelleno} style={{ width: `${anchoBarra(p.puntaje)}%` }} />
                    <span className={s.hojaMeta} style={{ left: `${anchoBarra(meta)}%` }} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={s.hojaPie}>
        <p>{ficha.aviso_legal.pie}</p>
        <p className={s.hojaGris}>
          <span>ComplianceIA | {ficha.codigo}</span>
          <span>Página 1</span>
        </p>
      </div>
    </div>
  );
}
