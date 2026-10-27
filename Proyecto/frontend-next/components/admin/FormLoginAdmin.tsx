"use client";

/**
 * HU-27/HU-28 · Inicio de sesión del administrador de Therion Labs.
 * Correo y contraseña van en el cuerpo de un POST al BFF; el token queda en una cookie
 * httpOnly que el JavaScript no puede leer. HU-28: los mensajes no revelan si el correo
 * existe, los intentos fallidos se limitan (429) y hay recuperación de contraseña.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useRef, useState, type FormEvent } from "react";
import { INICIO_DE, mensajeLogin, TEXTO_MOTIVO, type MotivoLogin } from "@/lib/acceso";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import s from "./admin.module.css";

export function FormLoginAdmin({ destino = INICIO_DE.admin, motivo }: { destino?: string; motivo?: MotivoLogin }) {
  const router = useRouter();
  const id = useId();
  const refPassword = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!email.trim() || !password) {
      setError(mensajeLogin("DATOS_INVALIDOS"));
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await pedir("/bff/admin/login", { method: "POST", json: { email: email.trim(), password } });
      setPassword("");
      router.replace(destino);
      router.refresh();
    } catch (err) {
      const info = err instanceof ErrorBff ? err.info : null;
      setError(mensajeLogin(info?.codigo ?? "DESCONOCIDO", info?.reintentarEnS));
      setPassword("");
      setEnviando(false);
      refPassword.current?.focus();
    }
  }

  return (
    <form className={s.loginTarjeta} onSubmit={enviar} noValidate>
      <div>
        <h1 className="page-title" style={{ fontSize: "var(--fs-2xl)" }}>Panel interno</h1>
        <p className="page-sub">Acceso solo para administradores de Therion Labs.</p>
      </div>
      {motivo ? (
        <p className="callout" role="status">{TEXTO_MOTIVO[motivo]}</p>
      ) : null}
      <div className={s.campo}>
        <label htmlFor={`${id}-email`}>Correo</label>
        <input id={`${id}-email`} className={s.control} type="email" autoComplete="username" value={email}
               onChange={(e) => setEmail(e.target.value)} maxLength={100} required aria-invalid={Boolean(error)} />
      </div>
      <div className={s.campo}>
        <label htmlFor={`${id}-pw`}>Contraseña</label>
        <input id={`${id}-pw`} ref={refPassword} className={s.control} type="password" autoComplete="current-password"
               value={password} onChange={(e) => setPassword(e.target.value)} maxLength={200} required
               aria-invalid={Boolean(error)} />
      </div>
      {error ? <p className={s.errorCampo} role="alert">{error}</p> : null}
      <button className="btn btn-primary" type="submit" disabled={enviando}>
        {enviando ? "Ingresando…" : "Ingresar"}
      </button>
      <p className={s.ayuda}>
        <Link href="/recuperar?tipo=admin" prefetch={false}>¿Olvidaste tu contraseña?</Link>
      </p>
    </form>
  );
}
