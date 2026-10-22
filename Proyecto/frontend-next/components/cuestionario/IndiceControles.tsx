"use client";

/**
 * HU-01 · Índice del cuestionario: controles agrupados por dominio con su estado.
 * En escritorio es una columna fija; en pantallas angostas se pliega (details/summary).
 */
import { Icon } from "@/components/ui/Icon";
import type { Cuestionario } from "@/hooks/useCuestionario";
import { ESTADO_POR_VALOR, esEstadoDeclarado } from "@/lib/cuestionario/modelo";
import s from "./cuestionario.module.css";

export function IndiceControles({ c }: { c: Cuestionario }) {
  const grupos = new Map<string, { i: number; id: number; codigo: string }[]>();
  c.controles.forEach((control, i) => {
    const d = control.dominio?.nombre_dominio ?? "Sin dominio";
    if (!grupos.has(d)) grupos.set(d, []);
    grupos.get(d)!.push({ i, id: control.id_control, codigo: control.codigo_control ?? `#${control.id_control}` });
  });
  const enCuestionario = c.fase.tipo === "cuestionario";
  const hechos = c.progreso?.controles_respondidos ?? 0;
  const total = c.progreso?.controles_aplicables ?? c.controles.length;

  const cuerpo = (
    <>
      <p className={s.indiceTitulo}>Controles de tu evaluación</p>
      {[...grupos.entries()].map(([dominio, items]) => {
        const respondidos = items.filter((x) => c.respondidas.has(x.id)).length;
        return (
          <div key={dominio} className={s.grupo}>
            <p className={s.grupoTitulo}>
              <span>{dominio}</span>
              <span>
                {respondidos}/{items.length}
              </span>
            </p>
            <ul className={s.lista}>
              {items.map((x) => {
                const r = c.respondidas.get(x.id);
                const estado = r?.estadoFinal ?? r?.estado ?? null;
                const etiqueta = esEstadoDeclarado(estado) ? ESTADO_POR_VALOR[estado].etiqueta : "Sin responder";
                const actual = enCuestionario && c.indice === x.i;
                return (
                  <li key={x.id}>
                    <button
                      type="button"
                      className={s.item}
                      aria-current={actual ? "step" : undefined}
                      onClick={() => c.irA(x.i)}
                      aria-label={`${x.codigo}: ${etiqueta}`}
                    >
                      <span className={s.punto} data-estado={estado ?? undefined} aria-hidden="true" />
                      {x.codigo}
                      <span className={s.itemEstado} aria-hidden="true">
                        {r ? "" : "pendiente"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        style={{ marginTop: 16, width: "100%" }}
        onClick={() => void c.editarFiltro()}
      >
        <Icon name="refrescar" />
        Cambiar preguntas iniciales
      </button>
    </>
  );

  return (
    <nav className={`card ${s.indice}`} aria-label="Índice de controles">
      <details open className={s.indiceDetalles}>
        <summary className={s.indiceResumen}>
          <span>Índice · {hechos} de {total} respondidos</span>
          <Icon name="lista" width={18} height={18} />
        </summary>
        <div className={s.indiceCuerpo}>{cuerpo}</div>
      </details>
    </nav>
  );
}
