"use client";

/**
 * HU-19 · Zona de la evaluación del encuestado (/encuesta).
 * Muestra su evaluación (y solo la suya: el BFF y el backend lo garantizan), los límites
 * del día, el cuestionario adaptativo (HU-01/02) y el email opcional. Al completar el
 * cuestionario se pasa al panel de resultados (/panel?evaluacion=ID).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Cuestionario } from "@/components/cuestionario/Cuestionario";
import { AvisoError } from "@/components/inicio/AvisoError";
import { FormEmailOpcional } from "@/components/inicio/FormEmailOpcional";
import { useLimitesEncuesta } from "@/hooks/useLimitesEncuesta";
import { useSesionEncuestado } from "@/hooks/useSesionEncuestado";
import { BannerLimites } from "./BannerLimites";

export function InicioEncuesta() {
  const router = useRouter();
  const { estado, cerrarSesion } = useSesionEncuestado();
  const activa = estado.tipo === "activa";
  const { limites, refrescar } = useLimitesEncuesta(activa);

  useEffect(() => {
    if (estado.tipo === "inactiva") router.replace("/retomar?motivo=sesion");
  }, [estado.tipo, router]);

  if (estado.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 220 }} role="status" aria-label="Cargando tu evaluación" />;
  }
  if (estado.tipo === "error") {
    return <AvisoError error={{ codigo: "SIN_CONEXION", mensaje: "" }} onReintentar={() => window.location.reload()} />;
  }
  if (estado.tipo !== "activa") return null;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Correcciones 29-10: sin número de evaluación, aviso de guardado ni saldo diario (el número
          y la clave ya se entregaron al iniciar). Solo aparece un aviso si se agota la cuota. */}
      <BannerLimites limites={limites} />

      <Cuestionario evaluacionId={estado.evaluacionId} onLimites={() => void refrescar()} />

      <section className="card" aria-label="Correo opcional" style={{ maxWidth: 720 }}>
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
