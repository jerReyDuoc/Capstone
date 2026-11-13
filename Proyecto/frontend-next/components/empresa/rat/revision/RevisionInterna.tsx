"use client";

/**
 * /empresa/registro-actividades/revision — Revisión interna del registro (modo de auditoría interna).
 *
 * El mismo usuario de la empresa, sin otra cuenta, recorre la lista de verificación de cada actividad y de cada
 * elemento y flujo del mapa de datos, deja observaciones y las cierra al corregir, y marca la versión del registro
 * como revisada con su nombre y la fecha (la marca aparece en el informe del registro). Ve las diferencias entre
 * versiones, descarga el informe de la revisión y el paquete de evidencia verificable, lo envía por correo y define
 * cada cuánto revisar el registro (con recordatorio).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useState, type CSSProperties } from "react";
import { Icon } from "@/components/ui/Icon";
import { useEspacioEmpresa } from "@/components/empresa/EspacioEmpresaContexto";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { descargarBlob } from "@/lib/exportar";
import { fechaHoraChile } from "@/lib/fechas";
import { mensajeError, plural } from "@/lib/mapaDatos";
import {
  cargarRevision, cerrarObservacion, decidir, descargarConstancia, iniciarRevision, marcarRevisada, observar,
  problemaNombre, reabrirObservacion, textoPeriodicidad,
  type Decision, type EstadoRevision, type Observacion, type ObjetoRevision, type Punto,
} from "@/lib/revisionInterna";
import { ListaVerificacion } from "./ListaVerificacion";
import { DialogoCerrarObservacion, DialogoObservacion, PanelDiferencias, PanelEvidencia, PanelObservaciones } from "./PanelesRevision";
import s from "./revision.module.css";

type Pestana = "lista" | "observaciones" | "diferencias" | "evidencia";
type Aviso = { tono: "ok" | "error"; texto: string } | null;

export function RevisionInterna() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const id = useId();
  const [estado, setEstado] = useState<EstadoRevision | null>(null);
  const [error, setError] = useState("");
  const [pestana, setPestana] = useState<Pestana>("lista");
  const [aviso, setAviso] = useState<Aviso>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [observando, setObservando] = useState<{ o: ObjetoRevision | null; p?: Punto } | null>(null);
  const [cerrando, setCerrando] = useState<Observacion | null>(null);
  const [marcando, setMarcando] = useState(false);
  const listo = espacio.tipo === "listo";
  const correoUsuario = espacio.tipo === "listo" ? espacio.datos.usuario.email : null;

  const sesionVencida = useCallback((e: unknown) => {
    if (e instanceof ErrorBff && e.status === 401) {
      router.replace("/ingresar?motivo=sesion");
      return true;
    }
    return false;
  }, [router]);

  const recargar = useCallback(async () => {
    try {
      setEstado(await cargarRevision());
      setError("");
    } catch (e) {
      if (!sesionVencida(e)) setError(mensajeError(e, "No pudimos cargar la revisión interna. Inténtalo de nuevo."));
    }
  }, [sesionVencida]);

  useEffect(() => {
    if (listo) void recargar();
  }, [listo, recargar]);

  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), aviso.tono === "error" ? 9000 : 5000);
    return () => clearTimeout(t);
  }, [aviso]);

  const abiertasPor = useMemo(() => {
    const m: Record<string, number> = {};
    for (const o of estado?.observaciones ?? []) if (o.estado === "abierta") m[o.objeto_clave] = (m[o.objeto_clave] ?? 0) + 1;
    return m;
  }, [estado]);

  /** Ejecuta una acción, avisa del error con el texto del servidor y recarga el estado. */
  const accion = useCallback(async (fn: () => Promise<string | void>, porDefecto: string, relanzar = false) => {
    try {
      const texto = await fn();
      if (texto) setAviso({ tono: "ok", texto });
      await recargar();
    } catch (e) {
      if (sesionVencida(e)) return;
      if (relanzar) throw e;
      setAviso({ tono: "error", texto: mensajeError(e, porDefecto) });
      if (e instanceof ErrorBff && e.status === 404) await recargar();
    }
  }, [recargar, sesionVencida]);

  const onDecidir = useCallback(async (clave: string, d: Decision, criterios?: string[], nota?: string) => {
    await accion(async () => {
      const r = await decidir(clave, d, criterios, nota);
      // La lista se actualiza al instante; el resto (requisitos y cifras) llega con la recarga
      setEstado((e) => e && { ...e, objetos: e.objetos.map((o) => (o.clave === clave ? r.objeto : o)) });
    }, "No pudimos guardar lo revisado. Inténtalo de nuevo.", d === "aceptado");
  }, [accion]);

  const encabezado = (
    <header className="page-head">
      <div>
        <Link href="/empresa/registro-actividades" className={s.volver}><Icon name="flecha" />Registro de actividades</Link>
        <span className="eyebrow">Auditoría interna</span>
        <h1 className="page-title">Revisión interna del registro</h1>
        <p className="page-sub">
          Verifica que el registro de actividades y el mapa de datos sean fieles y estén al día antes de presentarlos, certificarlos o
          informarlos al directorio, y deja constancia de esa revisión.
        </p>
      </div>
    </header>
  );

  if (espacio.tipo === "cargando" || (listo && !estado && !error)) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="skeleton" style={{ height: 140 }} role="status" aria-label="Cargando la revisión interna" />
        <div className="skeleton" style={{ height: 360 }} />
      </div>
    );
  }
  if (espacio.tipo === "error" || error) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="callout" role="alert">
          <Icon name="alerta" /><span>{espacio.tipo === "error" ? espacio.mensaje : error}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void recargar()}>Reintentar</button>
        </div>
      </div>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <div className={s.pagina}>
        {encabezado}
        <p className="callout" role="status"><Icon name="candado" />
          <span>La revisión interna es parte del servicio contratado y el de tu empresa no está activo. Tus constancias siguen en <Link href="/empresa/documentos">Mis documentos</Link> si las descargaste.</span>
        </p>
      </div>
    );
  }
  if (!estado) return null;

  const { revision, registro, resumen, requisitos, periodicidad } = estado;
  const per = textoPeriodicidad(periodicidad);
  const abiertas = resumen.observaciones.abiertas;
  const vigenteRevisada = !revision && registro.revisada;
  const tono = vigenteRevisada ? "ok" : revision && requisitos.puede_marcar ? "ok" : revision ? "aviso" : undefined;
  const sinActividades = registro.actividades === 0;

  const comenzar = () => void accion(async () => (await iniciarRevision()).mensaje, "No pudimos comenzar la revisión.");
  const botonMarcar = (
    <button type="button" className="btn btn-primary" disabled={!requisitos.puede_marcar} onClick={() => setMarcando(true)}
      title={requisitos.puede_marcar ? undefined : "Completa lo que falta para marcarla"}>
      <Icon name="constancia" />Marcar versión N.º {registro.version_siguiente} como revisada
    </button>
  );

  return (
    <div className={s.pagina}>
      {encabezado}

      {!sinActividades ? (
        <div className={s.periodo} data-tono={per.tono} role={per.tono === "alerta" ? "alert" : "status"}>
          <span className={s.periodoTexto}>
            <Icon name={per.tono === "ok" ? "check" : per.tono === "info" ? "info" : "reloj"} />
            <span><strong>{per.titulo}</strong><span>{per.detalle}</span></span>
          </span>
          <button type="button" className="link-btn" onClick={() => setPestana("evidencia")}>Cambiar el plazo</button>
        </div>
      ) : null}

      {/* ------------------------------------------------ estado de la versión */}
      <section className={s.hero} data-tono={tono} aria-labelledby={`${id}-h`}>
        <div className={s.anillo} style={{ "--p": vigenteRevisada ? 100 : resumen.porcentaje } as CSSProperties}
          role="img" aria-label={`${vigenteRevisada ? 100 : resumen.porcentaje} % de la lista revisada`}>
          <span className={s.anilloValor}>
            <strong>{vigenteRevisada ? 100 : resumen.porcentaje}%</strong>
            <small>revisado</small>
          </span>
        </div>
        <div className={s.heroTexto}>
          <h2 id={`${id}-h`}>
            {sinActividades ? "Aún no hay actividades que revisar"
              : vigenteRevisada ? `La versión N.º ${registro.revisada!.version_rat} está revisada`
              : revision ? `Revisión N.º ${revision.numero} en curso`
              : "Comienza la revisión interna"}
            <span className={s.pildora}>Registro versión N.º {registro.version_siguiente}</span>
          </h2>
          {sinActividades ? (
            <p>Registra y deja vigente al menos una actividad. Luego podrás revisarla y dejar constancia.</p>
          ) : vigenteRevisada ? (
            <p>{registro.revisada!.texto}. La marca aparece en el informe del registro. Si el registro cambia, tendrás que revisarlo de nuevo.</p>
          ) : revision ? (
            requisitos.puede_marcar ? (
              <p>Todo está revisado y no hay observaciones abiertas: ya puedes dejar constancia con tu nombre y la fecha.</p>
            ) : (
              <>
                <p>Para marcar la versión como revisada falta:</p>
                <ul className={s.faltan}>{requisitos.faltan.map((f) => <li key={f.codigo}>{f.texto}</li>)}</ul>
              </>
            )
          ) : (
            <p>
              Recorre la lista de verificación de cada actividad y de cada elemento del mapa. La plataforma comprueba lo que se puede comprobar
              sola; tú confirmas que lo declarado corresponde a la realidad de la empresa.
            </p>
          )}
          <span className={s.heroMeta}>
            {registro.cambio_desde_ultima ? <span><Icon name="alerta" />El registro cambió desde la última revisión</span> : null}
            {estado.ultima && !vigenteRevisada ? <span><Icon name="historial" />Última revisión: {fechaHoraChile(estado.ultima.fecha_revision)} (versión {estado.ultima.version_rat})</span> : null}
            {registro.borrador ? <span><Icon name="alerta" />Hay actividades que no están vigentes</span> : null}
            <span><Icon name="escudo" />Huella {registro.huella_legible}</span>
          </span>
        </div>
        {!sinActividades ? (
          <div className={s.heroAcciones}>
            {revision ? botonMarcar : (
              <button type="button" className="btn btn-primary" onClick={comenzar}>
                <Icon name="play" />{vigenteRevisada ? "Comenzar una nueva revisión" : "Comenzar la revisión"}
              </button>
            )}
            {revision ? (
              <button type="button" className="btn btn-ghost" disabled={ocupado !== null} onClick={async () => {
                setOcupado("avance");
                try {
                  const d = await descargarConstancia(revision.id);
                  descargarBlob(d.blob, d.nombre);
                } catch (e) {
                  if (!sesionVencida(e)) setAviso({ tono: "error", texto: mensajeError(e, "No pudimos generar el informe del avance.") });
                } finally {
                  setOcupado(null);
                }
              }}>
                <Icon name="pdf" />{ocupado === "avance" ? "Generando…" : "Informe del avance"}
              </button>
            ) : estado.ultima ? (
              <button type="button" className="btn btn-ghost" onClick={() => setPestana("evidencia")}><Icon name="constancia" />Ver constancias</button>
            ) : null}
          </div>
        ) : null}
      </section>

      {!sinActividades ? (
        <>
          <section className={ms.kpis} aria-label="Cifras de la revisión">
            <div className={ms.kpi}>
              <span className={ms.kpiEtiqueta}><Icon name="check" />Puntos revisados</span>
              <span className={ms.kpiValor}>{resumen.revisados}/{resumen.puntos}</span>
              <span className={ms.kpiPie}>{resumen.aceptados ? `${resumen.aceptados} aceptado(s) con justificación` : "verificados por ti"}</span>
            </div>
            <div className={ms.kpi} data-tono={resumen.por_resultado.falla ? "alerta" : undefined}>
              <span className={ms.kpiEtiqueta}><Icon name="alerta" />Fallas detectadas</span>
              <span className={ms.kpiValor}>{resumen.por_resultado.falla}</span>
              <span className={ms.kpiPie}>{plural(resumen.por_resultado.advertencia, "advertencia", "advertencias")}</span>
            </div>
            <div className={ms.kpi} data-tono={abiertas ? "aviso" : undefined}>
              <span className={ms.kpiEtiqueta}><Icon name="mensaje" />Observaciones abiertas</span>
              <span className={ms.kpiValor}>{abiertas}</span>
              <span className={ms.kpiPie}>{resumen.observaciones.cerradas} cerradas</span>
            </div>
            <div className={ms.kpi}>
              <span className={ms.kpiEtiqueta}><Icon name="mapa" />Alcance</span>
              <span className={ms.kpiValor}>{resumen.objetos}</span>
              <span className={ms.kpiPie}>{resumen.por_tipo.actividad} actividades · {resumen.por_tipo.elemento} elementos · {resumen.por_tipo.flujo} flujos</span>
            </div>
          </section>

          <div className={ms.pestanas} role="tablist" aria-label="Secciones de la revisión">
            {([
              ["lista", "Lista de verificación", "lista", resumen.pendientes, false],
              ["observaciones", "Observaciones", "mensaje", abiertas, abiertas > 0],
              ["diferencias", "Cambios entre versiones", "historial", 0, false],
              ["evidencia", "Constancias y evidencia", "constancia", 0, false],
            ] as const).map(([clave, titulo, icono, n, alerta]) => (
              <button key={clave} type="button" role="tab" id={`${id}-t-${clave}`} aria-controls={`${id}-p-${clave}`}
                aria-selected={pestana === clave} className={ms.pestana} onClick={() => setPestana(clave)}>
                <Icon name={icono} />{titulo}
                {n ? <span className={ms.contador} data-tono={alerta ? "alerta" : undefined}>{n}</span> : null}
              </button>
            ))}
          </div>

          <div role="tabpanel" id={`${id}-p-${pestana}`} aria-labelledby={`${id}-t-${pestana}`}>
            {pestana === "lista" ? (
              <ListaVerificacion objetos={estado.objetos} criterios={estado.criterios} abiertasPor={abiertasPor}
                onDecidir={onDecidir} onObservar={(o, p) => setObservando({ o, p })} />
            ) : pestana === "observaciones" ? (
              <PanelObservaciones observaciones={estado.observaciones} onNueva={() => setObservando({ o: null })}
                onCerrar={setCerrando}
                onReabrir={(o) => accion(async () => (await reabrirObservacion(o.id)).mensaje, "No pudimos reabrir la observación.")} />
            ) : pestana === "diferencias" ? (
              <PanelDiferencias versiones={estado.versiones} onSesionVencida={sesionVencida} />
            ) : (
              <PanelEvidencia estado={estado} correoUsuario={correoUsuario} onAviso={setAviso} onSesionVencida={sesionVencida}
                onPeriodicidad={(p) => setEstado((e) => e && { ...e, periodicidad: p })} />
            )}
          </div>

          <div className={s.barraMovil}>
            {revision ? botonMarcar : (
              <button type="button" className="btn btn-primary" onClick={comenzar}><Icon name="play" />Comenzar la revisión</button>
            )}
          </div>
        </>
      ) : (
        <Link href="/empresa/registro-actividades" className="btn btn-primary" style={{ justifySelf: "start" }}>
          <Icon name="lista" />Ir al registro de actividades
        </Link>
      )}

      {observando ? (
        <DialogoObservacion
          titulo={observando.o ? "Nueva observación" : "Observación sobre el registro completo"}
          antetitulo={observando.o?.nombre}
          criterio={observando.p?.titulo}
          onCerrar={() => setObservando(null)}
          onGuardar={async (prioridad, texto) => {
            await accion(async () => {
              const r = await observar(observando.o?.clave ?? "registro:0", prioridad, texto, observando.p?.codigo);
              setObservando(null);
              return r.mensaje;
            }, "No pudimos guardar la observación.", true);
          }}
        />
      ) : null}
      {cerrando ? (
        <DialogoCerrarObservacion observacion={cerrando} onCerrar={() => setCerrando(null)}
          onConfirmar={async (nota) => {
            await accion(async () => {
              const r = await cerrarObservacion(cerrando.id, nota);
              setCerrando(null);
              return r.mensaje;
            }, "No pudimos cerrar la observación.", true);
          }} />
      ) : null}
      {marcando && revision ? (
        <DialogoMarcar estado={estado} onCerrar={() => setMarcando(false)}
          onMarcado={async (mensaje) => {
            setMarcando(false);
            setAviso({ tono: "ok", texto: mensaje });
            setPestana("evidencia");
            await recargar();
          }}
          onSesionVencida={sesionVencida} />
      ) : null}

      {aviso ? (
        <div className={ms.aviso} data-tono={aviso.tono} role={aviso.tono === "error" ? "alert" : "status"}>
          <Icon name={aviso.tono === "error" ? "alerta" : "check"} />
          <span>{aviso.texto}</span>
          <button type="button" className="icon-btn" onClick={() => setAviso(null)} aria-label="Cerrar aviso"><Icon name="cerrar" /></button>
        </div>
      ) : null}
    </div>
  );
}

