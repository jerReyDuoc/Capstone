"use client";

/**
 * Correcciones 05-11 · Barra común del panel interno (Empresas cliente, Matriz normativa,
 * Bandeja de revisión y, desde HU-32, Solicitudes ARCOP). Antes cada página tenía su copia.
 *
 *  - "Actualizar" vuelve a pedir los datos de la sección abierta sin recargar la página (F5):
 *    no se pierde la pestaña, el filtro ni lo que se está escribiendo. Muestra la hora de la
 *    última actualización (hora de Chile) y lo anuncia a lectores de pantalla.
 *  - Con `alVolver`, la sección también se actualiza sola al volver a la pestaña del
 *    navegador después de un rato (como mínimo cada 30 s), para no trabajar con datos viejos.
 *  - La sección actual se marca con aria-current según la URL.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BrandMark, Icon } from "@/components/ui/Icon";
import { pedir } from "@/lib/encuesta/cliente";
import { horaChile } from "@/lib/fechas";
import a from "./admin.module.css";

const SECCIONES = [
  { href: "/admin/clientes", texto: "Empresas cliente" },
  { href: "/admin/matriz", texto: "Matriz normativa" },
  { href: "/admin/revision", texto: "Bandeja de revisión" },
  // HU-32: solicitudes de derechos ARCOP de los titulares
  { href: "/admin/arcop", texto: "Solicitudes ARCOP" },
  // HU-25: plazo de retención de usuarios temporales y ejecuciones de la anonimización
  { href: "/admin/retencion", texto: "Retención de datos" },
] as const;

const MIN_ENTRE_AUTOMATICAS_MS = 30_000;

export function BarraAdmin({
  onActualizar,
  alVolver = false,
}: {
  /** Vuelve a cargar los datos de la sección. */
  onActualizar: () => Promise<unknown> | unknown;
  /** Actualizar también al volver a la pestaña del navegador. */
  alVolver?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [actualizando, setActualizando] = useState(false);
  const [ultima, setUltima] = useState<Date | null>(null);
  const enCurso = useRef(false);
  const ultimaRef = useRef<number>(Date.now());
  const fn = useRef(onActualizar);
  fn.current = onActualizar;

  const actualizar = useCallback(async () => {
    if (enCurso.current) return;
    enCurso.current = true;
    setActualizando(true);
    try {
      await fn.current();
      const ahora = new Date();
      ultimaRef.current = ahora.getTime();
      setUltima(ahora);
    } finally {
      enCurso.current = false;
      setActualizando(false);
    }
  }, []);

  useEffect(() => {
    if (!alVolver) return;
    const alCambiar = () => {
      if (document.visibilityState === "visible" && Date.now() - ultimaRef.current > MIN_ENTRE_AUTOMATICAS_MS) {
        void actualizar();
      }
    };
    document.addEventListener("visibilitychange", alCambiar);
    return () => document.removeEventListener("visibilitychange", alCambiar);
  }, [alVolver, actualizar]);

  async function salir() {
    // HU-28: el BFF revoca la sesión en el servidor y luego borra la cookie
    await pedir("/bff/admin/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/admin/login?motivo=salida");
  }

  return (
    <header className={a.barra}>
      <div className={a.marca}>
        <BrandMark aria-hidden="true" />
        <span>
          ComplianceAI
          <span className={a.marcaSub}>Panel interno · Therion Labs</span>
        </span>
      </div>
      <nav className={a.nav} aria-label="Secciones del panel interno">
        {SECCIONES.map((x) => (
          <Link
            key={x.href}
            className={a.navLink}
            href={x.href}
            aria-current={pathname === x.href || pathname.startsWith(`${x.href}/`) ? "page" : undefined}
          >
            {x.texto}
          </Link>
        ))}
      </nav>
      <div className={a.barraAcciones}>
        <span className={a.actualizado} aria-live="polite">
          {actualizando ? "Actualizando…" : ultima ? `Actualizado ${horaChile(ultima)}` : ""}
        </span>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => void actualizar()}
          disabled={actualizando}
          aria-busy={actualizando}
          title="Vuelve a cargar los datos de esta sección"
        >
          <Icon name="refrescar" className={actualizando ? a.girando : undefined} />
          Actualizar
        </button>
        <button className="btn btn-ghost btn-sm" type="button" onClick={salir}>
          Cerrar sesión
        </button>
      </div>
    </header>
  );
}
