"use client";

/**
 * HU-19 · Flujo de inicio sin invitación:
 *   1. Aviso legal (HU-04)  →  2. Rubro + verificación (Turnstile)  →  3. Tu clave (+ email opcional)
 *
 * Al terminar el paso 2 el BFF ya creó el usuario temporal y la evaluación y dejó el token
 * en una cookie httpOnly. La clave vive SOLO en el estado de este componente: no se
 * guarda en localStorage/sessionStorage ni en la URL; al salir de la página desaparece.
 */
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent, type RefObject } from "react";
import type { Iniciada, Rubro } from "@/lib/encuesta/contratos";
import { formatearClave } from "@/lib/encuesta/contratos";
import { AVISO_LEGAL, AVISO_LEGAL_VERSION } from "@/lib/avisoLegal";
import { useIniciarEvaluacion } from "@/hooks/useIniciarEvaluacion";
import { Icon } from "@/components/ui/Icon";
import { AvisoError } from "./AvisoError";
import { FormEmailOpcional } from "./FormEmailOpcional";
import { Turnstile, type ControlTurnstile } from "./Turnstile";
import s from "./inicio.module.css";

type Paso = "aviso" | "rubro" | "clave";
const PASOS: { id: Paso; nombre: string }[] = [
  { id: "aviso", nombre: "Aviso legal" },
  { id: "rubro", nombre: "Tu rubro" },
  { id: "clave", nombre: "Tu clave" },
];

