"use client";

import { useState } from "react";
import { AccionesInforme } from "@/components/informe/AccionesInforme";
import { HojaPortada } from "@/components/informe/HojaPortada";
import s from "@/components/informe/informe.module.css";
import { PageHeader } from "@/components/shell/PageHeader";
import { EstadoPanel } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { useFichaInforme } from "@/hooks/useFichaInforme";
import {
  fechaEvaluacion,
  formatoFechaInforme,
  plural,
  textoSeveridades,
  type FichaInformeApi,
} from "@/lib/informe";

/**
 * HU-21 · Como Director de Riesgos / Representante Legal, quiero descargar el informe del
 * autodiagnóstico en PDF con puntajes por dimensión, brechas priorizadas y rutas recomendadas,
 * para presentar los resultados al directorio o a un auditor.
 *
 *   C1 El PDF se genera con los datos de la API         el botón pide el PDF al servidor; esta
 *                                                        página solo muestra su ficha (no recalcula)
 *   C2 Aviso legal en la portada y en el pie, 5 puntajes, brechas y rutas
 *                                                        facsímil de la portada + "Qué incluye"
 *   C3 Fecha, código de evaluación y versión de la matriz   "Ficha del informe"
 *
 * Diseño: la hoja (página 1 del PDF, con los colores del papel) es el elemento central; todo
 * lo demás es sobrio. En pantallas angostas la acción de descargar va primero.
 */
export function VistaInforme() {
  return (
    <>
      <PageHeader
        eyebrow="Informe para el directorio"
        titulo="Informe del autodiagnóstico"
        subtitulo="Revisa lo que dirá el PDF antes de presentarlo. Lo genera el servidor con los resultados guardados, así cada copia lleva el mismo código y la misma huella de verificación."
      />
      <EstadoPanel>{() => <ContenidoInforme />}</EstadoPanel>
    </>
  );
}

