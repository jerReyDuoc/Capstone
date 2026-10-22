"use client";

/**
 * HU-02 · Evidencias de un control y su validación con IA (asíncrona en el worker).
 * Mientras alguna está "En cola" o "Validando", se consulta cada pocos segundos con
 * espera creciente; al terminar se avisa (onTermina) para recargar la respuesta, porque
 * la IA puede cambiar su estado final.
 */
import { useEffect, useRef, useState } from "react";
import { obtenerEvidencia } from "@/lib/cuestionario/api";
import { ESTADO_EVIDENCIA, ESTADO_POR_VALOR, esEstadoDeclarado, evidenciaEnCurso, type EvidenciaApi } from "@/lib/cuestionario/modelo";
import s from "./cuestionario.module.css";

const ESPERA_INICIAL_MS = 2500;
const ESPERA_MAX_MS = 15_000;
const MAX_CONSULTAS = 40; // ~5 min: después se deja de consultar (el backend sigue)

export function useSeguimientoEvidencias(iniciales: EvidenciaApi[], onTermina?: () => void): EvidenciaApi[] {
  const [lista, setLista] = useState(iniciales);
  const onTerminaRef = useRef(onTermina);
  onTerminaRef.current = onTermina;
  const clave = iniciales.map((e) => `${e.id_evidencia}:${e.estado_validacion}`).join("|");

  useEffect(() => setLista(iniciales), [clave]); // eslint-disable-line react-hooks/exhaustive-deps

  const enCurso = lista.filter(evidenciaEnCurso).map((e) => e.id_evidencia).join(",");

  useEffect(() => {
    if (!enCurso) return;
    let vivo = true;
    let consultas = 0;
    let t: number;
    const ids = enCurso.split(",").map(Number);

    const consultar = async () => {
      consultas++;
      const nuevas = await Promise.all(ids.map((id) => obtenerEvidencia(id).catch(() => null)));
      if (!vivo) return;
      let termino = false;
      setLista((prev) =>
        prev.map((e) => {
          const n = nuevas.find((x) => x?.id_evidencia === e.id_evidencia);
          if (n && evidenciaEnCurso(e) && !evidenciaEnCurso(n)) termino = true;
          return n ?? e;
        }),
      );
      if (termino) onTerminaRef.current?.();
      if (nuevas.some((n) => n && evidenciaEnCurso(n)) && consultas < MAX_CONSULTAS) {
        t = window.setTimeout(consultar, Math.min(ESPERA_INICIAL_MS * 1.3 ** consultas, ESPERA_MAX_MS));
      }
    };
    t = window.setTimeout(consultar, ESPERA_INICIAL_MS);
    return () => {
      vivo = false;
      window.clearTimeout(t);
    };
  }, [enCurso]);

  return lista;
}

export function ListaEvidencias({ evidencias }: { evidencias: EvidenciaApi[] }) {
  if (!evidencias.length) return null;
  return (
    <ul className={s.evidencias} aria-label="Evidencias adjuntas" aria-live="polite">
      {evidencias.map((e) => {
        const est = ESTADO_EVIDENCIA[e.estado_validacion] ?? { etiqueta: e.estado_validacion, tono: "bajo" as const };
        const clasif = esEstadoDeclarado(e.clasificacion_llm) ? ESTADO_POR_VALOR[e.clasificacion_llm].etiqueta : null;
        return (
          <li key={e.id_evidencia} className={s.evidenciaItem}>
            <div className={s.evidenciaFila}>
              <span className={s.evidenciaNombre}>{e.nombre_archivo}</span>
              <span className={`badge tone-${est.tono}`}>{est.etiqueta}</span>
            </div>
            {clasif ? (
              <p className={s.evidenciaLlm}>
                La IA la clasificó como <strong>{clasif}</strong>
                {e.confianza != null ? ` (confianza ${Math.round(e.confianza * 100)} %)` : ""}.
                {e.justificacion_llm ? ` ${e.justificacion_llm}` : ""}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