function IndicadorPasos({ actual }: { actual: Paso }) {
  const i = PASOS.findIndex((p) => p.id === actual);
  return (
    <ol className={s.pasos} aria-label="Progreso">
      {PASOS.map((p, j) => (
        <li
          key={p.id}
          className={`${s.paso} ${j < i ? s.pasoHecho : ""} ${j === i ? s.pasoActual : ""}`}
          aria-current={j === i ? "step" : undefined}
        >
          <span>
            <span className="sr-only">Paso {j + 1} de {PASOS.length}: </span>
            {p.nombre}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function FlujoInicio({ rubros, siteKey, nonce }: { rubros: Rubro[]; siteKey: string; nonce?: string }) {
  const [paso, setPaso] = useState<Paso>("aviso");
  const [aceptado, setAceptado] = useState(false);
  const [rubroId, setRubroId] = useState<number | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [captchaFallo, setCaptchaFallo] = useState(false);
  const [iniciada, setIniciada] = useState<Iniciada | null>(null);
  const control = useRef<ControlTurnstile | null>(null);
  const titulo = useRef<HTMLHeadingElement>(null);
  const { iniciar, enviando, error, limpiarError } = useIniciarEvaluacion();

  function irA(siguiente: Paso) {
    setPaso(siguiente);
    // Mover el foco al título del paso: lectores de pantalla anuncian el cambio
    requestAnimationFrame(() => titulo.current?.focus());
  }

  async function comenzar(e: FormEvent) {
    e.preventDefault();
    if (!rubroId || !captcha || !aceptado) return;
    const r = await iniciar({ rubroId, avisoVersion: AVISO_LEGAL_VERSION, avisoAceptado: true, captchaToken: captcha });
    // El token de Turnstile es de un solo uso: siempre se pide uno nuevo
    control.current?.reset();
    if (r) {
      setIniciada(r);
      irA("clave");
    }
  }

  return (
    <div>
      <IndicadorPasos actual={paso} />

      {paso === "aviso" ? (
        <section aria-labelledby="t-aviso">
          <h2 id="t-aviso" ref={titulo} tabIndex={-1} className="card-title">Antes de comenzar</h2>
          <p className="card-sub">Lee cómo tratamos la información de tu autodiagnóstico.</p>
          <div className={s.aviso} role="region" aria-label="Aviso legal" tabIndex={0} style={{ marginTop: 16 }} id="aviso">
            {AVISO_LEGAL.map((sec) => (
              <div key={sec.titulo}>
                <h3>{sec.titulo}</h3>
                <p>{sec.texto}</p>
              </div>
            ))}
          </div>
          <p className={s.version}>Versión {AVISO_LEGAL_VERSION}</p>
          <label className={s.check}>
            <input type="checkbox" checked={aceptado} onChange={(e) => setAceptado(e.target.checked)} />
            <span>He leído y acepto el aviso legal.</span>
          </label>
          <div className={s.pie}>
            <span />
            <button type="button" className="btn btn-primary" disabled={!aceptado} onClick={() => irA("rubro")}>
              Continuar
              <Icon name="flecha" />
            </button>
          </div>
        </section>
      ) : null}

      {paso === "rubro" ? (
        <form onSubmit={comenzar} aria-labelledby="t-rubro" noValidate>
          <h2 id="t-rubro" ref={titulo} tabIndex={-1} className="card-title">¿En qué rubro está tu organización?</h2>
          <p className="card-sub">Lo usamos para comparar tu resultado con organizaciones similares, siempre de forma agregada.</p>
          <fieldset className={s.rubros} style={{ marginTop: 16 }}>
            <legend className="sr-only">Rubro</legend>
            <div className={s.rubrosGrid}>
              {rubros.map((r) => (
                <label key={r.id} className={s.rubro}>
                  <input
                    type="radio"
                    name="rubro"
                    value={r.id}
                    checked={rubroId === r.id}
                    onChange={() => {
                      setRubroId(r.id);
                      limpiarError();
                    }}
                  />
                  <span>{r.nombre}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className={s.verificacion}>
            <Turnstile
              siteKey={siteKey}
              nonce={nonce}
              control={control}
              onToken={(t) => {
                setCaptcha(t);
                if (t) setCaptchaFallo(false);
              }}
              onError={() => setCaptchaFallo(true)}
            />
            <p className={s.verificacionEstado} aria-live="polite">
              {captcha ? (
                <>
                  <Icon name="escudo" /> Verificación de seguridad lista.
                </>
              ) : captchaFallo ? (
                "No pudimos cargar la verificación. Revisa tu conexión o desactiva un momento el bloqueador de contenido."
              ) : (
                "Verificando que eres una persona…"
              )}
            </p>
          </div>

          {error ? <AvisoError error={error} onReintentar={limpiarError} /> : null}

          <div className={s.pie}>
            <button type="button" className="btn btn-ghost" onClick={() => irA("aviso")}>
              Atrás
            </button>
            <button type="submit" className="btn btn-primary" disabled={!rubroId || !captcha || enviando}>
              {enviando ? "Creando tu evaluación…" : "Comenzar evaluación"}
            </button>
          </div>
        </form>
      ) : null}

      {paso === "clave" && iniciada ? <PasoClave iniciada={iniciada} tituloRef={titulo} /> : null}
    </div>
  );
}

function PasoClave({ iniciada, tituloRef }: { iniciada: Iniciada; tituloRef: RefObject<HTMLHeadingElement | null> }) {
  const router = useRouter();
  const [guardada, setGuardada] = useState(false);
  const [copiado, setCopiado] = useState<string | null>(null);
  const clave = formatearClave(iniciada.clave);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(`Evaluación N.º ${iniciada.evaluacionId}\nClave: ${clave}`);
      setCopiado("Copiado al portapapeles.");
    } catch {
      setCopiado("No se pudo copiar: anótalo a mano.");
    }
  }

  function descargar() {
    const texto =
      `ComplianceAI · Acceso a tu autodiagnóstico\n\n` +
      `Evaluación N.º: ${iniciada.evaluacionId}\nClave: ${clave}\n\n` +
      `Para continuar: ${window.location.origin}/retomar\n` +
      `Guarda este archivo en un lugar seguro: con estos datos se accede a tus respuestas.\n`;
    const url = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `complianceai-evaluacion-${iniciada.evaluacionId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-labelledby="t-clave">
      <h2 id="t-clave" ref={tituloRef} tabIndex={-1} className="card-title">Tu evaluación está lista</h2>
      <p className="card-sub">
        Guarda estos datos: los necesitas para retomar desde otro momento o dispositivo. <strong>La clave se muestra solo una vez.</strong>
      </p>

      <div className={s.credenciales} style={{ marginTop: 16 }}>
        <div className={s.dato}>
          <span className={s.datoEtiqueta}>Evaluación N.º</span>
          <span className={s.datoValor}>{iniciada.evaluacionId}</span>
        </div>
        <div className={s.dato}>
          <span className={s.datoEtiqueta}>Clave de acceso</span>
          <span className={s.datoValor} aria-label={`Clave: ${clave.split("").join(" ")}`}>{clave}</span>
        </div>
      </div>
      <div className={s.credencialesAcciones}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={copiar}>
          <Icon name="copiar" /> Copiar
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={descargar}>
          <Icon name="descargar" /> Descargar .txt
        </button>
        {copiado ? <span className={s.estadoCopia} role="status">{copiado}</span> : null}
      </div>

      <label className={s.check}>
        <input type="checkbox" checked={guardada} onChange={(e) => setGuardada(e.target.checked)} />
        <span>Guardé mi número de evaluación y mi clave.</span>
      </label>

      <hr className={s.separador} />
      <FormEmailOpcional />

      <div className={s.pie}>
        <span className={s.ayuda}>Tu sesión queda abierta en este navegador por unas horas.</span>
        <button type="button" className="btn btn-primary" disabled={!guardada} onClick={() => router.replace("/encuesta")}>
          Ir a la encuesta
          <Icon name="flecha" />
        </button>
      </div>
    </section>
  );
}
