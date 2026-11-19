"use client";

/**
 * Navegación común del panel (/panel/*) y del espacio de la empresa (/empresa/*).
 *
 * Auditoría UX 16-11:
 *  - Fase 8.A: el menú se organiza por TAREAS (lib/navegacion.ts): Diagnóstico · Plan de acción ·
 *    Privacidad y registro · Documentos, con rótulos cortos de una línea. Las URL no cambian.
 *  - Fase 7: bajo 1024 px la barra superior con ~16 íconos sin rótulo se reemplaza por una barra
 *    INFERIOR fija con 4 destinos + "Más" (hoja con todas las entradas agrupadas). Respeta el área
 *    segura, áreas táctiles de 44 px, aria-current y navegación por teclado.
 *  - Fase 4.A/7: "Cerrar sesión" va dentro del menú de cuenta, no en la barra.
 *
 * Modos (de usePanel; fuera de <PanelProvider>, en /empresa, se asume "cliente"):
 *  - cliente: usuario definitivo de una empresa (servicio contratado).
 *  - encuestado: hizo el autodiagnóstico sin cuenta; conserva "Mi evaluación" mientras está en
 *    curso y ve "Contratar".
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { usePanelOpcional, type ModoPanel } from "@/hooks/usePanel";
import { LOGIN_DE } from "@/lib/acceso";
import { pedir } from "@/lib/encuesta/cliente";
import { limpiarDatosDeCuenta } from "@/lib/sesionNavegador";
import {
  entradaActiva,
  grupoActivo,
  gruposNavegacion,
  MI_EMPRESA,
  type EntradaNav,
  type GrupoNav,
} from "@/lib/navegacion";
import { BrandMark, Icon } from "@/components/ui/Icon";
import { MenuCuenta, type OpcionCuenta } from "@/components/ui/MenuCuenta";
import { SelectorTema } from "@/components/ui/SelectorTema";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const panel = usePanelOpcional();
  const modo: ModoPanel = panel?.modo ?? "cliente";
  const href = panel?.href ?? ((ruta: string) => ruta);
  const abiertas = panel?.estado.tipo === "listo" ? panel.estado.panel.brechas.length : null;
  const demo = panel?.demo ?? false;
  const evaluacionEnCurso =
    modo === "encuestado" && (panel?.evaluaciones ?? []).some((e) => e.estado_progreso !== "completada");
  const grupos = gruposNavegacion(modo === "cliente" ? "cliente" : modo === "encuestado" ? "encuestado" : "interno");
  const cliente = modo === "cliente";

  // Las rutas del panel conservan la evaluación elegida; las de la empresa no la necesitan
  const destino = (ruta: string) => (ruta.startsWith("/panel") ? href(ruta) : ruta);

  async function salir() {
    // HU-28: el BFF revoca la sesión en el servidor y luego borra la cookie
    await pedir("/bff/cliente/logout", { method: "POST" }).catch(() => undefined);
    limpiarDatosDeCuenta(); // Corrección 18-11: la conversación del asistente no pasa a la próxima cuenta
    router.replace(`${LOGIN_DE.cliente}?motivo=salida`);
    router.refresh();
  }
  const opcionesCuenta: OpcionCuenta[] = [
    { tipo: "enlace", texto: "Configuración de la empresa", href: "/empresa/configuracion", icono: "engranaje" },
    { tipo: "accion", texto: "Cerrar sesión", icono: "salir", onSelect: salir },
  ];

  const contador = (e: EntradaNav): ReactNode =>
    e.ruta === "/panel/brechas" && abiertas ? (
      <span className="nav-count">
        {abiertas}
        <span className="sr-only"> brechas abiertas</span>
      </span>
    ) : null;

  const enlace = (e: EntradaNav, alNavegar?: () => void) => (
    <li key={e.ruta}>
      <Link
        href={destino(e.ruta)}
        className="nav-link"
        aria-current={entradaActiva(e, pathname) ? "page" : undefined}
        data-label={e.titulo ?? e.etiqueta}
        title={e.titulo}
        prefetch={e.ruta.startsWith("/empresa") ? false : undefined}
        onClick={alNavegar}
      >
        <Icon name={e.icono} />
        <span className="nav-label">{e.etiqueta}</span>
        {contador(e)}
      </Link>
    </li>
  );

  const extrasEncuestado = (alNavegar?: () => void) =>
    modo === "encuestado" ? (
      <nav className="nav" aria-label="Siguiente paso">
        <ul className="nav-list">
          {evaluacionEnCurso ? (
            <li>
              <Link href="/encuesta" className="nav-link" data-label="Mi evaluación" prefetch={false} onClick={alNavegar}>
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
              onClick={alNavegar}
            >
              <Icon name="empresa" />
              <span className="nav-label">Contratar</span>
            </Link>
          </li>
        </ul>
      </nav>
    ) : null;

  const listaGrupos = (idBase: string, alNavegar?: () => void) => (
    <>
      {cliente ? (
        <nav className="nav" aria-label="Inicio">
          <ul className="nav-list">{enlace(MI_EMPRESA, alNavegar)}</ul>
        </nav>
      ) : null}
      {grupos.map((g) => (
        <nav key={g.id} className="nav" aria-labelledby={`${idBase}-${g.id}`}>
          <p className="nav-heading" id={`${idBase}-${g.id}`}>{g.titulo}</p>
          <ul className="nav-list">{g.entradas.map((e) => enlace(e, alNavegar))}</ul>
        </nav>
      ))}
      {extrasEncuestado(alNavegar)}
    </>
  );

  const marca = (
    <Link
      href={cliente ? "/empresa" : href("/panel")}
      className="brand"
      aria-label={cliente ? "TherionLabs ComplianceAI, ir a Mi empresa" : "TherionLabs ComplianceAI, ir al diagnóstico"}
    >
      <BrandMark className="brand-mark" />
      <span className="brand-text">
        <span className="brand-name">
          Therion<span>Labs</span>
        </span>
        <span className="brand-product">ComplianceAI</span>
      </span>
    </Link>
  );

  return (
    <>
      {/* Escritorio y tablet horizontal: barra lateral */}
      <aside className="sidebar" aria-label="Navegación principal">
        {marca}
        {listaGrupos("nav")}
        <div className="sidebar-foot">
          {demo ? <span className="badge badge-demo">Modo demo</span> : null}
          {cliente ? <MenuCuenta titulo="Mi cuenta" detalle="Usuario de tu empresa" opciones={opcionesCuenta} /> : null}
        </div>
      </aside>

      {/* Móvil: barra superior compacta (marca + cuenta) y barra inferior con rótulos */}
      <header className="barra-movil">
        {marca}
        {demo ? <span className="badge badge-demo">Demo</span> : null}
        {/* Corrección 18-11: en escritorio el selector va en la barra superior (BarraSuperior) */}
        <SelectorTema cuenta={cliente ? "cliente" : "ninguna"} compacto />
        {cliente ? <MenuCuenta titulo="Mi cuenta" detalle="Usuario de tu empresa" opciones={opcionesCuenta} /> : null}
      </header>
      <NavInferior grupos={grupos} destino={destino} pathname={pathname} listaGrupos={listaGrupos} cliente={cliente} />
    </>
  );
}

