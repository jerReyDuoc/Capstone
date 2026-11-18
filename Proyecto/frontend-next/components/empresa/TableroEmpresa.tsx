"use client";

/**
 * Auditoría UX 16-11 · Fase 8.C: lo accionable de "Mi empresa", arriba.
 * Junta datos que ya existen (contrato, registro de actividades y brechas de la evaluación más
 * reciente) y los ordena por urgencia (lib/tableroEmpresa.ts). Si algún dato no carga, el
 * tablero muestra lo demás: ninguna fuente bloquea a las otras.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { cargarPanel } from "@/lib/api";
import { diasParaTermino, type EspacioEmpresaApi } from "@/lib/empresa";
import { cargarCumplimiento, cargarRegistro } from "@/lib/registroActividades";
import { proximosPasos, type EntradaTablero, type PasoTablero } from "@/lib/tableroEmpresa";
import t from "./empresa.module.css";

const ICONO: Record<PasoTablero["tono"], "alerta" | "reloj" | "info" | "check"> = {
  urgente: "alerta",
  atencion: "reloj",
  info: "info",
  ok: "check",
};

export function TableroEmpresa({ datos }: { datos: EspacioEmpresaApi }) {
  const [entrada, setEntrada] = useState<EntradaTablero | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const reciente = datos.evaluaciones.find((e) => e.completada);
    Promise.allSettled([
      cargarCumplimiento(),
      cargarRegistro(),
      reciente ? cargarPanel(reciente.id, ctrl.signal, "/bff/cliente/api") : Promise.reject(new Error("sin evaluación")),
    ]).then(([cumplimiento, registro, panel]) => {
      if (ctrl.signal.aborted) return;
      const c = cumplimiento.status === "fulfilled" ? cumplimiento.value : null;
      const r = registro.status === "fulfilled" ? registro.value : null;
      setEntrada({
        diasContrato: diasParaTermino(datos.empresa.fecha_termino_contrato),
        revision: r?.revision_interna ? { estado: r.revision_interna.estado, dias: r.revision_interna.dias } : null,
        porRevisar: c?.registro.por_revisar ?? r?.global.por_revisar ?? null,
        brechasCriticas: panel.status === "fulfilled" ? panel.value.brechasPorSeveridad["Crítica"] : null,
        registro: c
          ? { mapaIniciado: c.mapa.iniciado, activas: c.registro.activas, vigenteCompleto: c.registro.vigente_completo, evidenciaAplicable: c.evidencia.aplicable }
          : null,
      });
    });
    return () => ctrl.abort();
  }, [datos]);

  if (!entrada) {
    return <div className={`skeleton ${t.esqueletoTablero}`} role="status" aria-label="Cargando tus próximos pasos" />;
  }
  const pasos = proximosPasos(entrada);

  return (
    <section className={`card ${t.tablero}`} aria-labelledby="tablero-titulo">
      <h2 className="card-title" id="tablero-titulo">Tus próximos pasos</h2>
      {pasos.length === 0 ? (
        <p className="card-sub">No tienes nada pendiente por ahora.</p>
      ) : (
        <ol className={t.pasos}>
          {pasos.map((p) => (
            <li key={p.id} className={t.paso} data-tono={p.tono}>
              <Icon name={ICONO[p.tono]} className={t.pasoIcono} aria-hidden="true" />
              <div className={t.pasoTexto}>
                <strong>{p.titulo}</strong>
                <span>{p.detalle}</span>
              </div>
              <Link href={p.accion.href} className={`btn ${p.tono === "urgente" ? "btn-primary" : "btn-ghost"} btn-sm`} prefetch={false}>
                {p.accion.texto}
                <span className="sr-only">: {p.titulo}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
