"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { ApiError, descargarInformePdf, enviarInformePorCorreo, MODO_DEMO, type EnvioInforme } from "@/lib/api";
import { descargarBlob, imprimirComoPdf, nombreArchivo } from "@/lib/exportar";
import type { FiltrosBrechas } from "@/lib/filtrosBrechas";

/**
 * Descargar el informe en PDF (directo, sin el diálogo de impresión) y enviarlo por correo
 * como respaldo. El PDF lo arma el servidor: es el mismo archivo en ambos casos.
 *
 * Con `filtros`, el listado de brechas del PDF es el filtrado (vista Brechas).
 */
export function AccionesInforme({
  evaluacionId,
  filtros,
  deshabilitado = false,
  tamano = "sm",
  onAviso,
}: {
  evaluacionId: number;
  filtros?: FiltrosBrechas;
  deshabilitado?: boolean;
  tamano?: "sm" | "md";
  /** Mensaje para la región aria-live de la página (si no, se muestra aquí). */
  onAviso?: (texto: string) => void;
}) {
  const { modo } = usePanel();
  const base = modo === "encuestado" ? "/bff/api" : "/api";
  const [descargando, setDescargando] = useState(false);
  const [aviso, setAvisoLocal] = useState("");
  const [abierto, setAbierto] = useState(false);
  const refBoton = useRef<HTMLButtonElement>(null);
  const aviso_ = (t: string) => (onAviso ? onAviso(t) : setAvisoLocal(t));
  const clase = tamano === "sm" ? "btn-sm" : "";

  const descargar = async () => {
    if (MODO_DEMO) {
      aviso_("Modo demo: abrimos la impresión. Con el backend conectado el PDF se descarga directo.");
      imprimirComoPdf(nombreArchivo(evaluacionId));
      return;
    }
    setDescargando(true);
    aviso_("Generando el PDF…");
    try {
      const { blob, nombre } = await descargarInformePdf(evaluacionId, filtros, base);
      descargarBlob(blob, nombre);
      aviso_(`Descargamos ${nombre}.`);
    } catch (e) {
      aviso_(e instanceof ApiError ? e.message : "No pudimos generar el PDF. Inténtalo de nuevo.");
    } finally {
      setDescargando(false);
    }
  };

  return (
    <>
      <div className="export-group" role="group" aria-label="Informe en PDF">
        <button ref={refBoton} type="button" className={`btn btn-ghost ${clase}`} onClick={() => setAbierto(true)} disabled={deshabilitado}>
          <Icon name="correo" />
          Enviar por correo
        </button>
        <button
          type="button"
          className={`btn btn-primary ${clase}`}
          onClick={descargar}
          disabled={deshabilitado || descargando}
          aria-busy={descargando}
        >
          <Icon name={descargando ? "reloj" : "descargar"} />
          {descargando ? "Generando…" : "Descargar PDF"}
        </button>
      </div>
      {!onAviso ? (
        <p className="aviso-accion" role="status" aria-live="polite" hidden={!aviso}>
          {aviso}
        </p>
      ) : null}
      {abierto ? (
        <DialogoCorreo
          evaluacionId={evaluacionId}
          filtros={filtros}
          encuestado={modo === "encuestado"}
          base={base}
          onCerrar={(resultado) => {
            setAbierto(false);
            // WCAG 2.4.3: al cerrar, el foco vuelve al botón que abrió el diálogo
            requestAnimationFrame(() => refBoton.current?.focus());
            if (resultado) {
              aviso_(
                resultado.modo === "archivo"
                  ? `Entorno de desarrollo: el correo para ${resultado.destino} quedó guardado en el servidor (storage/correos) en vez de enviarse.`
                  : `Enviamos el informe a ${resultado.destino}. Si no llega en unos minutos, revisa la carpeta de spam.`,
              );
            }
          }}
        />
      ) : null}
    </>
  );
}

