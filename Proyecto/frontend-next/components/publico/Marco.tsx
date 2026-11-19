/**
 * HU-19 · Encabezado y pie de las páginas públicas. Server Components: no hidratan.
 * Corrección 18-11: la única excepción es el selector de tema (SelectorTema, componente cliente), para que quien
 * no tiene cuenta también elija claro, oscuro o azul (se guarda en este navegador). En pantallas anchas es el
 * grupo de tres íconos; en las angostas, un botón que pasa al tema siguiente (así el encabezado no se desborda).
 */
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandMark } from "@/components/ui/Icon";
import { SelectorTema } from "@/components/ui/SelectorTema";
import s from "./publico.module.css";

/**
 * Auditoría UX 16-11 · Fase 4.B: encabezado, contenido y pie comparten EL MISMO contenedor.
 * Desde HU-30 /encuesta usaba un contenedor más ancho (1440 px) solo para el contenido y el
 * logo quedaba ~150 px más adentro que el título. Con `ancho="amplio"` los tres usan el ancho.
 */
export type AnchoPagina = "normal" | "amplio";
const CONTENEDOR: Record<AnchoPagina, string> = { normal: s.contenedor, amplio: s.contenedorAncho };

export function EncabezadoPublico({ enlaces = true, ancho = "normal" }: { enlaces?: boolean; ancho?: AnchoPagina }) {
  return (
    <header className={s.encabezado}>
      <div className={`${CONTENEDOR[ancho]} ${s.encabezadoFila}`}>
        <Link href="/" className={s.marca} aria-label="ComplianceAI, inicio">
          <BrandMark />
          <span>
            <span className={s.marcaNombre}>ComplianceAI</span>
            <span className={s.marcaSub}>por TherionLabs</span>
          </span>
        </Link>
        {enlaces ? (
          <nav className={s.navPublica} aria-label="Principal">
            <a className={s.navEnlace} href="/#como-funciona">Cómo funciona</a>
            <a className={s.navEnlace} href="/#privacidad">Privacidad</a>
            <Link className="btn btn-ghost btn-sm" href="/retomar" prefetch={false}>
              {/* un solo nodo de texto: el botón es flex con gap y separaría las dos palabras */}
              <span>Retomar<span className={s.soloAncho}> evaluación</span></span>
            </Link>
            {/* HU-28: acceso de las empresas que contrataron el servicio */}
            <Link className="btn btn-ghost btn-sm" href="/ingresar" prefetch={false}>
              Clientes
            </Link>
          </nav>
        ) : null}
        <div className={s.tema}>
          <span className={s.temaAncho}><SelectorTema compacto /></span>
          <span className={s.temaAngosto}><SelectorTema variante="ciclo" /></span>
        </div>
      </div>
    </header>
  );
}

export function PiePublico({ ancho = "normal" }: { ancho?: AnchoPagina }) {
  return (
    <footer className={s.pie}>
      <div className={`${CONTENEDOR[ancho]} ${s.pieFila}`}>
        <span>© {new Date().getFullYear()} TherionLabs · ComplianceAI</span>
        <span>
          Autodiagnóstico orientativo; no reemplaza una auditoría legal. <Link href="/aviso-legal" prefetch={false}>Aviso legal</Link>
          {" · "}
          {/* HU-32 */}
          <Link href="/mis-derechos" prefetch={false}>Mis derechos sobre tus datos</Link>
        </span>
      </div>
    </footer>
  );
}

export function PaginaPublica({ children, enlaces = true, ancho = "normal" }: { children: ReactNode; enlaces?: boolean; ancho?: AnchoPagina }) {
  return (
    <div className={s.pagina}>
      <a href="#contenido" className="skip-link">
        Saltar al contenido
      </a>
      <EncabezadoPublico enlaces={enlaces} ancho={ancho} />
      <main id="contenido" tabIndex={-1}>
        {children}
      </main>
      <PiePublico ancho={ancho} />
    </div>
  );
}
