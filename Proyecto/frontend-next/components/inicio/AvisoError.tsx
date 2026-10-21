"use client";

/** HU-19 · Muestra un ErrorEncuesta con su acción sugerida y la espera, si la hay. */
import Link from "next/link";
import { useEffect, useState } from "react";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import { duracionLegible, horaDeReinicio, mensajeDeError } from "@/lib/encuesta/errores";
import s from "./inicio.module.css";

export function AvisoError({ error, onReintentar }: { error: ErrorEncuesta; onReintentar?: () => void }) {
  const m = mensajeDeError(error);
  const [restante, setRestante] = useState(m.esperaS ?? 0);

  useEffect(() => {
    setRestante(m.esperaS ?? 0);
    if (!m.esperaS) return;
    const t = setInterval(() => setRestante((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(t);
  }, [m.esperaS, error]);

  const reinicio = horaDeReinicio(error.reiniciaEn);
  const esLimite = m.accion === "esperar" || m.accion === "retomar";

  return (
    <div className={`${s.error} ${esLimite ? s.aviso429 : ""}`} role="alert">
      <strong>{m.titulo}</strong>
      <p>{m.detalle}</p>
      {reinicio ? <p>El cupo se renueva hoy a las {reinicio} (hora de Chile).</p> : null}
      {!reinicio && restante > 0 ? <p aria-live="off">Podrás intentarlo de nuevo en {duracionLegible(restante)}.</p> : null}
      <div className={s.errorAcciones}>
        {m.accion === "retomar" ? (
          <Link href="/retomar" prefetch={false} className="btn btn-ghost btn-sm">Retomar con mi clave</Link>
        ) : null}
        {m.accion === "recargar" ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => window.location.reload()}>
            Recargar la página
          </button>
        ) : null}
        {(m.accion === "reintentar" || (m.accion === "esperar" && !reinicio)) && onReintentar ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onReintentar} disabled={restante > 0}>
            Intentar de nuevo
          </button>
        ) : null}
      </div>
    </div>
  );
}
