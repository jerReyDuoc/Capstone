/**
 * HU-19 · /comenzar — inicio del autodiagnóstico sin invitación.
 *
 * Server Component dinámico: lee el nonce de la CSP (middleware.ts) para el script de
 * Turnstile y trae los rubros en el servidor (el navegador no hace esa llamada). El
 * JavaScript del flujo solo se descarga al entrar aquí, nunca en la landing.
 */
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { FlujoInicio } from "@/components/inicio/FlujoInicio";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { Icon } from "@/components/ui/Icon";
import { parseRubros, type Rubro } from "@/lib/encuesta/contratos";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Comenzar autodiagnóstico", robots: { index: false } };

/** Clave pública de prueba de Cloudflare (siempre aprueba). Solo fuera de producción. */
const SITEKEY_PRUEBA = "1x00000000000000000000AA";

async function cargarRubros(): Promise<Rubro[] | null> {
  const api = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
  try {
    const res = await fetch(`${api}/api/rubros`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    const rubros = parseRubros(await res.json());
    return rubros.length ? rubros : null;
  } catch {
    return null;
  }
}

export default async function Comenzar() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const siteKey = process.env.TURNSTILE_SITE_KEY || (process.env.NODE_ENV === "production" ? "" : SITEKEY_PRUEBA);
  const rubros = await cargarRubros();

  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <Link href="/" className={s.volver}>
          <Icon name="flecha" /> Volver al inicio
        </Link>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Autodiagnóstico de gobernanza de IA</h1>
          <p className={s.flujoBajada}>Sin registro. Al terminar este paso recibirás una clave para continuar cuando quieras.</p>
        </header>
        <div className={s.tarjeta}>
          {!siteKey ? (
            <div className="state" role="alert">
              <h2>Inicio no disponible</h2>
              <p>Falta configurar la verificación de seguridad (TURNSTILE_SITE_KEY). Avisa al equipo de ComplianceAI.</p>
            </div>
          ) : rubros ? (
            <FlujoInicio rubros={rubros} siteKey={siteKey} nonce={nonce} />
          ) : (
            <div className="state" role="alert">
              <h2>No pudimos cargar el formulario</h2>
              <p>El servicio no responde en este momento. Intenta de nuevo en unos minutos.</p>
              <a className="btn btn-ghost" href="/comenzar">Reintentar</a>
            </div>
          )}
        </div>
      </div>
    </PaginaPublica>
  );
}
