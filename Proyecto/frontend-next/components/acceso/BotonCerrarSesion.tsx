"use client";

/**
 * HU-28 · "Cerrar sesión" del usuario definitivo o del administrador.
 * El BFF revoca la sesión en el servidor y borra la cookie; luego se vuelve al login.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LOGIN_DE, type TipoCuenta } from "@/lib/acceso";
import { pedir } from "@/lib/encuesta/cliente";

export function BotonCerrarSesion({ tipo, className = "btn btn-ghost btn-sm" }: { tipo: TipoCuenta; className?: string }) {
  const router = useRouter();
  const [saliendo, setSaliendo] = useState(false);

  async function salir() {
    if (saliendo) return;
    setSaliendo(true);
    await pedir(tipo === "admin" ? "/bff/admin/logout" : "/bff/cliente/logout", { method: "POST" }).catch(() => undefined);
    router.replace(`${LOGIN_DE[tipo]}?motivo=salida`);
    router.refresh();
  }

  return (
    <button type="button" className={className} onClick={salir} disabled={saliendo}>
      {saliendo ? "Cerrando sesión…" : "Cerrar sesión"}
    </button>
  );
}
