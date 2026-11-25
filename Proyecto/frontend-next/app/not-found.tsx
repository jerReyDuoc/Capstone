/** 404 — página inexistente. Sin esto Next muestra su pantalla genérica en inglés. */
import type { Metadata } from "next";
import Link from "next/link";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";

export const metadata: Metadata = { title: "Página no encontrada", robots: { index: false } };

export default function NoEncontrada() {
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>No encontramos esta página</h1>
          <p className={s.flujoBajada}>El enlace puede estar incompleto o la página ya no existe.</p>
        </header>
        <p>
          <Link href="/" className="btn btn-primary">Volver al inicio</Link>
        </p>
      </div>
    </PaginaPublica>
  );
}