function NavInferior({
  grupos,
  destino,
  pathname,
  listaGrupos,
  cliente,
}: {
  grupos: GrupoNav[];
  destino: (ruta: string) => string;
  pathname: string;
  listaGrupos: (idBase: string, alNavegar?: () => void) => ReactNode;
  cliente: boolean;
}) {
  const [hoja, setHoja] = useState(false);
  const idHoja = useId();
  const botonMas = useRef<HTMLButtonElement>(null);
  const panelHoja = useRef<HTMLDivElement>(null);
  const activo = grupoActivo(grupos, pathname);
  // "Más" queda activo cuando la página actual no es de ninguno de los 4 destinos (p. ej. Mi empresa)
  const masActivo = activo === null;

  useEffect(() => setHoja(false), [pathname]);
  useEffect(() => {
    if (!hoja) return;
    panelHoja.current?.querySelector<HTMLElement>("a, button")?.focus();
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setHoja(false);
        botonMas.current?.focus();
      }
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [hoja]);

  return (
    <>
      <nav className="nav-inferior" aria-label="Navegación principal">
        <ul>
          {grupos.map((g) => (
            <li key={g.id}>
              <Link
                href={destino(g.entradas[0].ruta)}
                className="nav-inferior-item"
                aria-current={activo === g.id ? "page" : undefined}
                aria-label={g.titulo}
                prefetch={g.entradas[0].ruta.startsWith("/empresa") ? false : undefined}
              >
                <Icon name={g.icono} />
                <span>{g.corto}</span>
              </Link>
            </li>
          ))}
          <li>
            <button
              ref={botonMas}
              type="button"
              className="nav-inferior-item"
              aria-expanded={hoja}
              aria-controls={idHoja}
              aria-current={masActivo && !hoja ? "page" : undefined}
              onClick={() => setHoja((x) => !x)}
            >
              <Icon name={hoja ? "cerrar" : "menu"} />
              <span>Más</span>
            </button>
          </li>
        </ul>
      </nav>
      {hoja ? (
        <>
          <div className="hoja-fondo" onClick={() => setHoja(false)} aria-hidden="true" />
          <div className="hoja" id={idHoja} ref={panelHoja} role="dialog" aria-modal="true" aria-label="Todas las secciones">
            <p className="hoja-titulo">{cliente ? "Todas las secciones" : "Secciones"}</p>
            {listaGrupos("hoja", () => setHoja(false))}
          </div>
        </>
      ) : null}
    </>
  );
}
