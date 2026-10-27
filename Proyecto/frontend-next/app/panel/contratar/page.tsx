/**
 * HU-31 · /panel/contratar — "Contratar la plataforma" desde los resultados (sin cuenta).
 *
 * Server Component dinámico: lee el nonce de la CSP (middleware.ts la trata como página del
 * flujo, igual que /comenzar) para cargar Turnstile, y la clave pública del CAPTCHA.
 * Vive dentro del panel (misma barra lateral) para que la persona no sienta que sale de
 * sus resultados.
 */
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { FormContratacion } from "@/components/contratacion/FormContratacion";
import s from "@/components/contratacion/contratacion.module.css";
import { PageHeader } from "@/components/shell/PageHeader";
import { Icon, type IconName } from "@/components/ui/Icon";
import { BENEFICIOS } from "@/lib/contratacion";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Contratar la plataforma", robots: { index: false } };

/** Clave pública de prueba de Cloudflare (siempre aprueba). Solo fuera de producción. */
const SITEKEY_PRUEBA = "1x00000000000000000000AA";

export default async function PaginaContratar() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const siteKey = process.env.TURNSTILE_SITE_KEY || (process.env.NODE_ENV === "production" ? "" : SITEKEY_PRUEBA);

  return (
    <>
      <Link href="/panel" className="btn btn-ghost btn-sm" style={{ marginBottom: "var(--sp-4)" }}>
        <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
        Volver a mis resultados
      </Link>
      <PageHeader
        eyebrow="Siguiente paso"
        titulo="Contratar la plataforma"
        subtitulo="Déjanos tus datos y el equipo de Therion Labs te contactará para activar el servicio de tu empresa. Enviar la solicitud no tiene costo ni te compromete."
      />

      <div className={s.layout}>
        <aside className={s.aside} aria-label="Qué incluye y cómo sigue">
          <section className="card" aria-labelledby="titulo-incluye">
            <h2 id="titulo-incluye" className="card-title">Qué incluye el servicio</h2>
            <ul className={s.beneficios}>
              {BENEFICIOS.map((b) => (
                <li key={b.titulo} className={s.beneficio}>
                  <Icon name={b.icono as IconName} />
                  <div>
                    <strong>{b.titulo}</strong>
                    <span>{b.texto}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <section className="card" aria-labelledby="titulo-pasos">
            <h2 id="titulo-pasos" className="card-title">Cómo sigue</h2>
            <ol className={s.pasos}>
              <li>
                <div>
                  <strong>Recibimos tu solicitud</strong>
                  <span>Llega al equipo comercial junto con tu diagnóstico.</span>
                </div>
              </li>
              <li>
                <div>
                  <strong>Te contactamos</strong>
                  <span>Conversamos sobre tu empresa y las condiciones del servicio.</span>
                </div>
              </li>
              <li>
                <div>
                  <strong>Activas la cuenta de tu empresa</strong>
                  <span>Si contratan, recibes un enlace de activación y tu evaluación pasa a la cuenta, sin repetirla.</span>
                </div>
              </li>
            </ol>
          </section>
        </aside>

        <div>
          {siteKey ? (
            <FormContratacion siteKey={siteKey} nonce={nonce} />
          ) : (
            <div className="state" role="alert">
              <h2>Formulario no disponible</h2>
              <p>Falta configurar la verificación de seguridad (TURNSTILE_SITE_KEY). Avisa al equipo de ComplianceAI.</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
