"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePanel } from "@/hooks/usePanel";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { BrandMark, Icon, type IconName } from "@/components/ui/Icon";

const ITEMS: { ruta: string; etiqueta: string; icono: IconName }[] = [
  { ruta: "/panel", etiqueta: "Diagnóstico", icono: "diagnostico" },
  { ruta: "/panel/dominios", etiqueta: "Dominios", icono: "dominios" },
  { ruta: "/panel/brechas", etiqueta: "Brechas", icono: "brechas" },
  { ruta: "/panel/capacitacion", etiqueta: "Capacitación", icono: "birrete" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { href, estado, demo, modo } = usePanel();
  const abiertas = estado.tipo === "listo" ? estado.panel.brechas.length : null;

  return (
    <aside className="sidebar">
      <Link href={href("/panel")} className="brand" aria-label="TherionLabs ComplianceAI, ir al diagnóstico">
        <BrandMark className="brand-mark" />
        <span className="brand-text">
          <span className="brand-name">
            Therion<span>Labs</span>
          </span>
          <span className="brand-product">ComplianceAI</span>
        </span>
      </Link>

      <nav className="nav" aria-label="Secciones del panel">
        <p className="nav-heading" id="nav-heading">Gobernanza de IA</p>
        <ul className="nav-list" aria-labelledby="nav-heading">
          {ITEMS.map((it) => {
            const activo = pathname === it.ruta;
            return (
              <li key={it.ruta}>
                <Link
                  href={href(it.ruta)}
                  className="nav-link"
                  aria-current={activo ? "page" : undefined}
                  data-label={it.etiqueta}
                >
                  <Icon name={it.icono} />
                  <span className="nav-label">{it.etiqueta}</span>
                  {it.ruta === "/panel/brechas" && abiertas ? (
                    <span className="nav-count">
                      {abiertas}
                      <span className="sr-only"> brechas abiertas</span>
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {modo === "encuestado" ? (
        <nav className="nav" aria-label="Mi evaluación">
          <ul className="nav-list">
            <li>
              <Link href="/encuesta" className="nav-link" data-label="Mi evaluación" prefetch={false}>
                <Icon name="lista" />
                <span className="nav-label">Mi evaluación</span>
              </Link>
            </li>
            <li>
              {/* HU-31 */}
              <Link
                href={href("/panel/contratar")}
                className="nav-link"
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
        // HU-28: el usuario definitivo vuelve al espacio de su empresa o cierra su sesión
        <nav className="nav" aria-label="Mi empresa">
          <ul className="nav-list">
            <li>
              <Link href="/empresa" className="nav-link" data-label="Mi empresa" prefetch={false}>
                <Icon name="lista" />
                <span className="nav-label">Mi empresa</span>
              </Link>
            </li>
          </ul>
          <div style={{ padding: "8px 12px" }}>
            <BotonCerrarSesion tipo="cliente" />
          </div>
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
