"use client";

/**
 * Informe del registro de actividades de tratamiento (ventana): para presentarlo ante la Agencia de
 * Protección de Datos Personales, el certificador del modelo de prevención o el directorio.
 *
 *   Estado        si saldrá como informe oficial o como borrador (y por qué), con la versión.
 *   Vista previa  las cifras del resumen y la matriz de riesgos (probabilidad × impacto).
 *   Descargar     PDF o Excel (el servidor arma los dos con el mismo código verificable y los guarda en
 *                 Mis documentos). Si el registro no cambió, se usa el último informe emitido.
 *   Enviar        por correo, con los formatos elegidos.
 *   Historial     los informes emitidos, con sus descargas.
 *   Verificar     confirma un código verificable y si el registro cambió desde entonces.
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useState, type CSSProperties } from "react";
import { Icon } from "@/components/ui/Icon";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { tamanoLegible } from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import { fechaHoraChile } from "@/lib/fechas";
import {
  cargarInformes, descargarInforme, emitirInforme, enviarInforme, ETIQUETA_IMPACTO, ETIQUETA_PROBABILIDAD, nivelDe,
  NOMBRE_FORMATO, problemaCodigo, TONO_NIVEL, verificarCodigo,
  type EmisionInforme, type FormatoInforme, type ListaInformes, type NivelRiesgo, type RespuestaVerificacion,
} from "@/lib/informeRat";
import { mensajeError, plural } from "@/lib/mapaDatos";
import s from "./rat.module.css";

type Ocupado = null | "emitir" | FormatoInforme | `h-${number}-${FormatoInforme}` | "correo" | "verificar";
type Mensaje = { tono: "ok" | "error" | "info"; texto: string } | null;

const INCLUYE = [
  { icono: "constancia" as const, titulo: "Portada", texto: "Empresa, código verificable, versión del registro, fecha y aviso legal." },
  { icono: "diagnostico" as const, titulo: "Resumen ejecutivo", texto: "Actividades, datos sensibles, transferencias internacionales y decisiones automatizadas." },
  { icono: "lista" as const, titulo: "Detalle por actividad", texto: "Los 11 campos del reglamento, las medidas de seguridad, el rol y los plazos por categoría." },
  { icono: "brechas" as const, titulo: "Matriz de riesgos", texto: "Probabilidad × impacto de cada actividad, con sus factores y tratamientos sugeridos." },
];

export function InformeRat({
  correoUsuario,
  onCerrar,
  onSesionVencida,
  onVerPendientes,
}: {
  correoUsuario: string | null;
  onCerrar: () => void;
  onSesionVencida: (e: unknown) => boolean;
  /** Lleva a la lista filtrada por las actividades que no están vigentes. */
  onVerPendientes: () => void;
}) {
  const id = useId();
  const [lista, setLista] = useState<ListaInformes | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState<Ocupado>(null);
  const [mensaje, setMensaje] = useState<Mensaje>(null);
  const [panel, setPanel] = useState<"" | "correo" | "historial" | "verificar">("");
  // correo
  const [otroCorreo, setOtroCorreo] = useState(!correoUsuario);
  const [email, setEmail] = useState("");
  const [formatos, setFormatos] = useState<FormatoInforme[]>(["pdf", "xlsx"]);
  // verificación
  const [codigo, setCodigo] = useState("");
  const [verificacion, setVerificacion] = useState<RespuestaVerificacion | null>(null);
  const [errorCodigo, setErrorCodigo] = useState("");

  const recargar = useCallback(async () => {
    try {
      setLista(await cargarInformes());
      setError("");
    } catch (e) {
      if (!onSesionVencida(e)) setError(mensajeError(e, "No pudimos preparar el informe. Inténtalo de nuevo."));
    }
  }, [onSesionVencida]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  // Al abrir un panel (correo, historial, verificar) queda a la vista
  useEffect(() => {
    if (!panel) return;
    requestAnimationFrame(() => document.getElementById(`${id}-${panel}`)?.closest("section")?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }, [panel, id]);

  const ultima = lista?.ultima ?? null;
  const previa = lista?.previa;
  const usable = (em: EmisionInforme | null, f: FormatoInforme) => Boolean(lista?.al_dia && em?.documentos[f]);

  const fallo = (e: unknown, porDefecto: string) => {
    if (onSesionVencida(e)) return;
    setMensaje({ tono: "error", texto: mensajeError(e, porDefecto) });
  };

  /** Emite (o reutiliza) y devuelve la emisión al día. */
  const emisionAlDia = async (forzar = false): Promise<EmisionInforme> => {
    if (!forzar && ultima && lista?.al_dia && ultima.documentos.pdf && ultima.documentos.xlsx) return ultima;
    const r = await emitirInforme(forzar);
    setMensaje({ tono: r.informe.borrador ? "info" : "ok", texto: r.mensaje });
    await recargar();
    return r.informe;
  };

  const obtener = async (formato: FormatoInforme) => {
    setOcupado(formato);
    setMensaje(null);
    try {
      const em = usable(ultima, formato) ? ultima! : await emisionAlDia();
      const { blob, nombre } = await descargarInforme(em.id, formato);
      descargarBlob(blob, nombre);
      setMensaje({ tono: em.borrador ? "info" : "ok", texto: `Descargamos ${nombre}. También quedó guardado en Mis documentos.` });
    } catch (e) {
      fallo(e, "No pudimos generar el informe. Inténtalo de nuevo.");
    } finally {
      setOcupado(null);
    }
  };

  const emitirDeNuevo = async () => {
    setOcupado("emitir");
    setMensaje(null);
    try {
      await emisionAlDia(true);
    } catch (e) {
      fallo(e, "No pudimos generar el informe. Inténtalo de nuevo.");
    } finally {
      setOcupado(null);
    }
  };

  const descargarDeHistorial = async (em: EmisionInforme, formato: FormatoInforme) => {
    setOcupado(`h-${em.id}-${formato}`);
    try {
      const { blob, nombre } = await descargarInforme(em.id, formato);
      descargarBlob(blob, nombre);
    } catch (e) {
      fallo(e, "No pudimos descargar el informe.");
    } finally {
      setOcupado(null);
    }
  };

  const enviar = async () => {
    const valor = otroCorreo ? email.trim() : "";
    if (otroCorreo && !/^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/.test(valor)) {
      setMensaje({ tono: "error", texto: "Revisa el formato del correo (ejemplo: nombre@empresa.cl)." });
      return;
    }
    if (!formatos.length) {
      setMensaje({ tono: "error", texto: "Elige al menos un formato para adjuntar." });
      return;
    }
    setOcupado("correo");
    setMensaje(null);
    try {
      const em = await emisionAlDia();
      const r = await enviarInforme(em.id, valor, formatos);
      setMensaje({ tono: "ok", texto: `Enviamos el informe (${r.formatos.map((f) => NOMBRE_FORMATO[f]).join(" y ")}) a ${r.destino}.` });
      setPanel("");
    } catch (e) {
      fallo(e, "No pudimos enviar el correo. Inténtalo de nuevo o descarga el informe.");
    } finally {
      setOcupado(null);
    }
  };

  const verificar = async () => {
    const problema = problemaCodigo(codigo);
    setVerificacion(null);
    if (problema) {
      setErrorCodigo(problema);
      return;
    }
    setErrorCodigo("");
    setOcupado("verificar");
    try {
      setVerificacion(await verificarCodigo(codigo));
    } catch (e) {
      if (!onSesionVencida(e)) setErrorCodigo(mensajeError(e, "No pudimos verificar el código."));
    } finally {
      setOcupado(null);
    }
  };

  const copiarCodigo = async (c: string) => {
    try {
      await navigator.clipboard.writeText(c);
      setMensaje({ tono: "ok", texto: `Copiamos el código ${c}.` });
    } catch {
      setMensaje({ tono: "info", texto: `El código es ${c}.` });
    }
  };

  const topRiesgos = useMemo(
    () => [...(previa?.actividades ?? [])].filter((a) => a.riesgo).sort((a, b) => b.riesgo!.puntaje - a.riesgo!.puntaje).slice(0, 4),
    [previa],
  );

  /* ---------------------------------------------------------------- contenido */
  const cuerpo = () => {
    if (error) {
      return (
        <div className="callout" role="alert">
          <Icon name="alerta" />
          <span>{error}</span>
        </div>
      );
    }
    if (!lista || !previa) {
      return (
        <div style={{ display: "grid", gap: 12 }} role="status" aria-label="Preparando la vista previa del informe">
          <div className="skeleton" style={{ height: 96 }} />
          <div className="skeleton" style={{ height: 120 }} />
        </div>
      );
    }
    if (!previa.puede_emitir) {
      return (
        <div className={s.informeVacio}>
          <Icon name="documento" />
          <div>
            <h3>Aún no hay actividades para el informe</h3>
            <p>Registra al menos una actividad de tratamiento. El informe se arma con la versión vigente de cada una.</p>
          </div>
        </div>
      );
    }
    const r = previa.resumen;
    return (
      <>
        {/* -------------------------------------------- estado */}
        <section className={s.estadoInforme} data-tono={previa.borrador ? "borrador" : "oficial"} aria-labelledby={`${id}-estado`}>
          <span className={s.estadoInformeIcono} aria-hidden="true"><Icon name={previa.borrador ? "alerta" : "escudo"} /></span>
          <div className={s.estadoInformeTexto}>
            <h3 id={`${id}-estado`}>
              {previa.borrador ? "Saldrá como borrador" : "Listo para el informe oficial"}
              <span className={s.versionInforme}>Versión del registro N.º {lista.al_dia && ultima ? ultima.version_rat : previa.version_siguiente}</span>
            </h3>
            {previa.borrador ? (
              <>
                <p>El documento llevará la marca de agua «BORRADOR» y no es apto para una presentación oficial porque:</p>
                <ul>
                  {previa.motivos_borrador.map((m) => <li key={m}>{m}</li>)}
                </ul>
                <button type="button" className="link-btn" onClick={onVerPendientes}>Ver las actividades pendientes</button>
              </>
            ) : (
              <p>Todas las actividades incluidas están vigentes. Cada una se informa con su versión fija e inmutable.</p>
            )}
            {previa.revision ? (
              <p><Icon name="constancia" width={14} height={14} /> <strong>{previa.revision.texto}.</strong> El informe lleva la marca de la revisión interna.</p>
            ) : !previa.borrador ? (
              <p>Esta versión aún no tiene una revisión interna. <Link href="/empresa/registro-actividades/revision">Revisarla y dejar constancia</Link></p>
            ) : null}
          </div>
        </section>

        {mensaje ? (
          <p className={ms.alertaInfo} data-tono={mensaje.tono === "ok" ? "ok" : mensaje.tono === "info" ? "nna" : undefined} role={mensaje.tono === "error" ? "alert" : "status"}>
            <Icon name={mensaje.tono === "ok" ? "check" : mensaje.tono === "error" ? "alerta" : "info"} />
            <span>{mensaje.texto}</span>
          </p>
        ) : null}
        {/* -------------------------------------------- correo */}
        {panel === "correo" ? (
          <section className={s.bloqueInforme} aria-labelledby={`${id}-correo`}>
            <div className={s.bloqueCabeza}>
              <h3 id={`${id}-correo`}><Icon name="correo" />Enviar por correo</h3>
              <button type="button" className="link-btn" onClick={() => setPanel("")}>Cancelar</button>
            </div>
            {!lista.correo_habilitado ? (
              <p className="callout"><Icon name="info" /><span>El envío por correo no está habilitado. Descarga el informe.</span></p>
            ) : (
              <div className={s.formCorreo}>
                {correoUsuario ? (
                  <div className={`${ms.segmentado} ${ms.dos}`} role="radiogroup" aria-label="Destino">
                    <label className={ms.segmento}>
                      <input type="radio" name={`${id}-dest`} checked={!otroCorreo} onChange={() => setOtroCorreo(false)} />
                      <Icon name="usuario" /><span>A mi correo</span>
                    </label>
                    <label className={ms.segmento}>
                      <input type="radio" name={`${id}-dest`} checked={otroCorreo} onChange={() => setOtroCorreo(true)} />
                      <Icon name="correo" /><span>A otro correo</span>
                    </label>
                  </div>
                ) : null}
                {otroCorreo ? (
                  <div className={ms.campo}>
                    <label htmlFor={`${id}-email`}>Correo de destino</label>
                    <input id={`${id}-email`} type="email" className={ms.control} placeholder="nombre@empresa.cl" value={email}
                      maxLength={100} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
                    <p className={ms.ayuda}>Por ejemplo, tu encargado de prevención, tu asesor legal o el directorio.</p>
                  </div>
                ) : <p className={ms.ayuda}>Se enviará a {correoUsuario}.</p>}
                <fieldset className={s.formatos}>
                  <legend className={ms.etiquetaCampo}>Adjuntar</legend>
                  {(["pdf", "xlsx"] as FormatoInforme[]).map((f) => (
                    <label key={f} className={ms.casillaLinea}>
                      <input type="checkbox" checked={formatos.includes(f)}
                        onChange={(e) => setFormatos(e.target.checked ? [...formatos, f] : formatos.filter((x) => x !== f))} />
                      <span>{f === "pdf" ? "PDF (para presentar)" : "Excel (para filtrar y trabajar)"}</span>
                    </label>
                  ))}
                </fieldset>
                <div>
                  <button type="button" className="btn btn-primary" onClick={() => void enviar()} disabled={ocupado !== null}>
                    <Icon name="enviar" />
                    {ocupado === "correo" ? "Enviando…" : "Enviar informe"}
                  </button>
                </div>
              </div>
            )}
          </section>
        ) : null}

        {/* -------------------------------------------- historial */}
        {panel === "historial" ? (
          <section className={s.bloqueInforme} aria-labelledby={`${id}-historial`}>
            <div className={s.bloqueCabeza}>
              <h3 id={`${id}-historial`}><Icon name="historial" />Informes emitidos</h3>
              <button type="button" className="link-btn" onClick={() => setPanel("")}>Ocultar</button>
            </div>
            {lista.emisiones.length ? (
              <div className="table-wrap">
                <table className="table">
                  <caption className="sr-only">Informes del registro emitidos</caption>
                  <thead>
                    <tr><th scope="col">Emitido</th><th scope="col">Código</th><th scope="col">Versión</th><th scope="col">Estado</th><th scope="col">Descargar</th></tr>
                  </thead>
                  <tbody>
                    {lista.emisiones.map((em) => (
                      <tr key={em.id}>
                        <td>{fechaHoraChile(em.fecha)}</td>
                        <td className="code">{em.codigo}</td>
                        <td>N.º {em.version_rat}</td>
                        <td><span className={`badge ${em.borrador ? "tone-medio" : "tone-ok"}`}>{em.borrador ? "Borrador" : "Oficial"}</span></td>
                        <td>
                          <div className={s.descargasFila}>
                            {(["pdf", "xlsx"] as FormatoInforme[]).map((f) => em.documentos[f] ? (
                              <button key={f} type="button" className="btn btn-ghost btn-sm" onClick={() => void descargarDeHistorial(em, f)}
                                disabled={ocupado !== null} title={tamanoLegible(em.documentos[f]!.tamano_bytes)}>
                                <Icon name={f === "pdf" ? "pdf" : "tabla"} />
                                {ocupado === `h-${em.id}-${f}` ? "…" : NOMBRE_FORMATO[f]}
                              </button>
                            ) : (
                              <span key={f} className={ms.sinDato} title="Se eliminó de Mis documentos">{NOMBRE_FORMATO[f]} eliminado</span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className={ms.ayuda}>Aún no emites informes. El primero aparecerá aquí.</p>}
          </section>
        ) : null}

        {/* -------------------------------------------- verificar */}
        {panel === "verificar" ? (
          <section className={s.bloqueInforme} aria-labelledby={`${id}-verificar`}>
            <div className={s.bloqueCabeza}>
              <h3 id={`${id}-verificar`}><Icon name="escudo" />Verificar un código</h3>
              <button type="button" className="link-btn" onClick={() => setPanel("")}>Ocultar</button>
            </div>
            <p className={ms.ayuda}>Si alguien te presenta un informe de tu empresa, escribe el código de su portada para confirmar que es auténtico y si el registro cambió desde entonces.</p>
            <div className={s.formVerificar}>
              <input className={ms.control} value={codigo} onChange={(e) => setCodigo(e.target.value)} placeholder="CIA-REG-2026-000045-K"
                aria-label="Código verificable" aria-invalid={Boolean(errorCodigo) || undefined} maxLength={40}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void verificar(); } }} />
              <button type="button" className="btn btn-ghost" onClick={() => void verificar()} disabled={ocupado !== null}>
                <Icon name="escudo" />
                {ocupado === "verificar" ? "Verificando…" : "Verificar"}
              </button>
            </div>
            {errorCodigo ? <p className={ms.error} role="alert">{errorCodigo}</p> : null}
            {verificacion ? (
              <p className={ms.alertaInfo} data-tono={verificacion.sigue_al_dia ? "ok" : undefined} role="status">
                <Icon name={verificacion.sigue_al_dia ? "check" : "info"} />
                <span>
                  <strong>{verificacion.mensaje}</strong>{" "}
                  Emitido el {fechaHoraChile(verificacion.informe.fecha)} · versión N.º {verificacion.informe.version_rat} ·{" "}
                  {verificacion.informe.borrador ? "borrador" : "oficial"} · huella {verificacion.informe.huella_legible}.
                </span>
              </p>
            ) : null}
          </section>
        ) : null}

        {/* -------------------------------------------- último informe */}
        {ultima ? (
          <section className={s.ultimoInforme} aria-labelledby={`${id}-ultimo`}>
            <div className={s.ultimoCabeza}>
              <h3 id={`${id}-ultimo`}>Último informe emitido</h3>
              <span className={`badge ${ultima.borrador ? "tone-medio" : "tone-ok"}`}>{ultima.borrador ? "Borrador" : "Oficial"}</span>
              {!lista.al_dia ? <span className="badge tone-info">El registro cambió después</span> : null}
            </div>
            <dl className={s.datosEmision}>
              <div><dt>Código verificable</dt><dd className={s.codigo}>{ultima.codigo}
                <button type="button" className="icon-btn" onClick={() => void copiarCodigo(ultima.codigo)} aria-label="Copiar el código" title="Copiar el código"><Icon name="copiar" /></button>
              </dd></div>
              <div><dt>Versión del registro</dt><dd>N.º {ultima.version_rat}</dd></div>
              <div><dt>Emitido el</dt><dd>{fechaHoraChile(ultima.fecha)}</dd></div>
              <div><dt>Actividades</dt><dd>{ultima.actividades}</dd></div>
            </dl>
          </section>
        ) : null}

        {/* -------------------------------------------- cifras */}
        <section aria-label="Vista previa del resumen" className={s.cifrasInforme}>
          {[
            { t: "Actividades", v: r.actividades, p: `${r.por_estado.vigente} vigentes`, i: "lista" as const },
            { t: "Con datos sensibles", v: r.con_sensibles, p: r.con_nna ? `${r.con_nna} con datos de NNA` : "actividades", i: "candado" as const, tono: r.con_sensibles ? "sensible" : undefined },
            { t: "Transferencias internacionales", v: r.transferencias, p: r.transferencias ? `${r.transferencias_sin_garantia} sin garantía` : "ninguna", i: "globo" as const, tono: r.transferencias_sin_garantia ? "aviso" : undefined },
            { t: "Decisiones automatizadas", v: r.con_decisiones, p: r.con_perfilamiento ? `${r.con_perfilamiento} con perfilamiento` : "actividades", i: "chispa" as const },
            { t: "Terceros destinatarios", v: r.terceros, p: r.terceros_sin_contrato ? `${r.terceros_sin_contrato} sin contrato` : "con contrato o no requieren", i: "empresa" as const },
            { t: "Riesgo alto o crítico", v: r.riesgos_altos, p: "actividades", i: "brechas" as const, tono: r.riesgos_altos ? "alerta" : undefined },
          ].map((k) => (
            <div key={k.t} className={ms.kpi} data-tono={k.tono === "alerta" || k.tono === "sensible" ? "alerta" : k.tono}>
              <span className={ms.kpiEtiqueta}><Icon name={k.i} />{k.t}</span>
              <span className={ms.kpiValor}>{k.v}</span>
              <span className={ms.kpiPie}>{k.p}</span>
            </div>
          ))}
        </section>

        {/* -------------------------------------------- matriz de riesgos */}
        <section className={s.bloqueInforme} aria-labelledby={`${id}-matriz`}>
          <div className={s.bloqueCabeza}>
            <h3 id={`${id}-matriz`}><Icon name="brechas" />Matriz de riesgos</h3>
            <span className={ms.ayuda}>Probabilidad × impacto, calculada con lo que registraste</span>
          </div>
          <div className={s.matrizRiesgos}>
            <MapaCalor celdas={previa.mapa_calor} />
            <div className={s.topRiesgos}>
              <span className={s.topRiesgosTitulo}>Actividades con mayor riesgo</span>
              <ol>
                {topRiesgos.map((a) => (
                  <li key={a.id}>
                    <span className={s.nivelRiesgo} style={{ "--c": TONO_NIVEL[a.riesgo!.nivel] } as CSSProperties}>{a.riesgo!.nivel}</span>
                    <span className={s.topNombre}>{a.nombre}</span>
                    <span className={s.topPuntaje}>{a.riesgo!.puntaje}/25</span>
                  </li>
                ))}
              </ol>
              <p className={ms.ayuda}>El informe detalla los factores de cada actividad y lo que conviene hacer. Es una valoración orientativa.</p>
            </div>
          </div>
        </section>

        {/* -------------------------------------------- qué incluye */}
        <section className={s.bloqueInforme} aria-labelledby={`${id}-incluye`}>
          <div className={s.bloqueCabeza}>
            <h3 id={`${id}-incluye`}><Icon name="documento" />Qué incluye</h3>
            <span className={ms.ayuda}>El PDF y el Excel dicen lo mismo y llevan el mismo código</span>
          </div>
          <ul className={s.incluye}>
            {INCLUYE.map((x) => (
              <li key={x.titulo}>
                <Icon name={x.icono} />
                <span><strong>{x.titulo}</strong>{x.texto}</span>
              </li>
            ))}
          </ul>
        </section>

      </>
    );
  };

  const listo = Boolean(lista && previa?.puede_emitir && !error);

  return (
    <Dialogo
      tamano="lg"
      icono="documento"
      antetitulo="Registro de actividades de tratamiento"
      titulo="Informe del registro"
      descripcion="Para presentarlo ante la Agencia de Protección de Datos Personales, el certificador de tu modelo de prevención de infracciones o tu directorio."
      onCerrar={onCerrar}
      cerrarAlHacerClicFuera={ocupado === null}
      cabeceraExtra={listo ? (
        <div className={s.accionesInforme}>
          <button type="button" className="btn btn-primary" onClick={() => void obtener("pdf")} disabled={ocupado !== null}>
            <Icon name="pdf" />
            {ocupado === "pdf" ? "Generando PDF…" : "Descargar PDF"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => void obtener("xlsx")} disabled={ocupado !== null}>
            <Icon name="tabla" />
            {ocupado === "xlsx" ? "Generando Excel…" : "Descargar Excel"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setPanel(panel === "correo" ? "" : "correo")} disabled={ocupado !== null} aria-expanded={panel === "correo"}>
            <Icon name="correo" />
            Enviar por correo
          </button>
          <span className={s.accionesSecundarias}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPanel(panel === "historial" ? "" : "historial")} aria-expanded={panel === "historial"}>
              <Icon name="historial" />
              Historial{lista?.emisiones.length ? ` (${lista.emisiones.length})` : ""}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPanel(panel === "verificar" ? "" : "verificar")} aria-expanded={panel === "verificar"}>
              <Icon name="escudo" />
              Verificar
            </button>
          </span>
        </div>
      ) : undefined}
      pie={
        <>
          <span className={s.pieAviso}><Icon name="info" />La plataforma apoya la gestión del registro y no reemplaza la asesoría legal.</span>
          <div className={ms.modalAcciones}>
            {listo && ultima && lista?.al_dia ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void emitirDeNuevo()} disabled={ocupado !== null} title="Genera un informe nuevo con un código distinto aunque el registro no haya cambiado">
                <Icon name="refrescar" />
                {ocupado === "emitir" ? "Generando…" : "Emitir de nuevo"}
              </button>
            ) : null}
            <Link href="/empresa/documentos" className="btn btn-ghost btn-sm">
              <Icon name="carpeta" />
              Mis documentos
            </Link>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onCerrar}>Cerrar</button>
          </div>
        </>
      }
    >
      {cuerpo()}
    </Dialogo>
  );
}

/* ============================================================ mapa de calor */

function MapaCalor({ celdas }: { celdas: number[][] }) {
  return (
    <div className={s.mapaCalor} role="img" aria-label={`Matriz de riesgos: ${celdas.flat().reduce((a, b) => a + b, 0)} actividades ubicadas según probabilidad e impacto`}>
      <span className={s.ejeY}>Probabilidad</span>
      <div className={s.rejillaCalor}>
        {celdas.map((fila, fi) => {
          const prob = 5 - fi;
          return [
            <span key={`y${prob}`} className={s.etiquetaEje} title={ETIQUETA_PROBABILIDAD[prob]}>{prob}</span>,
            ...fila.map((n, ci) => {
              const nivel: NivelRiesgo = nivelDe(prob * (ci + 1));
              return (
                <span key={`${fi}-${ci}`} className={s.celdaCalor} data-nivel={nivel} data-vacia={!n || undefined}
                  title={`Probabilidad ${ETIQUETA_PROBABILIDAD[prob].toLowerCase()} · impacto ${ETIQUETA_IMPACTO[ci + 1].toLowerCase()} · ${nivel}: ${plural(n, "actividad", "actividades")}`}>
                  {n || ""}
                </span>
              );
            }),
          ];
        })}
        <span />
        {[1, 2, 3, 4, 5].map((i) => <span key={`x${i}`} className={s.etiquetaEje} title={ETIQUETA_IMPACTO[i]}>{i}</span>)}
      </div>
      <span className={s.ejeX}>Impacto</span>
      <div className={s.leyendaCalor}>
        {(["Bajo", "Medio", "Alto", "Crítico"] as NivelRiesgo[]).map((n) => (
          <span key={n}><i data-nivel={n} />{n}</span>
        ))}
      </div>
    </div>
  );
}
