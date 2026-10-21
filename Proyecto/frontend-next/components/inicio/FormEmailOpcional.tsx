"use client";

/**
 * HU-19 · Email OPCIONAL. Nunca bloquea: se puede omitir y agregar después desde
 * /encuesta. Se guarda en el backend asociado al usuario temporal anónimo.
 */
import { useId, useState, type FormEvent } from "react";
import { comoErrorEncuesta, pedir } from "@/lib/encuesta/cliente";
import { parseEmailEntrada } from "@/lib/encuesta/contratos";
import { mensajeDeError } from "@/lib/encuesta/errores";
import { Icon } from "@/components/ui/Icon";
import s from "./inicio.module.css";

export function FormEmailOpcional({ compacto = false }: { compacto?: boolean }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [estado, setEstado] = useState<"inicial" | "guardando" | "guardado">("inicial");
  const [error, setError] = useState<string | null>(null);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const valido = parseEmailEntrada({ email });
    if (!valido.ok || valido.valor.email === null) {
      setError(valido.ok ? "Escribe un correo o deja el campo vacío." : valido.error);
      return;
    }
    setEstado("guardando");
    setError(null);
    try {
      await pedir<void>("/bff/encuesta/email", { method: "PATCH", json: { email: valido.valor.email } });
      setEstado("guardado");
    } catch (err) {
      setError(mensajeDeError(comoErrorEncuesta(err)).detalle);
      setEstado("inicial");
    }
  }

  return (
    <form onSubmit={guardar} className={s.campo} noValidate>
      <label htmlFor={`${id}-email`}>Correo electrónico (opcional)</label>
      {!compacto ? (
        <p className={s.ayuda} id={`${id}-ayuda`}>
          Solo para enviarte el informe y ayudarte a retomar. No es necesario para continuar.
        </p>
      ) : null}
      <div className={s.filaEmail}>
        <input
          id={`${id}-email`}
          className={s.input}
          type="email"
          inputMode="email"
          autoComplete="email"
          maxLength={100}
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (estado === "guardado") setEstado("inicial");
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={[!compacto ? `${id}-ayuda` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined}
        />
        <button type="submit" className="btn btn-ghost" disabled={estado === "guardando" || !email.trim()}>
          {estado === "guardando" ? "Guardando…" : "Guardar correo"}
        </button>
      </div>
      {error ? <p id={`${id}-error`} className={s.errorCampo}>{error}</p> : null}
      {estado === "guardado" ? (
        <p className={s.ok} role="status">
          <Icon name="check" /> Correo guardado.
        </p>
      ) : null}
    </form>
  );
}
