"use client";

/**
 * HU-19 · Retomar desde cualquier dispositivo con N.º de evaluación + clave.
 * Ambos van en el cuerpo de un POST al BFF (nunca en la URL). Acepta la clave con o
 * sin guiones, en minúsculas y con O/0, I/L/1 confundidos (igual que el backend).
 */
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";
import { comoErrorEncuesta, pedir } from "@/lib/encuesta/cliente";
import { formatearClave, parseRetomarEntrada, type ErrorEncuesta } from "@/lib/encuesta/contratos";
import { AvisoError } from "./AvisoError";
import s from "./inicio.module.css";

export function FormRetomar({ motivo }: { motivo?: string }) {
  const router = useRouter();
  const id = useId();
  const [evaluacion, setEvaluacion] = useState("");
  const [clave, setClave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorEncuesta | null>(null);
  const [errorCampo, setErrorCampo] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    const entrada = parseRetomarEntrada({ evaluacionId: evaluacion.trim(), clave });
    if (!entrada.ok) {
      setErrorCampo(entrada.error);
      return;
    }
    setErrorCampo(null);
    setError(null);
    setEnviando(true);
    try {
      await pedir("/bff/encuesta/retomar", { method: "POST", json: entrada.valor });
      setClave(""); // no dejar la clave en memoria más de lo necesario
      router.replace("/encuesta");
    } catch (err) {
      setError(comoErrorEncuesta(err));
      setEnviando(false);
    }
  }

  return (
    <form className={s.formRetomar} onSubmit={enviar} noValidate>
      {motivo === "sesion" ? (
        <p className="callout" role="status">
          Tu sesión en este navegador terminó o no existe. Ingresa con tus datos para continuar: tus respuestas están guardadas.
        </p>
      ) : null}
      <div className={s.campo}>
        <label htmlFor={`${id}-ev`}>Número de evaluación</label>
        <input
          id={`${id}-ev`}
          className={s.input}
          inputMode="numeric"
          autoComplete="off"
          pattern="[0-9]*"
          maxLength={10}
          value={evaluacion}
          onChange={(e) => setEvaluacion(e.target.value.replace(/\D/g, ""))}
          required
        />
      </div>
      <div className={s.campo}>
        <label htmlFor={`${id}-clave`}>Clave de acceso</label>
        <input
          id={`${id}-clave`}
          className={`${s.input} ${s.inputMono}`}
          autoComplete="off"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          placeholder="XXXX-XXXX-XXXX"
          maxLength={20}
          value={clave}
          onChange={(e) => setClave(formatearClave(e.target.value))}
          aria-invalid={errorCampo ? true : undefined}
          aria-describedby={errorCampo ? `${id}-err` : `${id}-ayuda`}
          required
        />
        <p id={`${id}-ayuda`} className={s.ayuda}>La recibiste al comenzar (12 caracteres).</p>
        {errorCampo ? <p id={`${id}-err`} className={s.errorCampo}>{errorCampo}</p> : null}
      </div>
      {error ? <AvisoError error={error} onReintentar={() => setError(null)} /> : null}
      <div>
        <button type="submit" className="btn btn-primary" disabled={enviando || !evaluacion || !clave}>
          {enviando ? "Verificando…" : "Continuar mi evaluación"}
        </button>
      </div>
    </form>
  );
}
