/** HU-27 · /activar#token=… — el usuario definitivo define su contraseña (enlace de un solo uso). */
import type { Metadata } from "next";
import { FormActivacion } from "@/components/activacion/FormActivacion";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";

export const metadata: Metadata = { title: "Activar cuenta", robots: { index: false, follow: false } };

export default function Activar() {
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Activa tu cuenta</h1>
          <p className={s.flujoBajada}>
            Define la contraseña con la que tu empresa accederá al servicio de ComplianceAI. Nunca te la pediremos por
            correo.
          </p>
        </header>
        <div className={s.tarjeta}>
          <FormActivacion />
        </div>
      </div>
    </PaginaPublica>
  );
}
