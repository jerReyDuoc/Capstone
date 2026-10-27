/**
 * HU-19 · Encabezado y pie de las páginas públicas. Server Components: no hidratan.
 */
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandMark } from "@/components/ui/Icon";
import s from "./publico.module.css";

export function EncabezadoPublico({ enlaces = true }: { enlaces?: boolean }) {
  return (
    <header className={s.encabezado}>
      <div className={`${s.contenedor} ${s.encabezadoFila}`}>
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
              Retomar evaluación
            </Link>
            {/* HU-28: acceso de las empresas que contrataron el servicio */}
            <Link className="btn btn-ghost btn-sm" href="/ingresar" prefetch={false}>
              Clientes
            </Link>
          </nav>
        ) : null}
      </div>
    </header>
  );
}

export function PiePublico() {
  return (
    <footer className={s.pie}>
      <div className={`${s.contenedor} ${s.pieFila}`}>
        <span>© {new Date().getFullYear()} TherionLabs · ComplianceAI</span>
        <span>
          Autodiagnóstico orientativo; no reemplaza una auditoría legal. <Link href="/aviso-legal" prefetch={false}>Aviso legal</Link>
        </span>
      </div>
    </footer>
  );
}

export function PaginaPublica({ children, enlaces = true }: { children: ReactNode; enlaces?: boolean }) {
  return (
    <div className={s.pagina}>
      <a href="#contenido" className="skip-link">
        Saltar al contenido
      </a>
      <EncabezadoPublico enlaces={enlaces} />
      <main id="contenido" tabIndex={-1}>
        {children}
      </main>
      <PiePublico />
    </div>
  );
}
