/** HU-27/HU-28 · /admin/login — inicio de sesión del panel interno. */
import type { Metadata } from "next";
import { FormLoginAdmin } from "@/components/admin/FormLoginAdmin";
import s from "@/components/admin/admin.module.css";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Iniciar sesión", robots: { index: false, follow: false } };

export default async function LoginAdmin({ searchParams }: { searchParams: Promise<{ motivo?: string }> }) {
  const { motivo } = await searchParams;
  return (
    <main id="contenido" className={s.pagina}>
      <div className={s.login}>
        <FormLoginAdmin motivo={motivo === "sesion" ? "sesion" : undefined} />
      </div>
    </main>
  );
}
