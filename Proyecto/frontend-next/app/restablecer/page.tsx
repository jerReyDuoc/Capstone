/** HU-28 · /restablecer#token=… — definir la contraseña nueva (enlace de un solo uso). */
import type { Metadata } from "next";
import { FormRestablecer } from "@/components/acceso/FormRestablecer";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";

export const metadata: Metadata = { title: "Restablecer contraseña", robots: { index: false, follow: false } };

export default function Restablecer() {
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Define una contraseña nueva</h1>
          <p className={s.flujoBajada}>Al guardarla cerraremos todas las sesiones que tengas abiertas.</p>
        </header>
        <div className={s.tarjeta}>
          <FormRestablecer />
        </div>
      </div>
    </PaginaPublica>
  );
}