function ContenidoInforme() {
  const { estado, reintentar } = useFichaInforme();
  const [aviso, setAviso] = useState("");

  if (estado.tipo === "cargando") {
    return (
      <div className={s.grid}>
        <div className={`skeleton ${s.esqueletoHoja}`} role="status" aria-label="Preparando la vista previa del informe" />
        <div className="skeleton" style={{ height: 320 }} aria-hidden="true" />
      </div>
    );
  }
  if (estado.tipo === "no-disponible" || estado.tipo === "error") {
    return (
      <div className="callout callout-aviso" role="alert">
        <Icon name="alerta" />
        <div>
          <strong>No pudimos preparar la vista previa del informe.</strong> {estado.mensaje}
          {estado.tipo === "error" ? (
            <p style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={reintentar}>
                <Icon name="refrescar" />
                Reintentar
              </button>
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  const f = estado.ficha;
  return (
    <>
      <p className="sr-only" role="status" aria-live="polite">
        {aviso}
      </p>
      <div className={s.grid}>
        <figure className={s.vistaPrevia} aria-labelledby="hoja-leyenda">
          <HojaPortada ficha={f} />
          <figcaption id="hoja-leyenda" className={s.leyenda}>
            Página 1 del PDF. El aviso legal se repite resumido en el pie de cada página, junto al código y al número de
            página.
          </figcaption>
        </figure>

        <div className={s.lateral}>
          <section className={`card ${s.descarga}`} aria-labelledby="descarga-titulo">
            <h2 className="card-title" id="descarga-titulo">
              Descargar el informe
            </h2>
            <p className="card-sub">
              Un PDF listo para imprimir o adjuntar al acta. Se descarga directo, sin pasar por la impresión del
              navegador.
            </p>
            <div className={s.acciones}>
              <AccionesInforme evaluacionId={f.evaluacion_id} tamano="md" onAviso={setAviso} />
            </div>
            <p className={s.avisoVisible} aria-hidden="true">
              {aviso}
            </p>
          </section>

          <FichaDelInforme ficha={f} onAviso={setAviso} />
          <QueIncluye ficha={f} />
        </div>
      </div>

      <Verificacion ficha={f} onAviso={setAviso} />
    </>
  );
}

/* ------------------------------------------------------------------ criterio 3 */
function FichaDelInforme({ ficha: f, onAviso }: { ficha: FichaInformeApi; onAviso: (t: string) => void }) {
  return (
    <section className="card" aria-labelledby="ficha-titulo">
      <h2 className="card-title" id="ficha-titulo">
        Ficha del informe
      </h2>
      <dl className={s.ficha}>
        <div className={s.fichaFila}>
          <dt>Código de evaluación</dt>
          <dd className={s.fichaCodigo}>
            <span>{f.codigo}</span>
            <BotonCopiar valor={f.codigo} etiqueta="Copiar código de evaluación" hecho="Código copiado." onAviso={onAviso} />
          </dd>
        </div>
        <div className={s.fichaFila}>
          <dt>Fecha de la evaluación</dt>
          <dd>{fechaEvaluacion(f)}</dd>
        </div>
        <div className={s.fichaFila}>
          <dt>Versión de la matriz</dt>
          <dd>
            {f.version_matriz}
            {f.version_matriz_registrada ? null : (
              <span className={s.nota}>
                Esta evaluación se completó antes de que se registrara la versión. El PDF imprime la vigente hoy y lo aclara.
              </span>
            )}
          </dd>
        </div>
        <div className={s.fichaFila}>
          <dt>Aviso legal</dt>
          <dd>
            Versión {f.aviso_legal.version}
            {f.aviso_legal.aceptado_version ? (
              <span className={s.nota}>
                Aceptado por el encuestado (versión {f.aviso_legal.aceptado_version}
                {f.aviso_legal.aceptado_fecha ? `, ${formatoFechaInforme(f.aviso_legal.aceptado_fecha)}` : ""}).
              </span>
            ) : null}
          </dd>
        </div>
        {f.rubro ? (
          <div className={s.fichaFila}>
            <dt>Rubro</dt>
            <dd>{f.rubro}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

/* ------------------------------------------------------------------ criterio 2 */
function QueIncluye({ ficha: f }: { ficha: FichaInformeApi }) {
  const severidades = textoSeveridades(f.brechas.por_severidad);
  const sinAplicables = f.puntajes.filter((p) => !p.global && p.puntaje == null).length;
  const items: { titulo: string; detalle: string }[] = [
    {
      titulo: "Aviso legal en la portada y en el pie de cada página",
      detalle: "Deja claro que es un autodiagnóstico orientativo y no una certificación de la Ley N.º 21.719.",
    },
    {
      titulo: "Los 5 puntajes de madurez",
      detalle:
        "Global, Gobernanza de IA, Gestión de Riesgos, Protección de Datos y Uso Responsable, con la meta de cada uno." +
        (sinAplicables ? ` ${plural(sinAplicables, "dimensión aparece", "dimensiones aparecen")} sin preguntas aplicables.` : ""),
    },
    {
      titulo: f.brechas.total ? `${plural(f.brechas.total, "brecha priorizada", "brechas priorizadas")}` : "Brechas priorizadas",
      detalle: f.brechas.total
        ? `Ordenadas por severidad (${severidades}), con la acción sugerida para cada una.`
        : "No se detectaron brechas: todas las prácticas evaluadas se cumplen.",
    },
    {
      titulo: f.rutas.modulos
        ? `Rutas recomendadas: ${plural(f.rutas.modulos, "módulo", "módulos")}, ${plural(f.rutas.horas, "hora", "horas")}`
        : "Rutas recomendadas",
      detalle: "El plan formativo por dimensión, con el nivel asignado (Inicial, Intermedio o Avanzado).",
    },
  ];
  return (
    <section className="card" aria-labelledby="incluye-titulo">
      <h2 className="card-title" id="incluye-titulo">
        Qué incluye
      </h2>
      <ul className={s.incluye}>
        {items.map((it) => (
          <li key={it.titulo}>
            <Icon name="check" aria-hidden="true" />
            <div>
              <strong>{it.titulo}</strong>
              <span>{it.detalle}</span>
            </div>
          </li>
        ))}
      </ul>
      {f.en_revision ? (
        <p className={s.nota}>
          {plural(f.en_revision, "pregunta sigue", "preguntas siguen")} en revisión y todavía no suma puntaje. El informe lo
          indica.
        </p>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ auditor */
function Verificacion({ ficha: f, onAviso }: { ficha: FichaInformeApi; onAviso: (t: string) => void }) {
  return (
    <section className={`card ${s.verificacion}`} aria-labelledby="verif-titulo">
      <div>
        <h2 className="card-title" id="verif-titulo">
          Si se lo presenta a un auditor
        </h2>
        <p className={s.verifTexto}>
          El PDF termina con esta huella. Resume los puntajes, las brechas y las rutas de la evaluación, no la fecha de
          descarga: dos copias con la misma huella dicen lo mismo. Si alguien modificara una copia, la huella dejaría de
          coincidir con la que entrega el sistema para este código.
        </p>
      </div>
      <div className={s.huella}>
        <span className={s.huellaEtiqueta}>Huella de los resultados</span>
        <span className={s.huellaValor} translate="no">
          {f.huella_corta}
        </span>
        <BotonCopiar valor={f.huella} etiqueta="Copiar huella completa" hecho="Huella completa copiada." onAviso={onAviso} texto="Copiar huella" />
      </div>
    </section>
  );
}

function BotonCopiar({
  valor,
  etiqueta,
  hecho,
  onAviso,
  texto,
}: {
  valor: string;
  etiqueta: string;
  hecho: string;
  onAviso: (t: string) => void;
  texto?: string;
}) {
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(valor);
      onAviso(hecho);
    } catch {
      onAviso(`No pudimos copiar. Selecciona el texto y cópialo a mano: ${valor}`);
    }
  };
  return (
    <button type="button" className={`btn btn-ghost btn-sm ${s.copiar}`} onClick={copiar} aria-label={etiqueta}>
      <Icon name="copiar" aria-hidden="true" />
      {texto ? <span>{texto}</span> : null}
    </button>
  );
}