function DialogoCorreo({
  evaluacionId,
  filtros,
  encuestado,
  base,
  onCerrar,
}: {
  evaluacionId: number;
  filtros?: FiltrosBrechas;
  encuestado: boolean;
  base: "/api" | "/bff/api";
  onCerrar: (resultado: EnvioInforme | null) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const refEmail = useRef<HTMLInputElement>(null);
  const idTitulo = useId();
  const idEmail = useId();
  const idAyuda = useId();
  const idError = useId();
  const [email, setEmail] = useState("");
  const [recordar, setRecordar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const [errorCampo, setErrorCampo] = useState(false); // el error es del correo escrito (no del servidor)

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal(); // foco atrapado y Esc nativos
    refEmail.current?.focus(); // showModal enfoca el primer botón (Cerrar); el foco va al campo
  }, []);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const valor = email.trim();
    if (!encuestado && !valor) {
      setError("Escribe el correo al que quieres recibir el informe.");
      setErrorCampo(true);
      return;
    }
    if (valor && !/^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/.test(valor)) {
      setError("Revisa el formato del correo (ejemplo: nombre@empresa.cl).");
      setErrorCampo(true);
      return;
    }
    setError("");
    setErrorCampo(false);
    setEnviando(true);
    try {
      const r = await enviarInformePorCorreo(evaluacionId, { email: valor, recordar: encuestado && recordar, filtros }, base);
      ref.current?.close();
      onCerrar(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No pudimos enviar el correo. Inténtalo de nuevo.");
      setErrorCampo(err instanceof ApiError && (err.codigo === "EMAIL_INVALIDO" || err.codigo === "EMAIL_REQUERIDO"));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <dialog
      ref={ref}
      className="dialogo"
      aria-labelledby={idTitulo}
      onClose={() => onCerrar(null)}
      onCancel={() => onCerrar(null)}
    >
      <form method="dialog" onSubmit={enviar} noValidate className="dialogo-cuerpo">
        <div className="dialogo-head">
          <h2 className="card-title" id={idTitulo}>
            Enviar el informe por correo
          </h2>
          <button type="button" className="icon-btn" onClick={() => onCerrar(null)} aria-label="Cerrar">
            <Icon name="cerrar" />
          </button>
        </div>
        <p className="card-sub">
          Te enviaremos el mismo PDF que descargas, como respaldo por si pierdes el archivo. Incluye tu resultado, las
          brechas priorizadas y el plan de capacitación.
        </p>

        <div className="field">
          <label className="field-label" htmlFor={idEmail}>
            Correo electrónico{encuestado ? " (opcional si ya lo registraste)" : ""}
          </label>
          <input
            id={idEmail}
            type="email"
            inputMode="email"
            autoComplete="email"
            className="input input-plano"
            placeholder="nombre@empresa.cl"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={errorCampo || undefined}
            aria-describedby={`${idAyuda}${error ? ` ${idError}` : ""}`}
            maxLength={100}
            ref={refEmail}
          />
          <span id={idAyuda} className="card-sub">
            {encuestado
              ? "Si lo dejas vacío, usaremos el correo que registraste al comenzar."
              : "Solo se usa para este envío."}
          </span>
        </div>

        {encuestado ? (
          <label className="check">
            <input type="checkbox" checked={recordar} onChange={(e) => setRecordar(e.target.checked)} />
            <span>Guardar este correo para retomar mi evaluación y recibir futuros informes</span>
          </label>
        ) : null}

        <p id={idError} className="dialogo-error" role="alert" hidden={!error}>
          <Icon name="alerta" />
          {error}
        </p>

        <div className="dialogo-acciones">
          <button type="button" className="btn btn-ghost" onClick={() => onCerrar(null)}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={enviando} aria-busy={enviando}>
            <Icon name="correo" />
            {enviando ? "Enviando…" : "Enviar informe"}
          </button>
        </div>
        <p className="dialogo-nota">Por seguridad hay un máximo de envíos por día para cada evaluación.</p>
      </form>
    </dialog>
  );
}
