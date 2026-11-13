"use client";

/**
 * Paneles de la revisión interna: observaciones (abrir, cerrar al corregir, reabrir), diferencias entre versiones
 * del registro y evidencia (constancias, paquete verificable, envío por correo, verificación de un paquete y plazo
 * de la revisión periódica).
 */
import { useEffect, useId, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { descargarBlob } from "@/lib/exportar";
import { fechaHoraChile } from "@/lib/fechas";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { mensajeError } from "@/lib/mapaDatos";
import {
  cargarDiferencias, descargarConstancia, descargarPaquete, enviarRevision, fechaCorta, guardarPeriodicidad,
  ordenarObservaciones, TITULO_PRIORIDAD, TITULO_TIPO, TONO_PRIORIDAD, verificarPaquete,
  type Diferencias, type EstadoRevision, type Observacion, type Periodicidad, type Prioridad,
  type ResultadoVerificacionPaquete, type Revision,
} from "@/lib/revisionInterna";
import s from "./revision.module.css";

type Aviso = (a: { tono: "ok" | "error"; texto: string }) => void;

/* ============================================================ observaciones */

export function PanelObservaciones({ observaciones, soloLectura, onNueva, onCerrar, onReabrir }: {
  observaciones: Observacion[];
  soloLectura?: boolean;
  onNueva: () => void;
  onCerrar: (o: Observacion) => void;
  onReabrir: (o: Observacion) => Promise<void>;
}) {
  const [filtro, setFiltro] = useState<"abiertas" | "cerradas" | "todas">("abiertas");
  const abiertas = observaciones.filter((o) => o.estado === "abierta").length;
  const visibles = ordenarObservaciones(observaciones).filter(
    (o) => filtro === "todas" || (filtro === "abiertas" ? o.estado === "abierta" : o.estado === "cerrada"),
  );
  return (
    <section style={{ display: "grid", gap: "var(--sp-4)" }} aria-label="Observaciones">
      <div className={s.filtros}>
        <div className="chip-group" role="group" aria-label="Filtrar observaciones">
          {(["abiertas", "cerradas", "todas"] as const).map((f) => (
            <button key={f} type="button" className="chip" aria-pressed={filtro === f} onClick={() => setFiltro(f)}>
              {f === "abiertas" ? `Abiertas · ${abiertas}` : f === "cerradas" ? `Cerradas · ${observaciones.length - abiertas}` : "Todas"}
            </button>
          ))}
        </div>
        {!soloLectura ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onNueva}>
            <Icon name="mas" />Observación sobre el registro completo
          </button>
        ) : null}
      </div>
      {visibles.length ? (
        <ul className={s.obsLista}>
          {visibles.map((o) => (
            <li key={o.id} className={s.obs} data-estado={o.estado} data-prioridad={o.prioridad}>
              <div className={s.obsCabeza}>
                <span className={s.obsMeta}>
                  <strong>N.º {o.numero}</strong>
                  <span className={`badge ${TONO_PRIORIDAD[o.prioridad]}`}>Prioridad {TITULO_PRIORIDAD[o.prioridad].toLowerCase()}</span>
                  <span className={`badge ${o.estado === "abierta" ? "tone-medio" : "tone-ok"}`}>{o.estado === "abierta" ? "Abierta" : "Cerrada"}</span>
                </span>
                <span className={s.obsMeta}>Abierta el {fechaHoraChile(o.fecha_apertura)}</span>
              </div>
              <span className={s.obsMeta}>
                <Icon name="lista" width={14} height={14} />
                {TITULO_TIPO[o.objeto_tipo]}: <strong>{o.objeto_nombre}</strong>
                {o.criterio_titulo ? ` · ${o.criterio_titulo}` : ""}
                {!o.objeto_existe ? <span className={ms.etiqueta} data-tono="pendiente">Ya no está en el registro</span> : null}
              </span>
              <p className={s.obsTexto}>{o.texto}</p>
              {o.estado === "cerrada" ? (
                <div className={s.obsCierre}>
                  <small>Cerrada el {fechaHoraChile(o.fecha_cierre)}{o.objeto_cambio === true ? " · el elemento se corrigió" : o.objeto_cambio === false ? " · sin cambios en el elemento" : ""}</small>
                  <span>{o.nota_cierre}</span>
                </div>
              ) : o.cambio_desde_apertura ? (
                <p className={ms.alertaInfo} data-tono="ok"><Icon name="check" /><span>El elemento cambió desde que lo observaste: si quedó corregido, cierra la observación.</span></p>
              ) : null}
              {!soloLectura ? (
                <div className={s.filaAcciones}>
                  {o.estado === "abierta" ? (
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => onCerrar(o)}><Icon name="check" />Cerrar al corregir</button>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => void onReabrir(o)}><Icon name="refrescar" />Reabrir</button>
                  )}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="callout" role="status">
          <Icon name={filtro === "abiertas" ? "check" : "info"} />
          <span>{filtro === "abiertas" ? "No hay observaciones abiertas." : "No hay observaciones con ese filtro."}</span>
        </p>
      )}
    </section>
  );
}

export function DialogoObservacion({ titulo, antetitulo, criterio, onCerrar, onGuardar }: {
  titulo: string;
  antetitulo?: string;
  criterio?: string | null;
  onCerrar: () => void;
  onGuardar: (prioridad: Prioridad, texto: string) => Promise<void>;
}) {
  const id = useId();
  const [prioridad, setPrioridad] = useState<Prioridad>("media");
  const [texto, setTexto] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const enviar = async () => {
    if (texto.trim().length < 5) {
      setError("Describe qué hay que corregir (al menos 5 caracteres).");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      await onGuardar(prioridad, texto);
    } catch (e) {
      setError(mensajeError(e, "No pudimos guardar la observación. Inténtalo de nuevo."));
      setOcupado(false);
    }
  };
  return (
    <Dialogo tamano="sm" icono="mensaje" antetitulo={antetitulo} titulo={titulo}
      descripcion={criterio ? `Sobre: ${criterio}. Mientras esté abierta, la versión no se puede marcar como revisada.` : "Mientras esté abierta, la versión no se puede marcar como revisada."}
      onCerrar={onCerrar} onEnviar={() => void enviar()}
      pie={<>
        <button type="button" className="btn btn-ghost" onClick={onCerrar}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={ocupado}>{ocupado ? "Guardando…" : "Registrar observación"}</button>
      </>}>
      <fieldset className={ms.campo}>
        <legend>Prioridad</legend>
        <div className={ms.segmentado} role="radiogroup">
          {(["alta", "media", "baja"] as Prioridad[]).map((p) => (
            <label key={p} className={ms.segmento}>
              <input type="radio" name={`${id}-p`} checked={prioridad === p} onChange={() => setPrioridad(p)} />
              <Icon name={p === "alta" ? "alerta" : p === "media" ? "reloj" : "info"} /><span>{TITULO_PRIORIDAD[p]}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className={ms.campo}>
        <label htmlFor={`${id}-t`}>Qué hay que corregir o confirmar</label>
        <textarea id={`${id}-t`} className={ms.control} rows={4} maxLength={1000} value={texto} data-autofoco
          aria-invalid={Boolean(error)} onChange={(e) => setTexto(e.target.value)}
          placeholder="Ej.: el plazo de conservación de los currículos no coincide con la política vigente." />
        <p className={ms.ayuda}>Describe el registro, no a personas (sin correos, RUT ni teléfonos). {texto.trim().length}/1000</p>
        {error ? <p className="dialogo-error" role="alert">{error}</p> : null}
      </div>
    </Dialogo>
  );
}

export function DialogoCerrarObservacion({ observacion, onCerrar, onConfirmar }: {
  observacion: Observacion;
  onCerrar: () => void;
  onConfirmar: (nota: string) => Promise<void>;
}) {
  const id = useId();
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const enviar = async () => {
    if (nota.trim().length < 5) {
      setError("Cuenta qué se corrigió o por qué se cierra.");
      return;
    }
    setOcupado(true);
    try {
      await onConfirmar(nota);
    } catch (e) {
      setError(mensajeError(e, "No pudimos cerrar la observación. Inténtalo de nuevo."));
      setOcupado(false);
    }
  };
  return (
    <Dialogo tamano="sm" icono="check" antetitulo={`Observación N.º ${observacion.numero}`} titulo="Cerrar la observación"
      descripcion={observacion.texto} onCerrar={onCerrar} onEnviar={() => void enviar()}
      pie={<>
        <button type="button" className="btn btn-ghost" onClick={onCerrar}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={ocupado}>{ocupado ? "Cerrando…" : "Cerrar observación"}</button>
      </>}>
      {observacion.objeto_tipo !== "registro" && observacion.cambio_desde_apertura === false ? (
        <p className={ms.alertaInfo}><Icon name="alerta" /><span>«{observacion.objeto_nombre}» no ha cambiado desde que la abriste. Si la corrección no requería cambios, explícalo en la nota.</span></p>
      ) : null}
      <div className={ms.campo}>
        <label htmlFor={`${id}-n`}>Qué se corrigió</label>
        <textarea id={`${id}-n`} className={ms.control} rows={3} maxLength={1000} value={nota} data-autofoco
          aria-invalid={Boolean(error)} onChange={(e) => setNota(e.target.value)}
          placeholder="Ej.: se actualizó el plazo a 2 años según la política de selección." />
        {error ? <p className="dialogo-error" role="alert">{error}</p> : null}
      </div>
    </Dialogo>
  );
}

/* ============================================================ diferencias */

export function PanelDiferencias({ versiones, onSesionVencida }: {
  versiones: EstadoRevision["versiones"];
  onSesionVencida: (e: unknown) => boolean;
}) {
  const id = useId();
  const revisadas = versiones.filter((v) => v.revisada);
  const [desde, setDesde] = useState<number | null>(revisadas[0]?.version ?? versiones[0]?.version ?? null);
  const [hasta, setHasta] = useState<number | null>(null);
  const [datos, setDatos] = useState<Diferencias | null>(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!desde) return;
    let vivo = true;
    setCargando(true);
    setError("");
    cargarDiferencias(desde, hasta)
      .then((d) => vivo && setDatos(d))
      .catch((e) => {
        if (vivo && !onSesionVencida(e)) setError(mensajeError(e, "No pudimos comparar las versiones."));
      })
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [desde, hasta, onSesionVencida]);

  if (!versiones.length) {
    return (
      <p className="callout" role="status"><Icon name="info" /><span>Todavía no hay versiones del registro para comparar. Cada informe del registro que generas fija una versión.</span></p>
    );
  }
  const etiqueta = (v: EstadoRevision["versiones"][number]) =>
    `Versión ${v.version}${v.revisada ? " · revisada" : v.borrador ? " · borrador" : ""}${v.fecha ? ` · ${fechaHoraChile(v.fecha).split(" ")[0]}` : ""}`;
  return (
    <section style={{ display: "grid", gap: "var(--sp-4)" }} aria-label="Diferencias entre versiones">
      <div className={s.selectores}>
        <div className={ms.campo}>
          <label htmlFor={`${id}-d`}>Desde</label>
          <select id={`${id}-d`} className="select" value={desde ?? ""} onChange={(e) => setDesde(Number(e.target.value) || null)}>
            {versiones.map((v) => <option key={v.version} value={v.version}>{etiqueta(v)}</option>)}
          </select>
        </div>
        <div className={ms.campo}>
          <label htmlFor={`${id}-h`}>Hasta</label>
          <select id={`${id}-h`} className="select" value={hasta ?? ""} onChange={(e) => setHasta(Number(e.target.value) || null)}>
            <option value="">El registro actual</option>
            {versiones.map((v) => <option key={v.version} value={v.version}>{etiqueta(v)}</option>)}
          </select>
        </div>
      </div>
      {error ? <p className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></p> : null}
      {cargando && !datos ? <div className="skeleton" style={{ height: 160 }} role="status" aria-label="Comparando versiones" /> : null}
      {datos ? (
        <div style={{ display: "grid", gap: "var(--sp-3)", opacity: cargando ? 0.6 : 1 }} aria-busy={cargando}>
          <h3 style={{ fontSize: "var(--fs-md)" }}>{datos.etiqueta}</h3>
          <div className={s.totales}>
            {([["Nuevas", datos.totales.agregadas, "mas"], ["Con cambios", datos.totales.cambiadas, "editar"],
               ["Ya no están", datos.totales.quitadas, "basura"], ["Sin cambios", datos.totales.iguales, "check"]] as const).map(([t, n, i]) => (
              <div key={t} className={ms.kpi}><span className={ms.kpiEtiqueta}><Icon name={i} />{t}</span><span className={ms.kpiValor}>{n}</span></div>
            ))}
          </div>
          {datos.sin_cambios ? (
            <p className="callout" role="status"><Icon name="check" /><span>El registro no cambió entre esas versiones.</span></p>
          ) : null}
          {datos.agregadas.map((a) => (
            <div key={`n${a.id}`} className={s.cambio}><span><span className="badge tone-ok">Nueva</span> <strong>{a.nombre}</strong></span></div>
          ))}
          {datos.quitadas.map((a) => (
            <div key={`q${a.id}`} className={s.cambio}><span><span className="badge tone-critico">Ya no está</span> <strong>{a.nombre}</strong> <small>(archivada o sin versión vigente)</small></span></div>
          ))}
          {datos.cambiadas.map((a) => (
            <div key={`c${a.id}`} className={s.cambio}>
              <span><span className="badge tone-medio">Cambió</span> <strong>{a.nombre}</strong> <small>· versión {a.version_antes ?? "—"} → {a.version_despues ?? "sin versión vigente"}</small></span>
              <div className={s.cambioCampos}>
                {a.campos.length ? a.campos.map((c) => (
                  <div key={c.codigo} className={s.campoCambio}>
                    <strong>{c.titulo}</strong>
                    <span className={s.antes}>{c.antes}</span>
                    <span className={s.despues}>{c.despues}</span>
                  </div>
                )) : <p className={ms.ayuda}>Cambió lo que toma del mapa de datos, no el texto de sus campos.</p>}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

/* ============================================================ evidencia */

export function PanelEvidencia({ estado, correoUsuario, onAviso, onSesionVencida, onPeriodicidad }: {
  estado: EstadoRevision;
  correoUsuario: string | null;
  onAviso: Aviso;
  onSesionVencida: (e: unknown) => boolean;
  onPeriodicidad: (p: Periodicidad) => void;
}) {
  const id = useId();
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [correo, setCorreo] = useState<Revision | null>(null);
  const [verificacion, setVerificacion] = useState<ResultadoVerificacionPaquete | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const p = estado.periodicidad;
  const [plazo, setPlazo] = useState(p.plazo_meses);
  const [aviso, setAvisoDias] = useState(p.aviso_dias);
  const [recordar, setRecordar] = useState(p.recordatorio_correo);
  const lista = [...(estado.revision ? [estado.revision] : []), ...estado.revisadas];

  const tarea = async (marca: string, fn: () => Promise<void>, error: string) => {
    setOcupado(marca);
    try {
      await fn();
    } catch (e) {
      if (!onSesionVencida(e)) {
        onAviso({ tono: "error", texto: e instanceof ErrorBff ? mensajeError(e, error) : (e instanceof Error && e.message) || error });
      }
    } finally {
      setOcupado(null);
    }
  };

  return (
    <div className={s.bloques}>
      <section className={`${s.bloque} ${s.bloqueAncho}`} aria-labelledby={`${id}-r`}>
        <h3 id={`${id}-r`}><Icon name="constancia" />Constancias y paquetes de evidencia</h3>
        <p className={ms.ayuda}>
          El informe de la revisión (PDF) resume la lista de verificación, las observaciones y los cambios desde la revisión anterior. El paquete (ZIP)
          agrega el informe del registro, el historial de cambios y un script para verificarlo con hash sin depender de la plataforma.
        </p>
        {lista.length ? (
          <ul className={s.revisiones}>
            {lista.map((r) => (
              <li key={r.id} className={s.revisionFila}>
                <div>
                  <strong>
                    Revisión N.º {r.numero}{" "}
                    <span className={`badge ${r.estado === "revisada" ? "tone-ok" : "tone-medio"}`}>{r.estado === "revisada" ? `Versión ${r.version_rat} revisada` : "En curso"}</span>
                  </strong>
                  <small>
                    {r.estado === "revisada"
                      ? `${fechaHoraChile(r.fecha_revision)} · ${r.revisor}${r.cargo ? `, ${r.cargo}` : ""} · ${r.resumen.revisados ?? 0} puntos · ${r.resumen.observaciones?.cerradas ?? 0} observaciones cerradas`
                      : `Iniciada el ${fechaHoraChile(r.fecha_inicio)} · el informe saldrá marcado «en curso»`}
                  </small>
                </div>
                <div className={s.filaAcciones}>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={ocupado !== null}
                    onClick={() => void tarea(`pdf${r.id}`, async () => {
                      const d = await descargarConstancia(r.id);
                      descargarBlob(d.blob, d.nombre);
                    }, "No pudimos generar el informe de la revisión.")}>
                    <Icon name="pdf" />{ocupado === `pdf${r.id}` ? "Generando…" : "Informe PDF"}
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={ocupado !== null}
                    onClick={() => void tarea(`zip${r.id}`, async () => {
                      const d = await descargarPaquete(r.id);
                      descargarBlob(d.blob, d.nombre);
                      onAviso({ tono: "ok", texto: `Descargaste el paquete ${d.codigo ?? ""}. Guárdalo: su código y su hash quedan registrados para verificarlo.` });
                    }, "No pudimos armar el paquete de evidencia.")}>
                    <Icon name="descargar" />{ocupado === `zip${r.id}` ? "Armando…" : "Paquete ZIP"}
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={!estado.correo_habilitado} onClick={() => setCorreo(r)}
                    title={estado.correo_habilitado ? undefined : "El envío por correo no está habilitado"}>
                    <Icon name="correo" />Enviar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="callout"><Icon name="info" /><span>Comienza la revisión para generar su informe y su paquete de evidencia.</span></p>
        )}
      </section>

      <section className={s.bloque} aria-labelledby={`${id}-v`}>
        <h3 id={`${id}-v`}><Icon name="escudo" />Verificar un paquete</h3>
        <p className={ms.ayuda}>Sube un ZIP que te hayan entregado para confirmar que es exactamente el que exportó tu empresa y que ningún archivo cambió.</p>
        <div className={s.archivo}>
          <input id={`${id}-f`} type="file" accept=".zip,application/zip" className="input"
            onChange={(e) => { setArchivo(e.target.files?.[0] ?? null); setVerificacion(null); }} />
          <button type="button" className="btn btn-primary btn-sm" disabled={!archivo || ocupado !== null}
            onClick={() => archivo && void tarea("verificar", async () => {
              if (archivo.size > estado.limites.paquete_verificar_mb * 1024 * 1024) {
                throw new Error(`El archivo supera los ${estado.limites.paquete_verificar_mb} MB.`);
              }
              setVerificacion(await verificarPaquete(archivo));
            }, "No pudimos verificar el paquete.")}>
            {ocupado === "verificar" ? "Verificando…" : "Verificar"}
          </button>
        </div>
        {verificacion ? (
          <div className={s.verificacion} role="status">
            <p className={ms.alertaInfo} data-tono={verificacion.valido ? "ok" : undefined}>
              <Icon name={verificacion.valido ? "check" : "alerta"} /><span>{verificacion.mensaje}</span>
            </p>
            {verificacion.paquete ? (
              <span>Paquete <strong>{verificacion.paquete.codigo}</strong> · {fechaHoraChile(verificacion.paquete.fecha)}
                {verificacion.paquete.revision ? ` · revisión N.º ${verificacion.paquete.revision.numero}` : ""}</span>
            ) : null}
            {[...verificacion.alterados.map((n) => `Modificado: ${n}`), ...verificacion.faltantes.map((n) => `Falta: ${n}`),
              ...verificacion.sobrantes.map((n) => `Sobra: ${n}`)].slice(0, 8).map((t) => <span key={t}>• {t}</span>)}
            <code>SHA-256 {verificacion.sha256}</code>
          </div>
        ) : null}
      </section>

      <section className={s.bloque} aria-labelledby={`${id}-p`}>
        <h3 id={`${id}-p`}><Icon name="reloj" />Revisión periódica</h3>
        <p className={ms.ayuda}>Cada cuánto debe revisarse el registro. Te avisamos en esta página y, si quieres, por correo.</p>
        <div className={s.dosCampos}>
          <div className={ms.campo}>
            <label htmlFor={`${id}-pl`}>Revisar cada</label>
            <select id={`${id}-pl`} className="select" value={plazo} onChange={(e) => setPlazo(Number(e.target.value))}>
              {[3, 6, 12, 18, 24, 36].concat([plazo].filter((x) => ![3, 6, 12, 18, 24, 36].includes(x))).sort((a, b) => a - b)
                .map((m) => <option key={m} value={m}>{m} meses{m === 12 ? " (recomendado)" : ""}</option>)}
            </select>
          </div>
          <div className={ms.campo}>
            <label htmlFor={`${id}-av`}>Avisar con</label>
            <select id={`${id}-av`} className="select" value={aviso} onChange={(e) => setAvisoDias(Number(e.target.value))}>
              {[0, 7, 15, 30, 45, 60, 90].map((d) => <option key={d} value={d}>{d ? `${d} días de anticipación` : "Solo al vencer"}</option>)}
            </select>
          </div>
        </div>
        <label className={ms.casillaLinea}>
          <input type="checkbox" checked={recordar} onChange={(e) => setRecordar(e.target.checked)} />
          <span>Enviarme un recordatorio por correo{correoUsuario ? ` (${correoUsuario})` : ""}</span>
        </label>
        <div>
          <button type="button" className="btn btn-primary btn-sm" disabled={ocupado !== null || (plazo === p.plazo_meses && aviso === p.aviso_dias && recordar === p.recordatorio_correo)}
            onClick={() => void tarea("plazo", async () => {
              const r = await guardarPeriodicidad(plazo, aviso, recordar);
              onPeriodicidad(r.periodicidad);
              onAviso({ tono: "ok", texto: r.mensaje });
            }, "No pudimos guardar el plazo.")}>
            {ocupado === "plazo" ? "Guardando…" : "Guardar"}
          </button>
        </div>
        {p.vence ? <p className={ms.ayuda}>Próximo vencimiento con el plazo guardado: {fechaCorta(p.vence)}.</p> : null}
      </section>

      {correo ? (
        <DialogoCorreo revision={correo} correoUsuario={correoUsuario} limiteMb={estado.limites.paquete_correo_mb}
          onCerrar={() => setCorreo(null)}
          onEnviar={async (email, conPaquete) => {
            const r = await enviarRevision(correo.id, email, conPaquete);
            setCorreo(null);
            onAviso({ tono: "ok", texto: `Enviamos el informe${r.con_paquete ? " y el paquete" : ""} a ${r.destino}.` });
          }} />
      ) : null}
    </div>
  );
}

function DialogoCorreo({ revision, correoUsuario, limiteMb, onCerrar, onEnviar }: {
  revision: Revision;
  correoUsuario: string | null;
  limiteMb: number;
  onCerrar: () => void;
  onEnviar: (email: string, conPaquete: boolean) => Promise<void>;
}) {
  const id = useId();
  const [otro, setOtro] = useState(!correoUsuario);
  const [email, setEmail] = useState("");
  const [paquete, setPaquete] = useState(revision.estado === "revisada");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const enviar = async () => {
    if (otro && !/^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/.test(email.trim())) {
      setError("Revisa el formato del correo (ejemplo: nombre@empresa.cl).");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      await onEnviar(otro ? email : "", paquete);
    } catch (e) {
      setError(mensajeError(e, "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos."));
      setOcupado(false);
    }
  };
  return (
    <Dialogo tamano="sm" icono="correo" antetitulo={`Revisión N.º ${revision.numero}`} titulo="Enviar por correo"
      descripcion="Por ejemplo, a tu encargado de prevención, al certificador o al directorio."
      onCerrar={onCerrar} onEnviar={() => void enviar()}
      pie={<>
        <button type="button" className="btn btn-ghost" onClick={onCerrar}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={ocupado}><Icon name="enviar" />{ocupado ? "Enviando…" : "Enviar"}</button>
      </>}>
      {correoUsuario ? (
        <div className={`${ms.segmentado} ${ms.dos}`} role="radiogroup" aria-label="Destino">
          <label className={ms.segmento}>
            <input type="radio" name={`${id}-d`} checked={!otro} onChange={() => setOtro(false)} /><Icon name="usuario" /><span>A mi correo</span>
          </label>
          <label className={ms.segmento}>
            <input type="radio" name={`${id}-d`} checked={otro} onChange={() => setOtro(true)} /><Icon name="correo" /><span>A otro correo</span>
          </label>
        </div>
      ) : null}
      {otro ? (
        <div className={ms.campo}>
          <label htmlFor={`${id}-e`}>Correo de destino</label>
          <input id={`${id}-e`} type="email" className={ms.control} value={email} maxLength={100} autoComplete="email"
            placeholder="nombre@empresa.cl" onChange={(e) => setEmail(e.target.value)} data-autofoco />
        </div>
      ) : <p className={ms.ayuda}>Se enviará a {correoUsuario}.</p>}
      <label className={ms.casillaLinea}>
        <input type="checkbox" checked={paquete} onChange={(e) => setPaquete(e.target.checked)} />
        <span>Adjuntar también el paquete de evidencia (ZIP, hasta {limiteMb} MB)</span>
      </label>
      {error ? <p className="dialogo-error" role="alert">{error}</p> : null}
      <p className={ms.ayuda}>El informe de la revisión en PDF siempre va adjunto.</p>
    </Dialogo>
  );
}
