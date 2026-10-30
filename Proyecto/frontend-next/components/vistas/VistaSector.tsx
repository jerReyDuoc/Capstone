"use client";

import Link from "next/link";
import { AvisoCohorte } from "@/components/sector/AvisoCohorte";
import { LeyendaSector, TiraSector } from "@/components/sector/TiraSector";
import s from "@/components/sector/sector.module.css";
import { PageHeader } from "@/components/shell/PageHeader";
import { EstadoPanel } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { formatoPuntaje } from "@/lib/madurez";
import {
  ETIQUETA_POSICION,
  TEXTO_POSICION,
  formatoPuntos,
  ordenarParaComparar,
  tonoPosicion,
} from "@/lib/sector";
import type { PanelVista } from "@/lib/types";

/**
 * HU-10 · Comparativa de madurez contra el sector, con k-anonimato.
 *
 * 1. Puntaje general frente al sector (criterio 1).
 * 2. Advertencia si la cohorte tiene menos de k empresas (criterio 3); las métricas ya
 *    vienen suprimidas desde el backend (criterio 2) y aquí se dibujan como "ocultas".
 * 3. Cada dimensión en su tira, ordenadas de mayor a menor distancia bajo el sector.
 * 4. Cómo protegemos a las empresas del sector (las reglas, en lenguaje simple).
 */
export function VistaSector() {
  const { href } = usePanel();
  return (
    <>
      <PageHeader
        eyebrow="Comparativa sectorial"
        titulo="Tu sector"
        subtitulo="Compara la madurez de tu empresa con la de otras empresas de tu rubro. Si el grupo es pequeño, ocultamos sus datos para que nadie pueda deducir el resultado de una empresa en particular."
      />
      <EstadoPanel>
        {(p) => (
          <>
            {/* Criterio 3: la advertencia va antes que los números, para leerlos con ese contexto */}
            <AvisoCohorte panel={p} />
            <ResumenSector panel={p} />
            <PorDimension panel={p} hrefDominios={href("/panel/dominios")} />
            <ComoProtegemos k={p.sector?.kMinimo ?? p.muestrasMinimas} />
          </>
        )}
      </EstadoPanel>
    </>
  );
}

