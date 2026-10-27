/** HU-28 · /recuperar[?tipo=admin] — pedir el enlace para restablecer la contraseña. */
import type { Metadata } from "next";
import { FormRecuperar } from "@/components/acceso/FormRecuperar";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { tipoCuenta } from "@/lib/acceso";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Recuperar contraseña", robots: { index: false, follow: false } };

export default async function Recuperar({ searchParams }: { searchParams: Promise<{ tipo?: string }> }) {
  const tipo = tipoCuenta((await searchParams).tipo);
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>¿Olvidaste tu contraseña?</h1>
          <p className={s.flujoBajada}>
            {tipo === "admin"
              ? "Escribe el correo de tu cuenta de administrador de Therion Labs."
              : "Escribe el correo con que tu empresa accede a ComplianceAI."}{" "}
            Nunca te pediremos tu contraseña por correo.
          </p>
        </header>
        <div className={s.tarjeta}>
          <FormRecuperar tipo={tipo} />
        </div>
      </div>
    </PaginaPublica>
  );
}