function DialogoMarcar({ estado, onCerrar, onMarcado, onSesionVencida }: {
  estado: EstadoRevision;
  onCerrar: () => void;
  onMarcado: (mensaje: string) => Promise<void>;
  onSesionVencida: (e: unknown) => boolean;
}) {
  const id = useId();
  const [nombre, setNombre] = useState(estado.revisor_sugerido ?? "");
  const [cargo, setCargo] = useState("");
  const [conclusion, setConclusion] = useState("");
  const [confirmo, setConfirmo] = useState(false);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const r = estado.resumen;
  const enviar = async () => {
    const problema = problemaNombre(nombre) ?? (cargo.trim() ? problemaNombre(cargo) : null);
    if (problema) {
      setError(problema);
      return;
    }
    if (!confirmo) {
      setError("Confirma la declaración para dejar constancia.");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      const res = await marcarRevisada({ revisor_nombre: nombre, revisor_cargo: cargo, conclusion, huella: estado.registro.huella });
      await onMarcado(res.mensaje);
    } catch (e) {
      if (onSesionVencida(e)) return;
      setError(mensajeError(e, "No pudimos marcar la versión como revisada. Inténtalo de nuevo."));
      setOcupado(false);
    }
  };
  return (
    <Dialogo tamano="md" icono="constancia" antetitulo={`Revisión N.º ${estado.revision?.numero}`}
      titulo={`Marcar la versión N.º ${estado.registro.version_siguiente} como revisada`}
      descripcion="Queda la fecha y tu nombre en la constancia, en el informe del registro y en el registro de auditoría. Después no se puede modificar."
      onCerrar={onCerrar} onEnviar={() => void enviar()}
      pie={<>
        <button type="button" className="btn btn-ghost" onClick={onCerrar}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={ocupado}><Icon name="constancia" />{ocupado ? "Registrando…" : "Dejar constancia"}</button>
      </>}>
      <div className={ms.kpis}>
        <div className={ms.kpi}><span className={ms.kpiEtiqueta}>Puntos revisados</span><span className={ms.kpiValor}>{r.revisados}</span></div>
        <div className={ms.kpi}><span className={ms.kpiEtiqueta}>Aceptados con justificación</span><span className={ms.kpiValor}>{r.aceptados}</span></div>
        <div className={ms.kpi}><span className={ms.kpiEtiqueta}>Observaciones cerradas</span><span className={ms.kpiValor}>{r.observaciones.cerradas}</span></div>
      </div>
      <div className={s.dosCampos}>
        <div className={ms.campo}>
          <label htmlFor={`${id}-n`}>Nombre de quien revisa</label>
          <input id={`${id}-n`} className={ms.control} value={nombre} maxLength={120} autoComplete="name" data-autofoco
            onChange={(e) => setNombre(e.target.value)} />
        </div>
        <div className={ms.campo}>
          <label htmlFor={`${id}-c`}>Cargo <span className="field-opcional">(opcional)</span></label>
          <input id={`${id}-c`} className={ms.control} value={cargo} maxLength={120} placeholder="Ej.: Encargado de prevención"
            onChange={(e) => setCargo(e.target.value)} />
        </div>
      </div>
      <div className={ms.campo}>
        <label htmlFor={`${id}-k`}>Conclusión <span className="field-opcional">(opcional)</span></label>
        <textarea id={`${id}-k`} className={ms.control} rows={3} maxLength={1500} value={conclusion}
          placeholder="Ej.: El registro refleja las actividades actuales. Se recomienda revisar los contratos con proveedores en el próximo trimestre."
          onChange={(e) => setConclusion(e.target.value)} />
      </div>
      <label className={ms.casillaLinea}>
        <input type="checkbox" checked={confirmo} onChange={(e) => setConfirmo(e.target.checked)} />
        <span>Declaro que revisé el registro de actividades y el mapa de datos con esta lista de verificación y que, a mi leal saber, el registro es fiel a la realidad de la empresa a la fecha.</span>
      </label>
      {error ? <p className="dialogo-error" role="alert">{error}</p> : null}
    </Dialogo>
  );
}
