"use client";

/**
 * Detalle de una actividad de tratamiento:
 *   Ficha        formulario en 6 pasos mientras es borrador o está en revisión; ficha de solo
 *                lectura cuando está vigente o archivada (para cambiarla se abre una nueva versión).
 *   Versiones    las versiones que quedaron vigentes (inmutables) y su contenido.
 *
 * Cada guardado envía solo lo que cambió y la revisión que se está viendo. Si la actividad cambió
 * en otra pestaña o por un cambio en el mapa de datos, se recarga y se avisa (nada se pisa).
 */
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { DialogoConfirmar } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { fechaHoraChile } from "@/lib/fechas";
import { mensajeError, type CatalogoMapa, type VistaMapa } from "@/lib/mapaDatos";
import {
  cambiarEstado, cambiosContenido, cargarActividad, editarActividad, ETIQUETA_ACCION_ESTADO, ETIQUETA_ESTADO,
  PASO_DE_CLAVE, pendientesPorPaso, textoVersion, TONO_ESTADO, vistaPreviaDesdeMapa,
  type AccionEstado, type Actividad, type CatalogoRat, type ContenidoActividad,
} from "@/lib/registroActividades";
import { FichaActividad, ResumenCorto } from "./Ficha";
import { HistorialActividad } from "./Historial";
import { PasoActividad, PasoConservacion, PasoDestinatarios, PasoLicitud, PasoSeguridad, PasoSistemas, type PropsPaso } from "./Pasos";
import s from "./rat.module.css";

type Pestana = "ficha" | "versiones";
type Aviso = { tono: "ok" | "error"; texto: string };

const ICONO_ACCION: Record<AccionEstado, IconName> = {
  enviar_revision: "enviar",
  volver_borrador: "flechaIzq",
  aprobar: "check",
  nueva_version: "editar",
  archivar: "carpeta",
  reactivar: "refrescar",
};

const CONFIRMAR: Partial<Record<AccionEstado, { titulo: string; texto: string; boton: string }>> = {
  aprobar: {
    titulo: "¿Dejar vigente esta actividad?",
    texto: "Se guardará una versión fija que ya no se podrá modificar y quedará como respaldo ante una fiscalización. "
      + "Si después necesitas cambiarla, abrirás una nueva versión y esta seguirá valiendo hasta que la nueva quede vigente.",
    boton: "Dejar vigente",
  },
  nueva_version: {
    titulo: "¿Editar en una nueva versión?",
    texto: "La actividad vuelve a borrador para que hagas los cambios. La versión vigente actual sigue valiendo hasta que "
      + "dejes vigente la nueva.",
    boton: "Abrir nueva versión",
  },
  archivar: {
    titulo: "¿Archivar esta actividad?",
    texto: "Úsalo cuando la actividad ya no se realiza. Se conserva con todo su historial y puedes reactivarla cuando quieras.",
    boton: "Archivar",
  },
};

