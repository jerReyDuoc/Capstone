/** HU-19 · /retomar — continuar el autodiagnóstico desde cualquier dispositivo. */
import type { Metadata } from "next";
import Link from "next/link";
import { FormRetomar } from "@/components/inicio/FormRetomar";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { Icon } from "@/components/ui/Icon";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Retomar evaluación", robots: { index: false } };

export default async function Retomar({ searchParams }: { searchParams: Promise<{ motivo?: string }> }) {
  const { motivo } = await searchParams;
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <Link href="/" className={s.volver}>
          <Icon name="flecha" /> Volver al inicio
        </Link>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Retomar mi evaluación</h1>
          <p className={s.flujoBajada}>Usa el número de evaluación y la clave que guardaste al comenzar.</p>
        </header>
        <div className={s.tarjeta}>
          <FormRetomar motivo={motivo === "sesion" ? "sesion" : undefined} />
        </div>
        <p style={{ marginTop: 20, color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>
          ¿Aún no tienes una evaluación?{" "}
          <Link href="/comenzar" prefetch={false}>Comienza una nueva</Link>.
        </p>
        {/* HU-32: con el mismo número y clave se ejercen los derechos ARCOP */}
        <p style={{ marginTop: 8, color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>
          ¿Quieres ver, corregir o eliminar tus datos?{" "}
          <Link href="/mis-derechos" prefetch={false}>Ejerce tus derechos</Link>.
        </p>
      </div>
    </PaginaPublica>
  );
}
