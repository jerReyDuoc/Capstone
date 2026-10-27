"use client";

/**
 * HU-28 · Define la contraseña nueva con el enlace de recuperación (/restablecer#token=…).
 *
 * Igual que la activación (HU-27): el token llega en el fragmento, que el navegador no envía
 * al servidor; al cargar se quita de la barra de direcciones y viaja solo en el cuerpo de
 * POST al BFF. Al terminar, todas las sesiones abiertas de la cuenta quedan cerradas.
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { LOGIN_DE, tipoCuenta, type TipoCuenta } from "@/lib/acceso";
import { problemasContrasena, tokenDesdeFragmento } from "@/lib/activacion";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import s from "@/components/inicio/inicio.module.css";

type Estado =
  | { fase: "verificando" }
  | { fase: "invalido"; mensaje: string }
  | { fase: "formulario"; email: string; tipo: TipoCuenta; minimo: number }
  | { fase: "listo"; tipo: TipoCuenta };

interface Verificacion {
  valido: boolean;
  tipo: string;
  email: string;
  password_min: number;
}

export function FormRestablecer() {
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
    pedir<Verificacion>("/bff/recuperacion/verificar", { method: "POST", json: { token: token.current } })
      .then((v) =>
        setEstado({ fase: "formulario", email: v.email, tipo: tipoCuenta(v.tipo), minimo: v.password_min || 12 }),
      )
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
      await pedir("/bff/recuperacion/restablecer", { method: "POST", json: { token: token.current, password } });
      token.current = null;
      setPassword("");
      setConfirmacion("");
      setEstado({ fase: "listo", tipo: estado.tipo });
    } catch (err) {
      const info = err instanceof ErrorBff ? (err.info as unknown as { codigo: string; mensaje: string; problemas?: string[] }) : null;
      if (info?.codigo === "CONTRASENA_DEBIL") {
        setProblemas(info.problemas?.length ? info.problemas : [info.mensaje]);
      } else {
        setEstado({ fase: "invalido", mensaje: info?.mensaje || "No pudimos cambiar tu contraseña. Inténtalo de nuevo." });
      }
    } finally {
      setEnviando(false);
    }
  }

  if (estado.fase === "verificando") return <p role="status">Validando tu enlace…</p>;
  if (estado.fase === "invalido") {
    return (
      <div className={s.error} role="alert">
        <strong>No se puede usar este enlace</strong>
        <p>{estado.mensaje}</p>
        <p style={{ marginTop: 12 }}><Link href="/recuperar" prefetch={false}>Pedir un enlace nuevo</Link></p>
      </div>
    );
  }
  if (estado.fase === "listo") {
    return (
      <div role="status">
        <p className={s.ok}>Tu contraseña quedó actualizada.</p>
        <p style={{ marginTop: 12, color: "var(--text-muted)" }}>
          Por seguridad cerramos todas las sesiones que tenías abiertas. Inicia sesión con la contraseña nueva.
        </p>
        <p style={{ marginTop: 16 }}>
          <Link className="btn btn-primary" href={`${LOGIN_DE[estado.tipo]}?motivo=restablecida`} prefetch={false}>
            Iniciar sesión
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form className={s.formRetomar} onSubmit={enviar} noValidate>
      <p>Cuenta de <strong>{estado.email}</strong>.</p>
      <input type="text" name="username" autoComplete="username" value={estado.email} readOnly hidden />
      <div className={s.campo}>
        <label htmlFor={`${id}-pw`}>Contraseña nueva</label>
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
        {enviando ? "Guardando…" : "Guardar contraseña"}
      </button>
    </form>
  );
}
