"use client";

/**
 * HU-28 · Inicio de sesión del usuario definitivo de una empresa cliente.
 *
 * Correo y contraseña van en el cuerpo de un POST al BFF (/bff/cliente/login); el token queda
 * en una cookie httpOnly que el JavaScript no puede leer. Los mensajes de error nunca dicen si
 * el correo existe: "Correo o contraseña incorrectos." en ambos casos.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useRef, useState, type FormEvent } from "react";
import { INICIO_DE, mensajeLogin, TEXTO_MOTIVO, type MotivoLogin } from "@/lib/acceso";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import s from "@/components/inicio/inicio.module.css";

export function FormIngresar({ motivo }: { motivo?: MotivoLogin }) {
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
      await pedir("/bff/cliente/login", { method: "POST", json: { email: email.trim(), password } });
      setPassword("");
      router.replace(INICIO_DE.cliente);
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
    <form className={s.formRetomar} onSubmit={enviar} noValidate aria-describedby={error ? `${id}-error` : undefined}>
      {motivo ? (
        <p className="callout" role="status">{TEXTO_MOTIVO[motivo]}</p>
      ) : null}
      <div className={s.campo}>
        <label htmlFor={`${id}-email`}>Correo</label>
        <input id={`${id}-email`} className={s.input} type="email" autoComplete="username" inputMode="email"
               value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} required
               aria-invalid={Boolean(error)} />
      </div>
      <div className={s.campo}>
        <label htmlFor={`${id}-pw`}>Contraseña</label>
        <input id={`${id}-pw`} ref={refPassword} className={s.input} type="password" autoComplete="current-password"
               value={password} onChange={(e) => setPassword(e.target.value)} maxLength={200} required
               aria-invalid={Boolean(error)} />
      </div>
      {error ? <p id={`${id}-error`} className={s.errorCampo} role="alert">{error}</p> : null}
      <button className="btn btn-primary" type="submit" disabled={enviando}>
        {enviando ? "Ingresando…" : "Ingresar"}
      </button>
      <p className={s.ayuda}>
        <Link href="/recuperar" prefetch={false}>¿Olvidaste tu contraseña?</Link>
      </p>
    </form>
  );
}
