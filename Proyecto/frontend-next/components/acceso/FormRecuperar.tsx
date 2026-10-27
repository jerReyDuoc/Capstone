"use client";

/**
 * HU-28 · "¿Olvidaste tu contraseña?": pide el enlace de recuperación por correo.
 *
 * La respuesta es la misma exista o no la cuenta (no se puede usar para averiguar qué
 * correos están registrados). El enlace sirve una vez y vence pronto.
 */
import Link from "next/link";
import { useId, useState, type FormEvent } from "react";
import { emailValido, LOGIN_DE, type TipoCuenta } from "@/lib/acceso";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import s from "@/components/inicio/inicio.module.css";

export function FormRecuperar({ tipo }: { tipo: TipoCuenta }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!emailValido(email)) {
      setError("Escribe un correo válido.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const r = await pedir<{ mensaje: string }>("/bff/recuperacion/solicitar", {
        method: "POST",
        json: { tipo, email: email.trim() },
      });
      setListo(r.mensaje);
    } catch (err) {
      const info = err instanceof ErrorBff ? err.info : null;
      setError(
        info?.codigo === "DEMASIADOS_INTENTOS"
          ? "Hiciste demasiadas solicitudes seguidas. Espera un rato antes de volver a intentarlo."
          : "No pudimos procesar la solicitud. Inténtalo de nuevo en unos minutos.",
      );
    } finally {
      setEnviando(false);
    }
  }

  if (listo) {
    return (
      <div role="status">
        <p className={s.ok}>Revisa tu correo</p>
        <p style={{ marginTop: 12, color: "var(--text-muted)" }}>{listo}</p>
        <p style={{ marginTop: 12, color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>
          El enlace sirve una sola vez y vence en pocos minutos. Si no llega, vuelve a pedirlo.
        </p>
        <p style={{ marginTop: 16 }}>
          <Link href={LOGIN_DE[tipo]} prefetch={false}>Volver a iniciar sesión</Link>
        </p>
      </div>
    );
  }

  return (
    <form className={s.formRetomar} onSubmit={enviar} noValidate>
      <div className={s.campo}>
        <label htmlFor={`${id}-email`}>Correo de tu cuenta</label>
        <input id={`${id}-email`} className={s.input} type="email" autoComplete="username" inputMode="email"
               value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} required
               aria-invalid={Boolean(error)} aria-describedby={`${id}-ayuda`} />
        <span id={`${id}-ayuda`} className={s.ayuda}>Te enviaremos un enlace para definir una contraseña nueva.</span>
      </div>
      {error ? <p className={s.errorCampo} role="alert">{error}</p> : null}
      <button className="btn btn-primary" type="submit" disabled={enviando}>
        {enviando ? "Enviando…" : "Enviar enlace"}
      </button>
      <p className={s.ayuda}>
        <Link href={LOGIN_DE[tipo]} prefetch={false}>Volver a iniciar sesión</Link>
      </p>
    </form>
  );
}
