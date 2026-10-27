"use client";

/**
 * HU-31 · Formulario "Contratar la plataforma" (/panel/contratar).
 *
 * Criterio 1: nombre, cargo, empresa, correo y teléfono opcional.
 * Criterio 2: DOS autorizaciones separadas, cada una con su texto y su versión (las lee del
 *             backend; si el PO cambia un texto, aquí aparece solo el nuevo).
 * Criterio 3: CAPTCHA (Turnstile, acción "solicitar_contratacion") + los límites por IP del
 *             backend, iguales a los de la encuesta pública.
 *
 * Accesibilidad (WCAG 2.1 AA): etiquetas visibles, autocomplete, errores con texto e icono
 * enlazados por aria-describedby, resumen de errores que recibe el foco y enlaza a cada
 * campo, foco al título de la confirmación, nada depende solo del color y áreas táctiles
 * de 44 px. El orden de tabulación sigue el orden visual.
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Turnstile, type ControlTurnstile } from "@/components/inicio/Turnstile";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { enviarSolicitud, obtenerConsentimientos, useSolicitudContratacion } from "@/hooks/useSolicitudContratacion";
import {
  campoDelError,
  cuerpoSolicitud,
  ESTADO_PUBLICO,
  FORMULARIO_VACIO,
  LIMITES,
  ORDEN_CAMPOS,
  primerError,
  validarFormulario,
  type CampoFormulario,
  type Consentimientos,
  type FormularioContratacion,
  type SolicitudPublica,
} from "@/lib/contratacion";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import s from "./contratacion.module.css";

const ACCION_CAPTCHA = "solicitar_contratacion";

const ETIQUETA_RESUMEN: Record<CampoFormulario, string> = {
  nombre: "Nombre y apellido",
  cargo: "Cargo",
  empresa: "Empresa",
  email: "Correo de trabajo",
  telefono: "Teléfono",
  aceptaContacto: "Autorización de contacto comercial",
  aceptaMigracion: "Autorización para asociar la evaluación",
};

export function FormContratacion({ siteKey, nonce }: { siteKey: string; nonce?: string }) {
  const { modo, evaluacionId, estado: panel, href } = usePanel();
  const encuestado = modo === "encuestado";
  const { estado, recargar } = useSolicitudContratacion(evaluacionId, encuestado);
  const [textos, setTextos] = useState<Consentimientos | null>(null);
  const [errorTextos, setErrorTextos] = useState(false);

  const cargarTextos = useCallback(async (signal?: AbortSignal) => {
    setErrorTextos(false);
    try {
      setTextos(await obtenerConsentimientos(signal));
    } catch (e) {
      if ((e as Error).name !== "AbortError") setErrorTextos(true);
    }
  }, []);

  useEffect(() => {
    if (!encuestado) return;
    const ctrl = new AbortController();
    void cargarTextos(ctrl.signal);
    return () => ctrl.abort();
  }, [encuestado, cargarTextos]);

  if (modo === "detectando" || (encuestado && (estado.tipo === "cargando" || panel.tipo === "cargando"))) {
    return (
      <div className="card" role="status">
        <p className={s.listo}>Cargando…</p>
      </div>
    );
  }

  if (!encuestado) {
    return (
      <Estado icono="info" titulo="Esta página es para quien hizo el autodiagnóstico">
        <p>
          El formulario de contratación aparece en los resultados de cada encuestado. Las solicitudes recibidas se
          gestionan en la bandeja del panel interno.
        </p>
        <Link href="/admin/clientes" className="btn btn-ghost" prefetch={false}>
          Ir a la bandeja de solicitudes
        </Link>
      </Estado>
    );
  }

  if (panel.tipo === "sin-resumen" || panel.tipo === "sin-evaluaciones") {
    return (
      <Estado icono="info" titulo="Primero termina tu evaluación">
        <p>Podrás pedir la contratación cuando completes el cuestionario y veas tus resultados.</p>
        <a href="/encuesta" className="btn btn-primary">
          Continuar mi cuestionario
          <Icon name="flecha" />
        </a>
      </Estado>
    );
  }

  if (estado.tipo === "enviada") {
    return <Confirmacion solicitud={estado.solicitud} volver={href("/panel")} recienEnviada={false} />;
  }

  if (estado.tipo === "error" || errorTextos) {
    return (
      <Estado icono="alerta" titulo="No pudimos cargar el formulario" rol="alert">
        <p>Revisa tu conexión e inténtalo de nuevo. Tus resultados siguen disponibles en el panel.</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            recargar();
            void cargarTextos();
          }}
        >
          <Icon name="refrescar" />
          Intentar de nuevo
        </button>
      </Estado>
    );
  }

  if (!textos || evaluacionId == null) {
    return (
      <div className="card" role="status">
        <p className={s.listo}>Cargando…</p>
      </div>
    );
  }

  return (
    <Formulario
      evaluacionId={evaluacionId}
      textos={textos}
      siteKey={siteKey}
      nonce={nonce}
      volver={href("/panel")}
      onYaEnviada={recargar}
      recargarTextos={() => cargarTextos()}
    />
  );
}

/* ------------------------------------------------------------------ formulario */
function Formulario({
  evaluacionId,
  textos,
  siteKey,
  nonce,
  volver,
  onYaEnviada,
  recargarTextos,
}: {
  evaluacionId: number;
  textos: Consentimientos;
  siteKey: string;
  nonce?: string;
  volver: string;
  onYaEnviada: () => void;
  recargarTextos: () => Promise<void>;
}) {
  const id = useId();
  const ids = Object.fromEntries(ORDEN_CAMPOS.map((c) => [c, `${id}-${c}`])) as Record<CampoFormulario, string>;
  const [f, setF] = useState<FormularioContratacion>(FORMULARIO_VACIO);
  const [errores, setErrores] = useState<Partial<Record<CampoFormulario, string>>>({});
  const [mostrarResumen, setMostrarResumen] = useState(false);
  const [errorEnvio, setErrorEnvio] = useState<ErrorEncuesta | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [captchaFallo, setCaptchaFallo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [enviada, setEnviada] = useState<SolicitudPublica | null>(null);
  const control = useRef<ControlTurnstile | null>(null);
  const refResumen = useRef<HTMLDivElement>(null);

  // El resumen recibe el foco al aparecer (los lectores de pantalla lo anuncian)
  useEffect(() => {
    if (mostrarResumen) refResumen.current?.focus();
  }, [mostrarResumen, errores]);

  const cambiar = <K extends CampoFormulario>(campo: K, valor: FormularioContratacion[K]) => {
    setF((prev) => ({ ...prev, [campo]: valor }));
    // El error de un campo se quita cuando la persona lo corrige (no se recalcula en cada tecla)
    if (errores[campo]) {
      const siguiente = validarFormulario({ ...f, [campo]: valor });
      setErrores((prev) => ({ ...prev, [campo]: siguiente[campo] }));
    }
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorEnvio(null);
    const encontrados = validarFormulario(f);
    setErrores(encontrados);
    if (primerError(encontrados)) {
      setMostrarResumen(true);
      return;
    }
    setMostrarResumen(false);
    if (!captcha) {
      setErrorEnvio({ codigo: captchaFallo ? "CAPTCHA_INVALIDO" : "CAPTCHA_PENDIENTE", mensaje: "" });
      return;
    }
    setEnviando(true);
    try {
      const s = await enviarSolicitud(cuerpoSolicitud(evaluacionId, f, textos, captcha));
      // La confirmación la muestra este componente (con el foco en su título). No se avisa al
      // padre: cambiaría a su propia vista y desmontaría esta confirmación.
      setEnviada(s);
    } catch (err) {
      const info = comoErrorEncuesta(err);
      if (info.codigo === "SOLICITUD_EXISTENTE") {
        onYaEnviada();
        return;
      }
      const campo = campoDelError(info.codigo, info.campo, info.consentimiento);
      if (info.codigo === "CONSENTIMIENTO_DESACTUALIZADO") {
        // Texto nuevo: hay que leerlo y aceptarlo otra vez
        await recargarTextos();
        setF((prev) => ({ ...prev, aceptaContacto: campo === "aceptaContacto" ? false : prev.aceptaContacto,
                                    aceptaMigracion: campo === "aceptaMigracion" ? false : prev.aceptaMigracion }));
      }
      if (campo) {
        setErrores((prev) => ({ ...prev, [campo]: info.mensaje || "Revisa este dato." }));
        document.getElementById(ids[campo])?.focus();
      }
      setErrorEnvio(info);
    } finally {
      setEnviando(false);
      control.current?.reset(); // el token de Turnstile es de un solo uso
    }
  };

  if (enviada) return <Confirmacion solicitud={enviada} volver={volver} recienEnviada email={f.email.trim()} />;

  const lista = ORDEN_CAMPOS.filter((c) => errores[c]);
  const describir = (campo: CampoFormulario, ayuda?: string) =>
    [ayuda, errores[campo] ? `${ids[campo]}-error` : null].filter(Boolean).join(" ") || undefined;

  const texto = (campo: "nombre" | "cargo" | "empresa" | "email" | "telefono", etiqueta: string, props: {
    autoComplete: string;
    type?: string;
    inputMode?: "email" | "tel" | "text";
    placeholder?: string;
    ayuda?: string;
    opcional?: boolean;
    completa?: boolean;
  }) => {
    const idAyuda = props.ayuda ? `${ids[campo]}-ayuda` : undefined;
    return (
      <div className={`${s.campo} ${props.completa ? s.filaCompleta : ""}`}>
        <label className={s.etiqueta} htmlFor={ids[campo]}>
          {etiqueta}
          {props.opcional ? <span className={s.opcional}> (opcional)</span> : null}
        </label>
        <input
          id={ids[campo]}
          name={campo}
          className={s.input}
          type={props.type ?? "text"}
          inputMode={props.inputMode}
          autoComplete={props.autoComplete}
          placeholder={props.placeholder}
          value={f[campo]}
          onChange={(e) => cambiar(campo, e.target.value)}
          maxLength={LIMITES[campo].max}
          required={!props.opcional}
          aria-required={!props.opcional || undefined}
          aria-invalid={errores[campo] ? true : undefined}
          aria-describedby={describir(campo, idAyuda)}
        />
        {props.ayuda ? (
          <span id={idAyuda} className={s.ayuda}>
            {props.ayuda}
          </span>
        ) : null}
        <ErrorCampo id={`${ids[campo]}-error`} texto={errores[campo]} />
      </div>
    );
  };

  const consentimiento = (campo: "aceptaContacto" | "aceptaMigracion", t: Consentimientos["contacto"]) => (
    <div className={s.consentimiento} data-invalido={errores[campo] ? "true" : undefined}>
      <label className={s.consentimientoCheck} htmlFor={ids[campo]}>
        <input
          id={ids[campo]}
          type="checkbox"
          checked={f[campo]}
          onChange={(e) => cambiar(campo, e.target.checked)}
          required
          aria-invalid={errores[campo] ? true : undefined}
          aria-describedby={[`${ids[campo]}-texto`, errores[campo] ? `${ids[campo]}-error` : null].filter(Boolean).join(" ")}
        />
        <span className={s.consentimientoTitulo}>{t.titulo}</span>
      </label>
      <p id={`${ids[campo]}-texto`} className={s.consentimientoTexto}>
        {t.texto}
      </p>
      <p className={s.version}>Versión del texto: {t.version}</p>
      <div className={s.consentimientoTexto}>
        <ErrorCampo id={`${ids[campo]}-error`} texto={errores[campo]} />
      </div>
    </div>
  );

  return (
    <form className={`card ${s.form}`} onSubmit={enviar} noValidate aria-labelledby={`${id}-titulo`}>
      <div>
        <h2 id={`${id}-titulo`} className="card-title">
          Tus datos de contacto
        </h2>
        <p className="card-sub">Todos los campos son obligatorios, salvo el teléfono.</p>
      </div>

      {mostrarResumen && lista.length ? (
        <div ref={refResumen} className={s.resumen} role="alert" tabIndex={-1} aria-labelledby={`${id}-resumen`}>
          <h2 id={`${id}-resumen`}>
            {lista.length === 1 ? "Falta revisar 1 dato" : `Faltan revisar ${lista.length} datos`}
          </h2>
          <ul>
            {lista.map((c) => (
              <li key={c}>
                <a
                  href={`#${ids[c]}`}
                  onClick={(e) => {
                    e.preventDefault();
                    document.getElementById(ids[c])?.focus();
                  }}
                >
                  {ETIQUETA_RESUMEN[c]}: {errores[c]}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className={s.filas}>
        {texto("nombre", "Nombre y apellido", { autoComplete: "name", placeholder: "Ana Pérez" })}
        {texto("cargo", "Cargo", { autoComplete: "organization-title", placeholder: "Gerenta de Cumplimiento" })}
        {texto("empresa", "Empresa", {
          autoComplete: "organization",
          placeholder: "Nombre de tu empresa",
          ayuda: "La razón social exacta la confirmamos al contratar.",
          completa: true,
        })}
        {texto("email", "Correo de trabajo", {
          autoComplete: "email",
          type: "email",
          inputMode: "email",
          placeholder: "nombre@empresa.cl",
        })}
        {texto("telefono", "Teléfono", {
          autoComplete: "tel",
          type: "tel",
          inputMode: "tel",
          placeholder: "+56 9 1234 5678",
          opcional: true,
        })}
      </div>

      <fieldset className={s.consentimientos}>
        <legend>Autorizaciones</legend>
        <p className={s.consentimientosAyuda}>
          Son dos autorizaciones distintas y necesitamos ambas para enviar la solicitud.
        </p>
        {consentimiento("aceptaContacto", textos.contacto)}
        {consentimiento("aceptaMigracion", textos.migracion)}
      </fieldset>

      <Turnstile
        siteKey={siteKey}
        nonce={nonce}
        accion={ACCION_CAPTCHA}
        control={control}
        onToken={(t) => {
          setCaptcha(t);
          if (t) setCaptchaFallo(false);
        }}
        onError={() => setCaptchaFallo(true)}
      />

      {errorEnvio ? <AvisoError error={errorEnvio} onReintentar={() => setErrorEnvio(null)} /> : null}

      <div className={s.envio}>
        <p className={s.privacidad}>
          <Icon name="candado" />
          <span>
            Usamos estos datos solo para contactarte por la contratación. Si no se concreta, se eliminan.{" "}
            <Link href="/aviso-legal" prefetch={false}>
              Aviso legal
            </Link>
          </span>
        </p>
        <button type="submit" className="btn btn-primary" disabled={enviando} aria-busy={enviando}>
          <Icon name={enviando ? "reloj" : "correo"} />
          {enviando ? "Enviando…" : "Enviar solicitud"}
        </button>
      </div>
      {!captcha && !captchaFallo ? (
        <p className={s.verificacion} aria-live="polite">
          Verificando que eres una persona…
        </p>
      ) : null}
    </form>
  );
}

/* ------------------------------------------------------------------ piezas */
function ErrorCampo({ id, texto }: { id: string; texto?: string }) {
  if (!texto) return null;
  return (
    <span id={id} className={s.errorCampo}>
      <Icon name="alerta" />
      {texto}
    </span>
  );
}

function Confirmacion({
  solicitud,
  volver,
  recienEnviada,
  email,
}: {
  solicitud: SolicitudPublica;
  volver: string;
  recienEnviada: boolean;
  email?: string;
}) {
  const ref = useRef<HTMLHeadingElement>(null);
  // WCAG 2.4.3: tras enviar, el foco va al resultado (si no, quedaría en un botón que ya no existe)
  useEffect(() => {
    if (recienEnviada) ref.current?.focus();
  }, [recienEnviada]);
  const e = ESTADO_PUBLICO[solicitud.estado];
  return (
    <section className={`card ${s.listo}`} role="status" aria-labelledby="titulo-confirmacion">
      <span className={s.listoIcono}>
        <Icon name="check" />
      </span>
      <h2 id="titulo-confirmacion" ref={ref} tabIndex={-1} className="card-title">
        {recienEnviada ? "Listo, recibimos tu solicitud" : e.titulo}
      </h2>
      <p>
        {recienEnviada && email
          ? `El equipo de Therion Labs te escribirá a ${email} para conversar sobre la contratación. Mientras tanto, tus resultados, el informe y el plan de capacitación siguen disponibles sin costo.`
          : e.detalle}
      </p>
      <p className={s.ayuda}>Solicitud n.º {solicitud.id}</p>
      <div className={s.listoAcciones}>
        <Link href={volver} className="btn btn-primary">
          Volver a mis resultados
        </Link>
      </div>
    </section>
  );
}

function Estado({
  icono,
  titulo,
  rol = "status",
  children,
}: {
  icono: "info" | "alerta";
  titulo: string;
  rol?: "status" | "alert";
  children: ReactNode;
}) {
  return (
    <div className="state" role={rol}>
      <Icon name={icono} width={32} height={32} style={{ color: icono === "alerta" ? "var(--alto)" : "var(--accent)" }} />
      <h2>{titulo}</h2>
      {children}
    </div>
  );
}
