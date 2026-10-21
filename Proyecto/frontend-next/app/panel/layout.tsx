import { Suspense } from "react";
import { Sidebar } from "@/components/shell/Sidebar";
import { Cargando } from "@/components/ui/Basicos";
import { PanelProvider } from "@/hooks/usePanel";

export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return (
    // useSearchParams (en PanelProvider) exige un límite de Suspense en Next 15
    <Suspense fallback={<div className="main"><Cargando /></div>}>
      <PanelProvider>
        <a href="#contenido" className="skip-link">
          Saltar al contenido
        </a>
        <div className="shell">
          <Sidebar />
          <main id="contenido" className="main" tabIndex={-1}>
            <div className="main-inner">{children}</div>
          </main>
        </div>
      </PanelProvider>
    </Suspense>
  );
}
