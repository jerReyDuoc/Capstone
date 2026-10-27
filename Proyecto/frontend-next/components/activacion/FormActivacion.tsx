"use client";

/**
 * HU-27 · El usuario definitivo define su contraseña con el enlace del correo.
 *
 * El token llega en el fragmento (#token=…), que el navegador no envía al servidor. Al
 * cargar se quita de la barra de direcciones (history.replaceState) para que no quede a
 * la vista ni en el historial; luego viaja solo en el cuerpo de POST al BFF.
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { problemasContrasena, tokenDesdeFragmento } from "@/lib/activacion";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import s from "@/components/inicio/inicio.module.css";

type Estado =
  | { fase: "verificando" }
  | { fase: "invalido"; mensaje: string }
  | { fase: "formulario"; email: string; empresa: string | null; minimo: number }
  | { fase: "listo" };

interface Verificacion {
  valido: boolean;
  email: string;
  empresa: string | null;
  password_min: number;
}

export function FormActivacion() {
  const id = useId();
  const token = useRef<string | null>(null);
  const [estado, setEstado] = useState<Estado>({ fase: "verificando" });
  const [password, setPassword] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [problemas, setProblemas] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    token.current = tokenDesdeFragmento(window.location.hash);
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
    if (!token.current) {
      setEstado({ fase: "invalido", mensaje: "El enlace está incompleto. Ábrelo directamente desde el correo." });
      return;
    }
    pedir<Verificacion>("/bff/activacion/verificar", { method: "POST", json: { token: token.current } })
      .then((v) => setEstado({ fase: "formulario", email: v.email, empresa: v.empresa, minimo: v.password_min || 12 }))
      .catch((e) =>
        setEstado({
          fase: "invalido",
          mensaje: (e instanceof ErrorBff && e.info.mensaje) || "No pudimos validar el enlace. Inténtalo de nuevo más tarde.",
        }),
      );
  }, []);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando || estado.fase !== "formulario" || !token.current) return;
    const locales = problemasContrasena(password, estado.minimo);
    if (password !== confirmacion) locales.push("Las contraseñas no coinciden.");
    setProblemas(locales);
    if (locales.length) return;
    setEnviando(true);
    try {
      await pedir("/bff/activacion/activar", { method: "POST", json: { token: token.current, password } });
      token.current = null;
      setPassword("");
      setConfirmacion("");
      setEstado({ fase: "listo" });
    } catch (err) {
      const info = err instanceof ErrorBff ? (err.info as unknown as { codigo: string; mensaje: string; problemas?: string[] }) : null;
      if (info?.codigo === "CONTRASENA_DEBIL") {
        setProblemas(info.problemas?.length ? info.problemas : [info.mensaje]);
      } else {
        setEstado({ fase: "invalido", mensaje: info?.mensaje || "No pudimos activar tu cuenta. Inténtalo de nuevo." });
      }
    } finally {
      setEnviando(false);
    }
  }

  if (estado.fase === "verificando") return <p role="status">Validando tu enlace…</p>;
  if (estado.fase === "invalido") {
    return (
      <div className={`${s.error}`} role="alert">
        <strong>No se puede usar este enlace</strong>
        <p>{estado.mensaje}</p>
      </div>
    );
  }
  if (estado.fase === "listo") {
    return (
      <div role="status">
        <p className={s.ok}>Tu cuenta quedó activa.</p>
        <p style={{ marginTop: 12, color: "var(--text-muted)" }}>
          Ya puedes iniciar sesión con tu correo y la contraseña que definiste. El enlace dejó de funcionar.
        </p>
        <p style={{ marginTop: 16 }}>
          {/* HU-28 */}
          <Link className="btn btn-primary" href="/ingresar?motivo=activada" prefetch={false}>Iniciar sesión</Link>
        </p>
      </div>
    );
  }

  return (
    <form className={s.formRetomar} onSubmit={enviar} noValidate>
      <p>
        Cuenta de <strong>{estado.email}</strong>
        {estado.empresa ? <> en <strong>{estado.empresa}</strong></> : null}.
      </p>
      {/* campo de usuario oculto: ayuda a los gestores de contraseñas a guardarla con el correo */}
      <input type="text" name="username" autoComplete="username" value={estado.email} readOnly hidden />
      <div className={s.campo}>
        <label htmlFor={`${id}-pw`}>Nueva contraseña</label>
        <input id={`${id}-pw`} className={s.input} type="password" autoComplete="new-password" value={password}
               maxLength={128} onChange={(e) => setPassword(e.target.value)}
               aria-describedby={`${id}-ayuda`} aria-invalid={problemas.length > 0} />
        <span id={`${id}-ayuda`} className={s.ayuda}>
          Al menos {estado.minimo} caracteres, con letras y números. No uses tu nombre ni tu correo.
        </span>
      </div>
      <div className={s.campo}>
        <label htmlFor={`${id}-pw2`}>Repite la contraseña</label>
        <input id={`${id}-pw2`} className={s.input} type="password" autoComplete="new-password" value={confirmacion}
               maxLength={128} onChange={(e) => setConfirmacion(e.target.value)} aria-invalid={problemas.length > 0} />
      </div>
      {problemas.length ? (
        <ul className={s.errorCampo} role="alert" style={{ margin: 0, paddingLeft: 20 }}>
          {problemas.map((p) => <li key={p}>{p}</li>)}
        </ul>
      ) : null}
      <button className="btn btn-primary" type="submit" disabled={enviando}>
        {enviando ? "Activando…" : "Activar mi cuenta"}
      </button>
    </form>
  );
}
