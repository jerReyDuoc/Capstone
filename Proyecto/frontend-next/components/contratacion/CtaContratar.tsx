"use client";

/**
 * HU-31 criterio 1 · "Contratar la plataforma" en los resultados del encuestado (sin cuenta).
 *
 * Va DESPUÉS de los resultados: primero el diagnóstico gratis, luego el siguiente paso.
 * Si ya pidió contratar, en vez del botón muestra el estado de su solicitud, así no la
 * envía dos veces. No aparece para el equipo interno (modo "interno").
 */
import Link from "next/link";
import { useId } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { useSolicitudContratacion } from "@/hooks/useSolicitudContratacion";
import { BENEFICIOS, ESTADO_PUBLICO } from "@/lib/contratacion";
import s from "./contratacion.module.css";

export function CtaContratar({ brechas }: { brechas: number }) {
  const { modo, evaluacionId, href } = usePanel();
  const encuestado = modo === "encuestado";
  const { estado } = useSolicitudContratacion(evaluacionId, encuestado);
  const idTitulo = useId();

  if (!encuestado) return null;

  const enviada = estado.tipo === "enviada" ? ESTADO_PUBLICO[estado.solicitud.estado] : null;

  return (
    <section className={`card card-glow ${s.cta}`} aria-labelledby={idTitulo}>
      <div>
        <p className={s.ctaEyebrow}>
          <Icon name="chispa" />
          Siguiente paso
        </p>
        <h2 id={idTitulo} className={s.ctaTitulo}>
          {brechas > 0
            ? `Cierra ${brechas === 1 ? "tu brecha" : `tus ${brechas} brechas`} con ComplianceIA`
            : "Mantén tu cumplimiento al día con ComplianceIA"}
        </h2>
        <p className={s.ctaTexto}>
          Con el servicio contratado tu equipo sigue desde este diagnóstico, sin repetirlo, y accede a:
        </p>
        <ul className={s.beneficios}>
          {BENEFICIOS.map((b) => (
            <li key={b.titulo} className={s.beneficio}>
              <Icon name={b.icono as IconName} aria-hidden="true" />
              <div>
                <strong>{b.titulo}</strong>
                <span>{b.texto}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {enviada ? (
        <div className={s.ctaEstado} role="status">
          <span className={`badge tone-${enviada.tono}`}>{enviada.titulo}</span>
          <p>{enviada.detalle}</p>
        </div>
      ) : (
        <div className={s.ctaAccion}>
          <Link href={href("/panel/contratar")} className="btn btn-primary" prefetch={false}>
            Contratar la plataforma
            <Icon name="flecha" />
          </Link>
          <p className={s.ctaNota}>Déjanos tus datos y Therion Labs te contactará. No pagas nada al enviarlos.</p>
        </div>
      )}
    </section>
  );
}
