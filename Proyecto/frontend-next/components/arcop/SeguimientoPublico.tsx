"use client";

/**
 * HU-32 · Consulta pública del estado de una solicitud ARCOP con su código de seguimiento
 * (ARC-XXXX-XXXX), sin ingresar. Sirve también después de una supresión aprobada, cuando el
 * titular ya no tiene clave ni cuenta. Solo muestra tipo, estado y fechas (sin datos personales).
 */
import { useId, useState, type FormEvent } from "react";
import { fechaChile } from "@/lib/fechas";
import { DERECHOS, ESTADOS, consultarSeguimiento, mensajeError, normalizarCodigo, type SeguimientoArcop } from "@/lib/arcop";
import { Icon } from "@/components/ui/Icon";
import { BadgeEstadoArcop, Plazo, Progreso } from "./Comunes";
import s from "./arcop.module.css";

export function SeguimientoPublico() {
  const id = useId();
  const [codigo, setCodigo] = useState("");
  const [consultando, setConsultando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<SeguimientoArcop | null>(null);

  async function consultar(e: FormEvent) {
    e.preventDefault();
    const normal = normalizarCodigo(codigo);
    if (!normal) {
      setError("Revisa el código: tiene el formato ARC-XXXX-XXXX (8 letras o números).");
      return;
    }
    setConsultando(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await consultarSeguimiento(normal));
      setCodigo(normal);
    } catch (err) {
      setError(mensajeError(err, "No pudimos consultar el estado. Inténtalo más tarde."));
    } finally {
      setConsultando(false);
    }
  }

  return (
    <div className={s.columna}>
      <form className={s.columna} onSubmit={consultar} noValidate>
        <div className={s.campo}>
          <label htmlFor={`${id}-codigo`}>Código de seguimiento</label>
          <input
            id={`${id}-codigo`}
            className={`${s.texto} ${s.mono}`}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="ARC-XXXX-XXXX"
            maxLength={20}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value.toUpperCase())}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${id}-error` : `${id}-ayuda`}
          />
          <p id={`${id}-ayuda`} className={s.ayuda}>Te lo mostramos al enviar tu solicitud.</p>
          {error ? <p id={`${id}-error`} className={s.error} role="alert">{error}</p> : null}
        </div>
        <div>
          <button type="submit" className="btn btn-ghost" disabled={consultando || !codigo.trim()} aria-busy={consultando}>
            <Icon name="buscar" />
            {consultando ? "Consultando…" : "Consultar estado"}
          </button>
        </div>
      </form>

      {resultado ? (
        <div className={s.resultado} role="status" aria-live="polite">
          <div className={s.acciones} style={{ justifyContent: "space-between" }}>
            <strong>{DERECHOS[resultado.tipo]?.accion ?? resultado.tipo}</strong>
            <BadgeEstadoArcop estado={resultado.estado} />
          </div>
          <Progreso estado={resultado.estado} />
          <p className={s.ayuda}>{ESTADOS[resultado.estado]?.titular}</p>
          <p className={s.ayuda}>
            <span className={s.mono}>{resultado.codigo_seguimiento}</span> · enviada el {fechaChile(resultado.fecha_creacion)}
          </p>
          <Plazo
            solicitud={{
              id_solicitud: 0, codigo_seguimiento: resultado.codigo_seguimiento, tipo: resultado.tipo, estado: resultado.estado,
              usuario_temporal_id: null, evaluacion_id: null, usuario_definitivo_id: null,
              fecha_creacion: resultado.fecha_creacion, fecha_actualizacion: resultado.fecha_actualizacion,
              fecha_cierre: resultado.fecha_cierre, fecha_limite_respuesta: resultado.fecha_limite_respuesta,
              fecha_limite_informacion: null, plazo_vencido: resultado.plazo_vencido,
              fecha_prorroga: resultado.prorrogada ? resultado.fecha_actualizacion : null,
            }}
          />
          <p className={s.ayuda}>Para leer la respuesta completa o responder, ingresa con tu clave o tu cuenta.</p>
        </div>
      ) : null}
    </div>
  );
}
