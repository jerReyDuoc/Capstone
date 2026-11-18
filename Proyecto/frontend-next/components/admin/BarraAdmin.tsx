"use client";

/**
 * Correcciones 05-11 · Barra común del panel interno (Empresas cliente, Matriz normativa,
 * Bandeja de revisión y, desde HU-32, Solicitudes ARCOP; HU-41: Privacidad de la plataforma). Antes cada
 * página tenía su copia.
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
import { useEffect, useId, useState } from "react";
import { Actualizado } from "@/components/ui/Actualizado";
import { BrandMark, Icon } from "@/components/ui/Icon";
import { MenuCuenta } from "@/components/ui/MenuCuenta";
import { useActualizacionAutomatica } from "@/hooks/useActualizacionAutomatica";
import { LOGIN_DE } from "@/lib/acceso";
import { pedir } from "@/lib/encuesta/cliente";
import a from "./admin.module.css";

/**
 * Auditoría UX 16-11 · Fase 4.A: el encabezado cabe en UNA línea a 1280 y 1440 px.
 *  - Rótulos cortos; "Cerrar sesión" pasa al menú de cuenta (extremo derecho).
 *  - "Actualizar" deja de ser un botón gris que parecía desactivado: los datos se recargan
 *    solos al volver a la pestaña y se muestra "Actualizado hace X" con un ícono para forzarlo.
 *  - En móvil: barra compacta (marca + Secciones + cuenta); las secciones se despliegan.
 */
export const SECCIONES_ADMIN = [
  { href: "/admin/clientes", texto: "Empresas cliente" },
  { href: "/admin/matriz", texto: "Matriz normativa" },
  { href: "/admin/revision", texto: "Bandeja de revisión" },
  // HU-32: solicitudes de derechos de los titulares (acceso, rectificación, cancelación, oposición y portabilidad)
  { href: "/admin/arcop", texto: "Solicitudes ARCOP", titulo: "Solicitudes de derechos ARCOP (acceso, rectificación, cancelación, oposición y portabilidad)" },
  // HU-25: plazo de retención de usuarios temporales y ejecuciones de la anonimización
  { href: "/admin/retencion", texto: "Retención" , titulo: "Retención de datos" },
  // HU-41: registro de tratamiento de la propia plataforma (mapa, registro y revisión interna)
  { href: "/admin/privacidad", texto: "Privacidad", titulo: "Privacidad de la plataforma" },
] as const;

export function BarraAdmin({
  onActualizar,
  alVolver = true,
}: {
  /** Vuelve a cargar los datos de la sección. */
  onActualizar: () => Promise<unknown> | unknown;
  /** Actualizar también al volver a la pestaña del navegador (por defecto, sí). */
  alVolver?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const actualizacion = useActualizacionAutomatica(onActualizar, alVolver);
  const [navAbierta, setNavAbierta] = useState(false);
  const idNav = useId();
  const { marcar } = actualizacion;

  // La sección acaba de cargar sus datos al montarse
  useEffect(() => marcar(), [marcar]);
  // Al cambiar de sección se cierra el menú móvil
  useEffect(() => setNavAbierta(false), [pathname]);

  async function salir() {
    // HU-28: el BFF revoca la sesión en el servidor y luego borra la cookie
    await pedir("/bff/admin/logout", { method: "POST" }).catch(() => undefined);
    router.replace(`${LOGIN_DE.admin}?motivo=salida`);
    router.refresh();
  }

  return (
    <header className={a.barra}>
      <Link href="/admin/clientes" className={a.marca} aria-label="ComplianceAI, panel interno de Therion Labs">
        <BrandMark aria-hidden="true" />
        <span>
          ComplianceAI
          <span className={a.marcaSub}>Panel interno</span>
        </span>
      </Link>
      <button
        type="button"
        className={`btn btn-ghost btn-sm ${a.botonNav}`}
        aria-expanded={navAbierta}
        aria-controls={idNav}
        onClick={() => setNavAbierta((x) => !x)}
      >
        <Icon name="menu" />
        Secciones
      </button>
      <nav id={idNav} className={a.nav} data-abierta={navAbierta || undefined} aria-label="Secciones del panel interno">
        {SECCIONES_ADMIN.map((x) => (
          <Link
            key={x.href}
            className={a.navLink}
            href={x.href}
            title={"titulo" in x ? x.titulo : undefined}
            aria-current={pathname === x.href || pathname.startsWith(`${x.href}/`) ? "page" : undefined}
          >
            {x.texto}
          </Link>
        ))}
      </nav>
      <div className={a.barraAcciones}>
        <Actualizado estado={actualizacion} className={a.actualizado} />
        <MenuCuenta
          titulo="Administración Therion Labs"
          detalle="Sesión de administrador"
          opciones={[{ tipo: "accion", texto: "Cerrar sesión", icono: "salir", onSelect: salir }]}
        />
      </div>
    </header>
  );
}
