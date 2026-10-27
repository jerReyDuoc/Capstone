"use client";

/**
 * HU-27/HU-28 · Inicio de sesión del administrador de Therion Labs.
 * Correo y contraseña van en el cuerpo de un POST al BFF; el token queda en una cookie
 * httpOnly que el JavaScript no puede leer.
 */
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";
import { comoErrorAdmin } from "@/lib/admin/api";
import { pedir } from "@/lib/encuesta/cliente";
import s from "./admin.module.css";

export function FormLoginAdmin({ destino = "/admin/clientes", motivo }: { destino?: string; motivo?: string }) {
  const router = useRouter();
  const id = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!email.trim() || !password) {
      setError("Ingresa tu correo y tu contraseña.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await pedir("/bff/admin/login", { method: "POST", json: { email: email.trim(), password } });
      setPassword("");
      router.replace(destino);
    } catch (err) {
      setError(comoErrorAdmin(err).mensaje);
      setEnviando(false);
    }
  }

  return (
    <form className={s.loginTarjeta} onSubmit={enviar} noValidate>
      <div>
        <h1 className="page-title" style={{ fontSize: "var(--fs-2xl)" }}>Panel interno</h1>
        <p className="page-sub">Acceso solo para administradores de Therion Labs.</p>
      </div>
      {motivo === "sesion" ? (
        <p className="callout" role="status">Tu sesión terminó o no existe. Inicia sesión para continuar.</p>
      ) : null}
      <div className={s.campo}>
        <label htmlFor={`${id}-email`}>Correo</label>
        <input id={`${id}-email`} className={s.control} type="email" autoComplete="username" value={email}
               onChange={(e) => setEmail(e.target.value)} maxLength={100} required />
      </div>
      <div className={s.campo}>
        <label htmlFor={`${id}-pw`}>Contraseña</label>
        <input id={`${id}-pw`} className={s.control} type="password" autoComplete="current-password" value={password}
               onChange={(e) => setPassword(e.target.value)} maxLength={200} required />
      </div>
      {error ? <p className={s.errorCampo} role="alert">{error}</p> : null}
      <button className="btn btn-primary" type="submit" disabled={enviando}>
        {enviando ? "Ingresando…" : "Ingresar"}
      </button>
    </form>
  );
}
