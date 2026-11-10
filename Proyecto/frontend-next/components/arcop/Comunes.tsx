"use client";

/**
 * HU-32 · Piezas compartidas por la página del titular y la bandeja del admin: insignia de
 * estado, progreso en 4 hitos, plazo, historial y campo de texto con contador.
 */
import { useId } from "react";
import { fechaHoraChile } from "@/lib/fechas";
import {
  ESTADOS, PASOS, esFinal, pasoActual, textoEvento, textoPlazo,
  type EstadoArcop, type EventoArcop, type SolicitudArcop,
} from "@/lib/arcop";
import { Icon } from "@/components/ui/Icon";
import s from "./arcop.module.css";

export function BadgeEstadoArcop({ estado }: { estado: EstadoArcop }) {
  const e = ESTADOS[estado];
  return (
    <span className={`badge tone-${e?.tono ?? "info"}`}>
      <span className="sr-only">Estado: </span>
      {e?.etiqueta ?? estado}
    </span>
  );
}

/** Enviada → En revisión → En proceso → Respondida (el último dice Resuelta, Rechazada o Cancelada). */
export function Progreso({ estado }: { estado: EstadoArcop }) {
  const actual = pasoActual(estado);
  const final = esFinal(estado);
  return (
    <ol className={s.progreso} aria-label="Avance de la solicitud">
      {PASOS.map((paso, i) => {
        const hecho = i < actual || (final && i === actual);
        const esActual = i === actual;
        const ultimo = i === PASOS.length - 1;
        const clases = [s.hito];
        if (hecho) clases.push(s.hitoHecho);
        if (esActual) clases.push(s.hitoActual);
        if (ultimo && estado === "rechazada") clases.push(s.hitoAlto);
        if (ultimo && estado === "cancelada") clases.push(s.hitoCancelado);
        const texto = ultimo && final ? ESTADOS[estado].etiqueta : paso;
        return (
          <li key={paso} className={clases.join(" ")} aria-current={esActual ? "step" : undefined}>
            {texto}
            <span className="sr-only">{hecho ? " (completado)" : esActual ? " (paso actual)" : " (pendiente)"}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function Plazo({ solicitud }: { solicitud: SolicitudArcop }) {
  const p = textoPlazo(solicitud);
  if (!p) return null;
  const clase = p.tono === "alto" ? s.plazoAlto : p.tono === "medio" ? s.plazoMedio : "";
  return (
    <span className={`${s.plazo} ${clase}`}>
      <Icon name={p.tono === "alto" ? "alerta" : "reloj"} aria-hidden="true" />
      {p.texto}
      {solicitud.fecha_prorroga && !esFinal(solicitud.estado) ? " · prorrogado" : ""}
    </span>
  );
}

export function Historial({ eventos, paraTitular }: { eventos: EventoArcop[]; paraTitular: boolean }) {
  if (!eventos.length) return null;
  return (
    <details>
      <summary className={s.historialResumen}>Ver historial ({eventos.length})</summary>
      <ol className={s.historial}>
        {eventos.map((e) => (
          <li key={e.id_evento} className={`${s.paso} ${e.actor_rol !== "admin_therion" ? s.pasoTitular : ""}`}>
            <span aria-hidden="true" />
            <span className={s.pasoTexto}>
              <strong>{textoEvento(e, paraTitular)}</strong>
              <span className={s.pasoMeta}>
                {fechaHoraChile(e.fecha)} · {e.actor_rol === "admin_therion" ? "Responsable" : paraTitular ? "Tú" : "Titular"}
              </span>
              {e.comentario ? <span className={s.pasoComentario}>{e.comentario}</span> : null}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** Textarea con etiqueta, ayuda, contador y error accesibles. */
export function CampoTexto({
  etiqueta, valor, onCambio, max, ayuda, error, placeholder, corto = false, obligatorio = true,
}: {
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  max: number;
  ayuda?: string;
  error?: string | null;
  placeholder?: string;
  corto?: boolean;
  obligatorio?: boolean;
}) {
  const id = useId();
  const describe = [ayuda ? `${id}-ayuda` : "", error ? `${id}-error` : "", `${id}-cuenta`].filter(Boolean).join(" ");
  return (
    <div className={s.campo}>
      <label htmlFor={id}>
        {etiqueta}
        {obligatorio ? null : <span className="field-opcional"> (opcional)</span>}
      </label>
      {ayuda ? <p id={`${id}-ayuda`} className={s.ayuda}>{ayuda}</p> : null}
      <textarea
        id={id}
        className={`${s.area} ${corto ? s.areaCorta : ""}`}
        value={valor}
        maxLength={max}
        placeholder={placeholder}
        onChange={(e) => onCambio(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describe}
        aria-required={obligatorio || undefined}
      />
      <div className={s.pieCampo}>
        <span id={`${id}-error`} className={s.error} role={error ? "alert" : undefined}>{error ?? ""}</span>
        <span id={`${id}-cuenta`}>{valor.trim().length.toLocaleString("es-CL")} / {max.toLocaleString("es-CL")}</span>
      </div>
    </div>
  );
}
