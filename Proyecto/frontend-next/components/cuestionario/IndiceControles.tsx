"use client";

/**
 * HU-01 · Índice del cuestionario: las preguntas agrupadas por dominio con su estado.
 *
 * Correcciones 29-10: parte plegado, como una pestaña sobre la pregunta ("Ver todas las
 * preguntas"); quien quiera volver a una pregunta concreta lo despliega. Así la pregunta usa
 * todo el ancho. Cada ítem se llama "Pregunta N" con el inicio de su enunciado: los códigos
 * internos de los controles (DAT-001…) no se muestran.
 */
import { useState, type SyntheticEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import type { Cuestionario } from "@/hooks/useCuestionario";
import { ESTADO_POR_VALOR, esEstadoDeclarado } from "@/lib/cuestionario/modelo";
import s from "./cuestionario.module.css";

export function IndiceControles({ c }: { c: Cuestionario }) {
  const [abierto, setAbierto] = useState(false);
  const grupos = new Map<string, { i: number; id: number; texto: string }[]>();
  c.controles.forEach((control, i) => {
    const d = control.dominio?.nombre_dominio ?? "Sin dominio";
    if (!grupos.has(d)) grupos.set(d, []);
    grupos.get(d)!.push({ i, id: control.id_control, texto: control.pregunta_evaluacion ?? "" });
  });
  const enCuestionario = c.fase.tipo === "cuestionario";
  const hechos = c.progreso?.controles_respondidos ?? 0;
  const total = c.progreso?.controles_aplicables ?? c.controles.length;

  return (
    <nav className={`card ${s.indice}`} aria-label="Índice de preguntas">
      <details open={abierto} onToggle={(e: SyntheticEvent<HTMLDetailsElement>) => setAbierto(e.currentTarget.open)}>
        <summary className={s.indiceResumen}>
          <span className={s.indiceResumenTexto}>
            <Icon name="lista" width={18} height={18} />
            {abierto ? "Ocultar las preguntas" : "Ver todas las preguntas"}
          </span>
          <span className={s.indiceResumenCuenta}>
            <span className="sr-only">{hechos} de {total} respondidas</span>
            <Icon name="flecha" width={16} height={16} className={s.indiceFlecha} data-abierto={abierto || undefined} />
          </span>
        </summary>

        <div className={s.indiceCuerpo}>
          <div className={s.indiceGrupos}>
            {[...grupos.entries()].map(([dominio, items]) => {
              const respondidos = items.filter((x) => c.respondidas.has(x.id)).length;
              return (
                <div key={dominio}>
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
                            onClick={() => {
                              c.irA(x.i);
                              setAbierto(false);
                            }}
                            aria-label={`Pregunta ${x.i + 1}, ${etiqueta}: ${x.texto}`}
                            title={x.texto}
                          >
                            <span className={s.punto} data-estado={estado ?? undefined} aria-hidden="true" />
                            <span className={s.itemNumero} aria-hidden="true">{x.i + 1}</span>
                            <span className={s.itemTexto} aria-hidden="true">{x.texto}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
          <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 16 }} onClick={() => void c.editarFiltro()}>
            <Icon name="refrescar" />
            Cambiar preguntas iniciales
          </button>
        </div>
      </details>
    </nav>
  );
}
