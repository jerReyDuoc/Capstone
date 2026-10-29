/**
 * Correcciones 29-10 · Esqueleto del espacio de la empresa: la misma barra lateral del panel
 * y las páginas Mi empresa, Mis evaluaciones y Mis documentos. El grupo (espacio) no cambia
 * las URL; la reevaluación (/empresa/evaluacion/[id]) queda fuera para que el cuestionario
 * conserve todo el ancho.
 * Lo protege middleware.ts (sin sesión de cliente → /ingresar); la autorización real la hace
 * FastAPI en cada llamada.
 */
import type { Metadata } from "next";
import { Sidebar } from "@/components/shell/Sidebar";
import { EspacioEmpresaProvider } from "@/components/empresa/EspacioEmpresaContexto";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function EspacioLayout({ children }: { children: React.ReactNode }) {
  return (
    <EspacioEmpresaProvider>
      <a href="#contenido" className="skip-link">
        Saltar al contenido
      </a>
      <div className="shell">
        <Sidebar />
        <main id="contenido" className="main" tabIndex={-1}>
          <div className="main-inner">{children}</div>
        </main>
      </div>
    </EspacioEmpresaProvider>
  );
}
