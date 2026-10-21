/**
 * HU-19 · /encuesta — zona del encuestado. middleware.ts ya redirige a /retomar si no
 * hay cookie de sesión vigente; aquí se vuelve a comprobar en el servidor.
 */
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { InicioEncuesta } from "@/components/encuesta/InicioEncuesta";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { COOKIE_SESION, sesionDelToken } from "@/lib/servidor/sesion";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Mi evaluación", robots: { index: false } };

export default async function Encuesta() {
  const token = (await cookies()).get(COOKIE_SESION)?.value;
  if (!sesionDelToken(token)) redirect("/retomar?motivo=sesion");
  return (
    <PaginaPublica enlaces={false}>
      <div className={`${s.contenedorEstrecho} ${s.flujo}`}>
        <header className={s.flujoCabecera}>
          <h1 className={s.flujoTitulo}>Mi autodiagnóstico</h1>
          <p className={s.flujoBajada}>Solo tú, con tu clave, puedes ver y editar esta evaluación.</p>
        </header>
        <InicioEncuesta />
      </div>
    </PaginaPublica>
  );
}
