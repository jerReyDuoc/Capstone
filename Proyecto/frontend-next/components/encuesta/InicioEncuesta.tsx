"use client";

/**
 * HU-19 · Portada de la evaluación del encuestado (/encuesta).
 * Muestra su evaluación (y solo la suya: el BFF y el backend lo garantizan), el
 * progreso, los límites del día y el email opcional. El cuestionario (HU-01/02) se
 * monta aquí cuando esté su pantalla.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useLimitesEncuesta } from "@/hooks/useLimitesEncuesta";
import { useSesionEncuestado } from "@/hooks/useSesionEncuestado";
import { comoErrorEncuesta, pedir } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import { AvisoError } from "@/components/inicio/AvisoError";
import { FormEmailOpcional } from "@/components/inicio/FormEmailOpcional";
import { BannerLimites } from "./BannerLimites";

interface Progreso {
  etapa: "filtro" | "cuestionario" | "completo" | "cerrada" | string;
  porcentaje: number;
  controles_aplicables: number;
  controles_respondidos: number;
  cerrada: boolean;
}

const ETAPA: Record<string, string> = {
  filtro: "Preguntas iniciales pendientes",
  cuestionario: "Cuestionario en curso",
  completo: "Listo para cerrar",
  cerrada: "Evaluación cerrada",
};

export function InicioEncuesta() {
  const router = useRouter();
  const { estado, cerrarSesion } = useSesionEncuestado();
  const activa = estado.tipo === "activa";
  const { limites } = useLimitesEncuesta(activa);
  const [progreso, setProgreso] = useState<Progreso | null>(null);
  const [error, setError] = useState<ErrorEncuesta | null>(null);

  useEffect(() => {
    if (estado.tipo === "inactiva") router.replace("/retomar?motivo=sesion");
  }, [estado.tipo, router]);

  useEffect(() => {
    if (estado.tipo !== "activa") return;
    pedir<Progreso>(`/bff/api/evaluaciones/${estado.evaluacionId}/progreso`)
      .then(setProgreso)
      .catch((e) => setError(comoErrorEncuesta(e)));
  }, [estado]);

  if (estado.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 220 }} role="status" aria-label="Cargando tu evaluación" />;
  }
  if (estado.tipo === "error") {
    return <AvisoError error={{ codigo: "SIN_CONEXION", mensaje: "" }} onReintentar={() => window.location.reload()} />;
  }
  if (estado.tipo !== "activa") return null;

  const pct = Math.round(progreso?.porcentaje ?? 0);

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <BannerLimites limites={limites} />

      <section className="card" aria-labelledby="t-ev">
        <div className="card-head">
          <div>
            <h2 id="t-ev" className="card-title">Evaluación N.º {estado.evaluacionId}</h2>
            <p className="card-sub">{progreso ? ETAPA[progreso.etapa] ?? progreso.etapa : "Cargando progreso…"}</p>
          </div>
          <span className="badge tone-ok">{pct} %</span>
        </div>
        <div
          className="meter"
          role="progressbar"
          aria-label="Avance del cuestionario"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          style={{ marginTop: 16 }}
        >
          <span style={{ width: `${pct}%` }} />
        </div>
        {progreso ? (
          <p className="card-sub" style={{ marginTop: 8 }}>
            {progreso.controles_respondidos} de {progreso.controles_aplicables} controles respondidos
          </p>
        ) : null}
        {error ? <AvisoError error={error} /> : null}
        <p className="callout" style={{ marginTop: 20 }}>
          El cuestionario se guarda solo a medida que respondes. Puedes cerrar esta ventana y retomar con tu número y tu clave.
        </p>
      </section>

      <section className="card" aria-label="Correo opcional">
        <FormEmailOpcional compacto />
      </section>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "space-between" }}>
        <Link href="/" className="btn btn-ghost btn-sm">Ir al inicio</Link>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={async () => {
            await cerrarSesion();
            router.replace("/");
          }}
        >
          Cerrar sesión en este dispositivo
        </button>
      </div>
    </div>
  );
}