export function DetalleActividad({
  id,
  catalogo,
  catalogoMapa,
  mapa,
  onVolver,
  onAviso,
  onSesionVencida,
  onMapaDesactualizado,
}: {
  id: number;
  catalogo: CatalogoRat;
  catalogoMapa: CatalogoMapa | null;
  mapa: VistaMapa;
  onVolver: () => void;
  onAviso: (a: Aviso) => void;
  onSesionVencida: (e: unknown) => boolean;
  onMapaDesactualizado: () => Promise<void>;
}) {
  const [actividad, setActividad] = useState<Actividad | null>(null);
  const [borrador, setBorrador] = useState<ContenidoActividad | null>(null);
  const [error, setError] = useState("");
  const [paso, setPaso] = useState(1);
  const [pestana, setPestana] = useState<Pestana>("ficha");
  const [ocupado, setOcupado] = useState(false);
  const [errorCampo, setErrorCampo] = useState<{ campo: string; mensaje: string } | null>(null);
  const [confirmar, setConfirmar] = useState<AccionEstado | null>(null);
  const refContenido = useRef<HTMLDivElement>(null);

  const aplicar = useCallback((a: Actividad) => {
    setActividad(a);
    if (a.contenido) setBorrador(a.contenido);
  }, []);

  const recargar = useCallback(async () => {
    try {
      const r = await cargarActividad(id);
      aplicar(r.actividad);
    } catch (e) {
      if (!onSesionVencida(e)) setError(mensajeError(e, "No pudimos cargar la actividad. Inténtalo de nuevo."));
    }
  }, [id, aplicar, onSesionVencida]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  const cambios = useMemo(
    () => (actividad?.contenido && borrador ? cambiosContenido(actividad.contenido, borrador) : {}),
    [actividad, borrador],
  );
  const sinGuardar = Object.keys(cambios).length > 0;

  // Avisa antes de cerrar la pestaña con cambios sin guardar
  useEffect(() => {
    if (!sinGuardar) return;
    const antes = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", antes);
    return () => window.removeEventListener("beforeunload", antes);
  }, [sinGuardar]);

  const previa = useMemo(
    () => vistaPreviaDesdeMapa(borrador ?? { elementos: [], flujos: [] }, mapa, catalogoMapa),
    [borrador, mapa, catalogoMapa],
  );

  /** Maneja los errores comunes de un guardado o cambio de estado. Devuelve true si ya avisó. */
  const resolverError = useCallback(
    async (e: unknown, porDefecto: string) => {
      if (onSesionVencida(e)) return;
      if (e instanceof ErrorBff && e.info.codigo === "ACTIVIDAD_DESACTUALIZADA") {
        await Promise.all([recargar(), onMapaDesactualizado()]);
        onAviso({ tono: "error", texto: "La actividad cambió en otra pestaña o por un cambio en el mapa de datos. Cargamos lo más reciente: revisa y vuelve a intentarlo." });
        return;
      }
      if (e instanceof ErrorBff && e.info.campo) {
        const campo = e.info.campo as keyof ContenidoActividad;
        setErrorCampo({ campo: e.info.campo, mensaje: e.info.mensaje || porDefecto });
        if (PASO_DE_CLAVE[campo]) setPaso(PASO_DE_CLAVE[campo]);
      }
      onAviso({ tono: "error", texto: mensajeError(e, porDefecto) });
    },
    [onAviso, onMapaDesactualizado, onSesionVencida, recargar],
  );

  /** Guarda lo que cambió. Devuelve la actividad actualizada (o null si no se pudo). */
  const guardar = useCallback(
    async (silencioso = false): Promise<Actividad | null> => {
      if (!actividad || !borrador) return null;
      if (!sinGuardar) return actividad;
      setOcupado(true);
      setErrorCampo(null);
      try {
        const r = await editarActividad(actividad.id, actividad.revision, cambios);
        aplicar(r.actividad);
        if (!silencioso) onAviso({ tono: "ok", texto: "Guardamos los cambios." });
        return r.actividad;
      } catch (e) {
        await resolverError(e, "No pudimos guardar los cambios. Inténtalo de nuevo.");
        return null;
      } finally {
        setOcupado(false);
      }
    },
    [actividad, borrador, sinGuardar, cambios, aplicar, onAviso, resolverError],
  );

  const ejecutarAccion = async (accion: AccionEstado) => {
    if (!actividad) return;
    // Lo que no se guardó se guarda antes de cambiar de estado
    const actual = sinGuardar ? await guardar(true) : actividad;
    if (!actual) return;
    setOcupado(true);
    try {
      const r = await cambiarEstado(actual.id, actual.revision, accion);
      aplicar(r.actividad);
      setConfirmar(null);
      if (accion === "nueva_version" || accion === "reactivar") setPaso(1);
      onAviso({ tono: "ok", texto: r.mensaje ?? "Listo." });
    } catch (e) {
      setConfirmar(null);
      await resolverError(e, "No pudimos cambiar el estado. Inténtalo de nuevo.");
    } finally {
      setOcupado(false);
    }
  };

  const irAPaso = async (n: number) => {
    if (n === paso) return;
    if (sinGuardar && !(await guardar(true))) return;
    setPaso(n);
    requestAnimationFrame(() => refContenido.current?.focus());
  };

  if (error) {
    return (
      <>
        <button type="button" className={`btn btn-ghost btn-sm ${s.volver}`} onClick={onVolver}><Icon name="flechaIzq" />Volver al registro</button>
        <div className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></div>
      </>
    );
  }
  if (!actividad || !borrador) {
    return <div className="skeleton" style={{ height: 480 }} role="status" aria-label="Cargando la actividad" />;
  }

  const c = actividad.completitud;
  const pendientes = pendientesPorPaso(c);
  const cambiar = (parcial: Partial<ContenidoActividad>) => {
    setBorrador((b) => (b ? { ...b, ...parcial } : b));
    if (errorCampo && Object.keys(parcial).includes(errorCampo.campo)) setErrorCampo(null);
  };
  const props: PropsPaso = { borrador, cambiar, catalogo, catalogoMapa, mapa, completitud: c, previa, errorCampo };
  const ultimoPaso = catalogo.pasos.length;

  const moverPestana = (e: KeyboardEvent, actual: Pestana) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const otra: Pestana = actual === "ficha" ? "versiones" : "ficha";
    setPestana(otra);
    document.getElementById(`tab-rat-${otra}`)?.focus();
  };

  return (
    <>
      <button
        type="button"
        className={`btn btn-ghost btn-sm ${s.volver}`}
        onClick={async () => {
          if (sinGuardar && !window.confirm("Tienes cambios sin guardar. ¿Salir de todas formas?")) return;
          onVolver();
        }}
      >
        <Icon name="flechaIzq" />
        Volver al registro
      </button>

      <section className={`card ${s.cabeza}`} aria-labelledby="titulo-actividad">
        <div className={s.cabezaFila}>
          <div style={{ display: "grid", gap: 8, minWidth: 0 }}>
            <span className={s.acciones}>
              <span className={`badge ${TONO_ESTADO[actividad.estado]}`}>{ETIQUETA_ESTADO[actividad.estado]}</span>
              <span className="card-sub">{textoVersion(actividad)}</span>
            </span>
            <h2 id="titulo-actividad" className={s.titulo}>{actividad.nombre}</h2>
            <ResumenCorto porcentaje={c.porcentaje} faltan={c.faltantes.length} />
          </div>
          <div className={s.acciones}>
            {actividad.acciones.map((a) => {
              const bloqueada = a === "aprobar" && !c.puede_quedar_vigente;
              const principal = a === "aprobar" || a === "enviar_revision" || a === "reactivar";
              return (
                <button
                  key={a}
                  type="button"
                  className={`btn ${principal ? "btn-primary" : "btn-ghost"}`}
                  disabled={ocupado || bloqueada}
                  title={bloqueada ? "Completa los datos obligatorios para dejarla vigente" : undefined}
                  onClick={() => (CONFIRMAR[a] ? setConfirmar(a) : void ejecutarAccion(a))}
                >
                  <Icon name={ICONO_ACCION[a]} />
                  {ETIQUETA_ACCION_ESTADO[a]}
                </button>
              );
            })}
          </div>
        </div>
        <div className={ms.barra} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={c.porcentaje} aria-label="Avance de la actividad">
          <span style={{ width: `${c.porcentaje}%` }} />
        </div>
        {actividad.estado === "en_revision" && !c.puede_quedar_vigente ? (
          <p className={ms.ayuda} style={{ fontSize: "var(--fs-sm)" }}>
            Para dejarla vigente faltan: {c.faltantes.map((f) => f.titulo.toLowerCase()).join(", ")}.
          </p>
        ) : null}
        {actividad.fecha_vigencia && actividad.estado === "vigente" ? (
          <p className="card-sub">Vigente desde el {fechaHoraChile(actividad.fecha_vigencia)}.</p>
        ) : null}
      </section>

      {actividad.motivos_revision.length ? (
        <div className="callout callout-aviso" role="status">
          <Icon name="alerta" />
          <div style={{ display: "grid", gap: 6 }}>
            <strong>Cambió algo del mapa de datos que esta actividad usa</strong>
            <ul className={s.motivos}>
              {actividad.motivos_revision.slice(-6).map((m, i) => <li key={`${m.fecha}-${i}`}>{m.texto}</li>)}
            </ul>
            <span>Revisa los pasos 2 y 4 y, si todo está bien, déjala vigente otra vez.</span>
          </div>
        </div>
      ) : null}

      <div className={ms.pestanas} role="tablist" aria-label="Secciones de la actividad">
        {(["ficha", "versiones"] as Pestana[]).map((p) => (
          <button
            key={p}
            id={`tab-rat-${p}`}
            type="button"
            role="tab"
            aria-selected={pestana === p}
            aria-controls={`panel-rat-${p}`}
            tabIndex={pestana === p ? 0 : -1}
            className={ms.pestana}
            onClick={() => setPestana(p)}
            onKeyDown={(e) => moverPestana(e, p)}
          >
            <Icon name={p === "ficha" ? "documento" : "historial"} />
            {p === "ficha" ? "Ficha de la actividad" : "Versiones"}
            {p === "versiones" && actividad.version_vigente ? <span className={ms.contador}>{actividad.version_vigente}</span> : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-rat-${pestana}`} aria-labelledby={`tab-rat-${pestana}`}>
        {pestana === "versiones" ? (
          <div style={{ marginTop: 16 }}>
            <HistorialActividad id={actividad.id} revision={actividad.revision} catalogo={catalogo} catalogoMapa={catalogoMapa} />
          </div>
        ) : !actividad.editable ? (
          <section className="card" style={{ display: "grid", gap: 16, marginTop: 16 }} aria-label="Ficha de la actividad">
            <p className="callout" style={{ margin: 0 }}>
              <Icon name={actividad.estado === "vigente" ? "candado" : "carpeta"} />
              <span>
                {actividad.estado === "vigente"
                  ? "Esta versión está vigente y ya no se puede modificar. Para cambiarla, usa «Editar en una nueva versión»."
                  : "La actividad está archivada. Reactívala para volver a trabajar en ella."}
              </span>
            </p>
            {actividad.derivados ? (
              <FichaActividad contenido={borrador} mapa={actividad.derivados} catalogo={catalogo} catalogoMapa={catalogoMapa} />
            ) : null}
          </section>
        ) : (
          <div className={s.zona} style={{ marginTop: 16 }}>
            <nav aria-label="Pasos del formulario">
              <ol className={s.pasos}>
                {catalogo.pasos.map((p) => {
                  const n = pendientes[p.numero] ?? 0;
                  return (
                    <li key={p.numero}>
                      <button type="button" className={s.paso} aria-current={paso === p.numero ? "step" : undefined} data-completo={n === 0} onClick={() => void irAPaso(p.numero)} disabled={ocupado}>
                        <span className={s.pasoNum}>{n === 0 ? <Icon name="check" /> : p.numero}</span>
                        <strong>{p.titulo}</strong>
                        <small>{n === 0 ? "Completo" : n === 1 ? "1 dato pendiente" : `${n} datos pendientes`}</small>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            <form
              className={s.contenido}
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                void guardar();
              }}
            >
              <div ref={refContenido} tabIndex={-1} style={{ outline: "none", display: "grid", gap: 4 }}>
                <span className="eyebrow">Paso {paso} de {ultimoPaso}</span>
                <h2 className="card-title">{catalogo.pasos[paso - 1]?.titulo}</h2>
                <p className="card-sub">{catalogo.pasos[paso - 1]?.descripcion}</p>
              </div>

              {paso === 1 ? <PasoActividad {...props} /> : null}
              {paso === 2 ? <PasoSistemas {...props} /> : null}
              {paso === 3 ? <PasoLicitud {...props} /> : null}
              {paso === 4 ? <PasoDestinatarios {...props} /> : null}
              {paso === 5 ? <PasoConservacion {...props} /> : null}
              {paso === 6 ? <PasoSeguridad {...props} onIrAPaso={(n) => void irAPaso(n)} sinGuardar={sinGuardar} /> : null}

              <div className={s.navPasos}>
                <button type="button" className="btn btn-ghost" onClick={() => void irAPaso(paso - 1)} disabled={paso === 1 || ocupado}>
                  <Icon name="flechaIzq" />
                  Anterior
                </button>
                <span className={s.acciones}>
                  {sinGuardar ? <span className={s.sinGuardar} role="status">Cambios sin guardar</span> : null}
                  <button type="submit" className="btn btn-ghost" disabled={!sinGuardar || ocupado}>
                    {ocupado ? "Guardando…" : "Guardar"}
                  </button>
                  {paso < ultimoPaso ? (
                    <button type="button" className="btn btn-primary" onClick={() => void irAPaso(paso + 1)} disabled={ocupado}>
                      {sinGuardar ? "Guardar y seguir" : "Siguiente"}
                      <Icon name="flecha" />
                    </button>
                  ) : actividad.estado === "borrador" ? (
                    <button type="button" className="btn btn-primary" onClick={() => void ejecutarAccion("enviar_revision")} disabled={ocupado}>
                      <Icon name="enviar" />
                      {sinGuardar ? "Guardar y enviar a revisión" : "Enviar a revisión"}
                    </button>
                  ) : (
                    <button type="button" className="btn btn-primary" onClick={() => setConfirmar("aprobar")} disabled={ocupado || !c.puede_quedar_vigente || sinGuardar}>
                      <Icon name="check" />
                      Dejar vigente
                    </button>
                  )}
                </span>
              </div>
              {paso === ultimoPaso && actividad.estado === "en_revision" && sinGuardar ? (
                <p className={ms.ayuda}>Guarda los cambios para comprobar si ya puede quedar vigente.</p>
              ) : null}
            </form>
          </div>
        )}
      </div>

      <p className={ms.ayuda} style={{ marginTop: 8 }}>
        {catalogo.aviso} Los sistemas, terceros y flujos se editan en el <Link href="/empresa/mapa-datos">mapa de datos</Link>.
      </p>

      {confirmar && CONFIRMAR[confirmar] ? (
        <DialogoConfirmar
          titulo={CONFIRMAR[confirmar]!.titulo}
          textoConfirmar={CONFIRMAR[confirmar]!.boton}
          peligro={confirmar === "archivar"}
          onCerrar={() => setConfirmar(null)}
          onConfirmar={() => ejecutarAccion(confirmar)}
        >
          <p>{CONFIRMAR[confirmar]!.texto}</p>
          {confirmar === "aprobar" && c.advertencias?.length ? (
            <p>Antes de confirmar, revisa las recomendaciones del paso 6.</p>
          ) : null}
        </DialogoConfirmar>
      ) : null}
    </>
  );
}
