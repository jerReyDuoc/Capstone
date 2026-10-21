/** HU-04 · Aviso legal (página estática, misma fuente de texto que el paso 1 del flujo). */
import type { Metadata } from "next";
import Link from "next/link";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { AVISO_LEGAL, AVISO_LEGAL_VERSION } from "@/lib/avisoLegal";

export const dynamic = "force-static";
export const metadata: Metadata = { title: "Aviso legal" };

export default function AvisoLegal() {
  return (
    <PaginaPublica>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Aviso legal</h1>
          <p className={s.flujoBajada}>Versión {AVISO_LEGAL_VERSION}</p>
        </header>
        <article className={s.tarjeta} style={{ display: "grid", gap: 20 }}>
          {AVISO_LEGAL.map((sec) => (
            <section key={sec.titulo}>
              <h2 style={{ fontSize: "var(--fs-lg)" }}>{sec.titulo}</h2>
              <p style={{ marginTop: 6, color: "var(--text-muted)" }}>{sec.texto}</p>
            </section>
          ))}
        </article>
        <p style={{ marginTop: 24 }}>
          <Link href="/comenzar" prefetch={false} className="btn btn-primary">Comenzar autodiagnóstico</Link>
        </p>
      </div>
    </PaginaPublica>
  );
}