function ResumenSector({ panel: p }: { panel: PanelVista }) {
  const sec = p.sector;
  const k = sec?.kMinimo ?? p.muestrasMinimas;
  const tu = sec?.tuPuntaje ?? p.puntajeGeneral;
  const visible = !!sec?.cohorteSuficiente && sec.promedio != null;
  const tono = tonoPosicion(sec?.posicion ?? null);
  const rubro = sec?.rubro ?? (p.sinRubro ? "Sin sector asociado" : "Tu sector");

  return (
    <section className={`card ${s.resumen}`} aria-labelledby="sector-titulo">
      <div className={s.resumenHead}>
        <div>
          <h2 className={s.rubro} id="sector-titulo">
            {rubro}
          </h2>
          <p className={s.frase}>
            {visible && sec?.posicion ? (
              <>
                <strong>{TEXTO_POSICION[sec.posicion]}</strong> Tu puntaje general es {formatoPuntaje(tu)} y el promedio
                de tu sector, {sec.promedio}.
              </>
            ) : p.sinRubro ? (
              <>Tu puntaje general es {formatoPuntaje(tu)}. Sin un sector asociado, lo comparamos solo con la meta.</>
            ) : (
              <>
                Tu puntaje general es {formatoPuntaje(tu)}. El promedio de tu sector se mostrará cuando haya al menos {k}{" "}
                empresas evaluadas.
              </>
            )}
          </p>
        </div>
        {p.sinRubro ? null : visible ? (
          <span className={`${s.cohorte} ${s.cohorteOk}`}>
            <Icon name="escudo" />
            {sec?.empresas} empresas en la comparación
          </span>
        ) : (
          <span className={`${s.cohorte} ${s.cohorteOculta}`}>
            <Icon name="candado" />
            Grupo de menos de {k} empresas
          </span>
        )}
      </div>

      <TiraSector
        nombre="Puntaje general"
        puntaje={tu}
        promedio={visible ? sec!.promedio : null}
        p25={visible ? sec!.p25 : null}
        p75={visible ? sec!.p75 : null}
        meta={p.meta}
        k={k}
        grande
        conEscala
      />
      <LeyendaSector conSector={visible} conBanda={visible && sec!.p25 != null} conMeta conOculta={!visible && !p.sinRubro} />

      <dl className={s.cifras}>
        <div>
          <dt>Tu empresa</dt>
          <dd>
            {formatoPuntaje(tu)}
            <small>/ 100</small>
          </dd>
        </div>
        <div>
          <dt>Promedio del sector</dt>
          <dd className={visible ? undefined : s.vacio}>{visible ? sec!.promedio : "Oculto"}</dd>
        </div>
        <div>
          <dt>Diferencia</dt>
          <dd className={visible && tono ? s[tono] : s.vacio}>{visible ? formatoPuntos(sec!.diferencia) : "—"}</dd>
        </div>
        <div>
          <dt>Mitad central del sector</dt>
          <dd className={visible && sec!.p25 != null ? undefined : s.vacio}>
            {visible && sec!.p25 != null && sec!.p75 != null ? `${sec!.p25}–${sec!.p75}` : "No disponible"}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function PorDimension({ panel: p, hrefDominios }: { panel: PanelVista; hrefDominios: string }) {
  const k = p.sector?.kMinimo ?? p.muestrasMinimas;
  const dominios = ordenarParaComparar(p.dominios);
  const conBanda = dominios.some((d) => d.p25Industria != null);
  const conOculta = dominios.some((d) => !d.cohorteSuficiente);
  const conSector = dominios.some((d) => d.cohorteSuficiente);

  return (
    <section className="card" aria-labelledby="dim-titulo">
      <div className="card-head">
        <div>
          <h2 className="card-title" id="dim-titulo">
            Por dimensión
          </h2>
          <p className="card-sub">Primero las dimensiones donde más te alejas por debajo del sector.</p>
        </div>
        <Link href={hrefDominios} className="btn btn-ghost btn-sm">
          Ver detalle de dominios
          <Icon name="flecha" />
        </Link>
      </div>
      <LeyendaSector conSector={conSector} conBanda={conBanda} conMeta conOculta={conOculta} />

      <ul className={s.filas}>
        {dominios.map((d) => {
          const tono = tonoPosicion(d.posicion);
          return (
            <li key={d.nombre} className={s.fila}>
              <p className={s.nombre}>
                {d.nombre}
                <span>{d.posicion ? ETIQUETA_POSICION[d.posicion] : d.cohorteSuficiente ? "Con comparación" : "Sin comparación"}</span>
              </p>
              <TiraSector
                nombre={d.nombre}
                puntaje={d.puntaje}
                promedio={d.promedioIndustria}
                p25={d.p25Industria}
                p75={d.p75Industria}
                meta={d.meta}
                k={k}
              />
              <dl className={s.valores}>
                <div>
                  <dt>Tú</dt>
                  <dd>{formatoPuntaje(d.puntaje)}</dd>
                </div>
                <div>
                  <dt>Sector</dt>
                  <dd className={d.promedioIndustria == null ? s.vacio : undefined}>
                    {d.promedioIndustria ?? "Oculto"}
                  </dd>
                </div>
                <div>
                  <dt>Diferencia</dt>
                  <dd className={tono ? s[tono] : s.vacio}>{formatoPuntos(d.diferencia)}</dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ComoProtegemos({ k }: { k: number }) {
  return (
    <details className={`card ${s.proteccion}`}>
      <summary>
        <Icon name="escudo" />
        Cómo protegemos a las empresas de tu sector
      </summary>
      <ul className={s.reglas}>
        <li>
          <strong>Solo grupos de {k} empresas o más</strong>
          Si en tu sector, o en una dimensión, hay menos de {k} empresas evaluadas, no mostramos su promedio ni
          cuántas son.
        </li>
        <li>
          <strong>Contamos empresas, no evaluaciones</strong>
          Una empresa que se evalúa varias veces aparece una sola vez, con su evaluación más reciente.
        </li>
        <li>
          <strong>Nada que apunte a una empresa</strong>
          No mostramos el puntaje más alto ni el más bajo del sector, porque cada uno pertenece a una sola empresa.
          La mitad central solo aparece con grupos grandes.
        </li>
        <li>
          <strong>Promedios redondeados</strong>
          Mostramos el promedio en números enteros para que no se pueda despejar el resultado de una empresa
          comparando dos fechas.
        </li>
      </ul>
    </details>
  );
}
