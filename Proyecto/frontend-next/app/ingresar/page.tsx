/**
 * HU-28 · /ingresar — inicio de sesión del usuario definitivo de una empresa cliente.
 * Con una sesión de cliente vigente, middleware.ts lo lleva directo a /empresa.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { FormIngresar } from "@/components/acceso/FormIngresar";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { Icon } from "@/components/ui/Icon";
import { motivoLogin } from "@/lib/acceso";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Iniciar sesión", robots: { index: false, follow: false } };

export default async function Ingresar({ searchParams }: { searchParams: Promise<{ motivo?: string }> }) {
  const { motivo } = await searchParams;
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <Link href="/" className={s.volver}>
          <Icon name="flecha" /> Volver al inicio
        </Link>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Iniciar sesión</h1>
          <p className={s.flujoBajada}>
            Acceso para las empresas que contrataron el servicio de ComplianceAI. Usa el correo y la contraseña que
            definiste al activar tu cuenta.
          </p>
        </header>
        <div className={s.tarjeta}>
          <FormIngresar motivo={motivoLogin(motivo)} />
        </div>
        <p style={{ marginTop: 20, color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>
          ¿Hiciste el autodiagnóstico gratuito?{" "}
          <Link href="/retomar" prefetch={false}>Retoma tu evaluación</Link> con su número y su clave.
        </p>
      </div>
    </PaginaPublica>
  );
}
