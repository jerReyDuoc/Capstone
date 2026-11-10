/**
 * HU-32 · /mis-derechos — puerta pública a los derechos ARCOP (Ley 21.719).
 *
 * Una sola página para cualquiera que llegue desde la portada, el aviso legal o un correo:
 *   1. "Hice el autodiagnóstico": N.º de evaluación + clave (el mismo ingreso de /retomar) y
 *      de ahí a /panel/mis-derechos.
 *   2. "Tengo cuenta de empresa": a /ingresar (luego "Mis derechos" en el menú).
 *   3. "Ya tengo un código": consulta pública del estado, sin ingresar.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { SeguimientoPublico } from "@/components/arcop/SeguimientoPublico";
import s from "@/components/arcop/arcop.module.css";
import { FormRetomar } from "@/components/inicio/FormRetomar";
import { PaginaPublica } from "@/components/publico/Marco";
import p from "@/components/publico/publico.module.css";
import { Icon } from "@/components/ui/Icon";
import { DERECHOS, TIPOS_ARCOP } from "@/lib/arcop";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Mis derechos sobre mis datos",
  description: "Accede, corrige, llévate o elimina tus datos personales (derechos ARCOP, Ley 21.719).",
};

export default async function MisDerechos({ searchParams }: { searchParams: Promise<{ motivo?: string }> }) {
  const { motivo } = await searchParams;
  return (
    <PaginaPublica>
      <div className={`${p.contenedor} ${p.flujo}`}>
        <Link href="/" className={p.volver}>
          <Icon name="flecha" /> Volver al inicio
        </Link>
        <header className={p.flujoCabecera}>
          <span className="eyebrow">Privacidad · Ley 21.719</span>
          <h1 className={p.flujoTitulo}>Mis derechos sobre mis datos</h1>
          <p className={p.flujoBajada}>
            Puedes pedir ver, corregir, llevarte o eliminar tus datos personales. Ingresa para enviar una solicitud o
            consulta el estado de una que ya enviaste.
          </p>
        </header>

        <div className={s.puertas}>
          <section className={`${p.tarjeta} ${s.puerta}`} aria-labelledby="titulo-clave">
            <div>
              <h2 id="titulo-clave" className={s.puertaTitulo}>Hice el autodiagnóstico</h2>
              <p className={s.puertaBajada}>
                Ingresa con el número de evaluación y la clave que recibiste al comenzar. No necesitas cuenta.
              </p>
            </div>
            <FormRetomar destino="derechos" motivo={motivo === "sesion" ? "sesion" : undefined} />
          </section>

          <div className={s.columna}>
            <section className={`${p.tarjeta} ${s.puerta}`} aria-labelledby="titulo-cliente">
              <div>
                <h2 id="titulo-cliente" className={s.puertaTitulo}>Tengo cuenta de empresa</h2>
                <p className={s.puertaBajada}>
                  Ingresa con tu correo y contraseña. Encontrarás «Mis derechos» en el menú, aunque el contrato de tu
                  empresa haya terminado.
                </p>
              </div>
              <div>
                <Link href="/ingresar" className="btn btn-ghost" prefetch={false}>
                  <Icon name="usuario" />
                  Ingresar como cliente
                </Link>
              </div>
            </section>

            <section id="seguimiento" className={`${p.tarjeta} ${s.puerta}`} aria-labelledby="titulo-seguimiento">
              <div>
                <h2 id="titulo-seguimiento" className={s.puertaTitulo}>Ya envié una solicitud</h2>
                <p className={s.puertaBajada}>Consulta en qué va con tu código de seguimiento, sin ingresar.</p>
              </div>
              <SeguimientoPublico />
            </section>
          </div>
        </div>

        <section aria-labelledby="titulo-que-puedo" style={{ marginTop: "var(--sp-10)", display: "grid", gap: "var(--sp-5)" }}>
          <h2 id="titulo-que-puedo" className={s.puertaTitulo}>¿Qué puedo pedir?</h2>
          <ul className={s.resumenDerechos}>
            {TIPOS_ARCOP.map((t) => (
              <li key={t}>
                <Icon name={DERECHOS[t].icono} aria-hidden="true" />
                <strong>{DERECHOS[t].accion}</strong>
                <span>{DERECHOS[t].descripcion}</span>
              </li>
            ))}
          </ul>
          <p className={s.ayuda}>
            Respondemos en un máximo de 30 días corridos (prorrogables una vez por 30 días más, con aviso); el bloqueo
            temporal, en 2 días hábiles. Más información en el <Link href="/aviso-legal" prefetch={false}>aviso legal</Link>.
          </p>
        </section>
      </div>
    </PaginaPublica>
  );
}
