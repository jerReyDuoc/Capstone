"use client";

/**
 * Barra lateral común del panel (/panel/*) y del espacio de la empresa (/empresa/*).
 *
 * Correcciones 29-10:
 * - El usuario definitivo (modo "cliente") ve la misma barra en ambos lugares, con el grupo
 *   "Mi empresa": Mi empresa, Mis evaluaciones y Mis documentos (cada uno con su página).
 * - Quien hizo el autodiagnóstico sin cuenta (modo "encuestado") no ve "Cerrar brechas",
 *   "Mis documentos" ni "Mi evaluación" una vez completada: le quedan sus resultados y "Contratar".
 *   Si su evaluación sigue en curso, conserva "Mi evaluación" para volver a ella.
 * Fuera de <PanelProvider> (páginas de /empresa) se asume el modo "cliente".
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { usePanelOpcional, type ModoPanel } from "@/hooks/usePanel";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { BrandMark, Icon, type IconName } from "@/components/ui/Icon";

interface Item {
  ruta: string;
  etiqueta: string;
  icono: IconName;
  /** Ruta exacta (no marca sus subrutas como activas). */
  exacta?: boolean;
}

const RESULTADOS: Item[] = [
  { ruta: "/panel", etiqueta: "Diagnóstico", icono: "diagnostico", exacta: true },
  { ruta: "/panel/dominios", etiqueta: "Dominios", icono: "dominios" },
  { ruta: "/panel/brechas", etiqueta: "Brechas", icono: "brechas" },
  // HU-10: comparativa contra el sector (k-anonimato)
  { ruta: "/panel/sector", etiqueta: "Sector", icono: "sector" },
  // HU-26: /panel/capacitacion/[ruta] sigue marcando "Capacitación"
  { ruta: "/panel/capacitacion", etiqueta: "Capacitación", icono: "birrete" },
];

// HU-17: cerrar brechas con evidencia. Es del servicio contratado: solo el cliente la ve.
const CERRAR_BRECHAS: Item = { ruta: "/panel/remediacion", etiqueta: "Cerrar brechas", icono: "subir" };

const EMPRESA: Item[] = [
  { ruta: "/empresa", etiqueta: "Mi empresa", icono: "empresa", exacta: true },
  { ruta: "/empresa/evaluaciones", etiqueta: "Mis evaluaciones", icono: "historial" },
  { ruta: "/empresa/documentos", etiqueta: "Mis documentos", icono: "carpeta" },
];

export function Sidebar() {
  const pathname = usePathname();
  const panel = usePanelOpcional();
  const modo: ModoPanel = panel?.modo ?? "cliente";
  const href = panel?.href ?? ((ruta: string) => ruta);
  const abiertas = panel?.estado.tipo === "listo" ? panel.estado.panel.brechas.length : null;
  const demo = panel?.demo ?? false;
  // El encuestado conserva "Mi evaluación" solo mientras su evaluación sigue en curso
  const evaluacionEnCurso =
    modo === "encuestado" && (panel?.evaluaciones ?? []).some((e) => e.estado_progreso !== "completada");

  const resultados = modo === "cliente" ? [...RESULTADOS, CERRAR_BRECHAS] : RESULTADOS;

  const enlace = (it: Item, extra?: ReactNode) => {
    const activo = it.exacta ? pathname === it.ruta : pathname === it.ruta || pathname.startsWith(`${it.ruta}/`);
    // Las rutas del panel conservan la evaluación elegida; las de la empresa no la necesitan
    const destino = it.ruta.startsWith("/panel") ? href(it.ruta) : it.ruta;
    return (
      <li key={it.ruta}>
        <Link
          href={destino}
          className="nav-link"
          aria-current={activo ? "page" : undefined}
          data-label={it.etiqueta}
          prefetch={it.ruta.startsWith("/empresa") ? false : undefined}
        >
          <Icon name={it.icono} />
          <span className="nav-label">{it.etiqueta}</span>
          {extra}
        </Link>
      </li>
    );
  };

  return (
    <aside className="sidebar">
      <Link
        href={modo === "cliente" ? "/empresa" : href("/panel")}
        className="brand"
        aria-label={modo === "cliente" ? "TherionLabs ComplianceAI, ir a Mi empresa" : "TherionLabs ComplianceAI, ir al diagnóstico"}
      >
        <BrandMark className="brand-mark" />
        <span className="brand-text">
          <span className="brand-name">
            Therion<span>Labs</span>
          </span>
          <span className="brand-product">ComplianceAI</span>
        </span>
      </Link>

      {modo === "cliente" ? (
        <nav className="nav" aria-labelledby="nav-empresa">
          <p className="nav-heading" id="nav-empresa">Mi empresa</p>
          <ul className="nav-list">{EMPRESA.map((it) => enlace(it))}</ul>
        </nav>
      ) : null}

      <nav className="nav" aria-labelledby="nav-heading">
        <p className="nav-heading" id="nav-heading">Gobernanza de IA</p>
        <ul className="nav-list">
          {resultados.map((it) =>
            enlace(
              it,
              it.ruta === "/panel/brechas" && abiertas ? (
                <span className="nav-count">
                  {abiertas}
                  <span className="sr-only"> brechas abiertas</span>
                </span>
              ) : null,
            ),
          )}
        </ul>
      </nav>

      {modo === "encuestado" ? (
        <nav className="nav" aria-label="Siguiente paso">
          <ul className="nav-list">
            {evaluacionEnCurso ? (
              <li>
                <Link href="/encuesta" className="nav-link" data-label="Mi evaluación" prefetch={false}>
                  <Icon name="lista" />
                  <span className="nav-label">Mi evaluación</span>
                </Link>
              </li>
            ) : null}
            <li>
              {/* HU-31: única puerta al servicio para quien no tiene cuenta, por eso destaca */}
              <Link
                href={href("/panel/contratar")}
                className="nav-link nav-link-destacado"
                data-label="Contratar"
                aria-current={pathname === "/panel/contratar" ? "page" : undefined}
                prefetch={false}
              >
                <Icon name="chispa" />
                <span className="nav-label">Contratar</span>
              </Link>
            </li>
          </ul>
        </nav>
      ) : null}

      {modo === "cliente" ? (
        <nav className="nav" aria-label="Sesión">
          <ul className="nav-list">
            <li>
              <BotonCerrarSesion tipo="cliente" className="nav-link nav-boton" icono={<Icon name="salir" />} />
            </li>
          </ul>
        </nav>
      ) : null}

      <div className="sidebar-foot">
        {demo ? <span className="badge badge-demo">Modo demo</span> : null}
        <p>
          <strong>Ley 21.719</strong> · lectura ejecutiva de exposición en gobernanza de IA y datos personales.
        </p>
      </div>
    </aside>
  );
}
