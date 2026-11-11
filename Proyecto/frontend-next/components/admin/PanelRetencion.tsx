"use client";

/**
 * HU-25 · "Retención de datos" del panel interno: el Oficial de Privacidad fija cuánto tiempo se
 * conservan los datos de los usuarios temporales después de que vence su acceso y revisa cada
 * ejecución de la anonimización automática (Ley 21.719, limitación de la conservación).
 *
 *   - Plazo vigente, próxima ejecución programada y cuántos se anonimizarían hoy.
 *   - Cambiar el plazo (valor del servidor, días propios o desactivada) con vista previa en vivo;
 *     si el cambio adelanta la anonimización de alguien, pide confirmar antes de guardar.
 *   - Simular (no cambia nada) o ejecutar ahora (irreversible: casilla de confirmación).
 *   - Historial de ejecuciones y de cambios del plazo, leído del audit log (solo conteos).
 * La autorización real (solo admin_therion) la hace FastAPI en cada llamada.
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { BarraAdmin } from "@/components/admin/BarraAdmin";
import { Icon } from "@/components/ui/Icon";
import { comoErrorAdmin } from "@/lib/admin/api";
import {
  ETIQUETA_ORIGEN, SE_ANONIMIZA, SE_CONSERVA,
  apiRetencion, describirPlazo, errorPlazo, etiquetaResultado, plazoLegible, requiereConfirmacion, resumenEjecucion, textoConfirmacion,
  type DetalleEjecucion, type EstadoRetencion, type ModoRetencion, type Pendientes, type RegistroLog, type ResultadoSimulacion,
} from "@/lib/admin/retencion";
import { fechaChile, fechaHoraChile } from "@/lib/fechas";
import a from "./admin.module.css";

const TAMANO_PAGINA = 20;

export function PanelRetencion() {
  const id = useId();
  const router = useRouter();
  const [estado, setEstado] = useState<EstadoRetencion | null>(null);
  const [historial, setHistorial] = useState<RegistroLog<DetalleEjecucion>[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // formulario del plazo
  const [modo, setModo] = useState<ModoRetencion>("entorno");
  const [dias, setDias] = useState("");
  const [previa, setPrevia] = useState<Pendientes | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [guardando, setGuardando] = useState(false);

  // ejecutar
  const [simulacion, setSimulacion] = useState<ResultadoSimulacion | null>(null);
  const [entiendo, setEntiendo] = useState(false);
  const [trabajando, setTrabajando] = useState<"simular" | "ejecutar" | null>(null);

  const manejarError = useCallback(
    (e: unknown) => {
      const err = comoErrorAdmin(e);
      if (err.status === 401) {
        router.replace("/admin/login?motivo=sesion");
        return;
      }
      setError(err.mensaje);
    },
    [router],
  );
  const alError = useRef(manejarError);
  alError.current = manejarError;

  const cargar = useCallback(async (paginas = 1) => {
    try {
      const [e, h] = await Promise.all([apiRetencion.estado(), apiRetencion.ejecuciones(1, TAMANO_PAGINA * paginas)]);
      setEstado(e);
      setHistorial(h.items);
      setTotal(h.total);
      return e;
    } catch (e2) {
      alError.current(e2);
      return null;
    }
  }, []);

  // Al cargar, el formulario parte con lo que rige hoy
  useEffect(() => {
    void cargar().then((e) => {
      if (!e) return;
      setModo(e.modo);
      setDias(e.modo === "plazo" && e.plazo_titular_dias != null ? String(e.plazo_titular_dias) : "");
    });
  }, [cargar]);

  const errDias = estado && modo === "plazo" ? errorPlazo(dias, estado.limites) : null;

  // Vista previa en vivo del plazo que se escribe (no queda en el audit log)
  useEffect(() => {
    setConfirmando(false);
    if (!estado || modo !== "plazo" || errorPlazo(dias, estado.limites)) {
      setPrevia(null);
      return;
    }
    const n = Number(dias);
    const t = setTimeout(() => {
      apiRetencion.vistaPrevia(n).then((r) => setPrevia(r.pendientes)).catch(() => setPrevia(null));
    }, 400);
    return () => clearTimeout(t);
  }, [modo, dias, estado]);

  const nuevoPlazo: number | null =
    modo === "plazo" ? (errDias ? null : Number(dias)) : modo === "entorno" ? (estado?.valor_entorno_dias ?? null) : null;
  const pendientesNuevo = modo === "plazo" ? (previa?.titulares ?? null) : modo === "entorno" ? null : 0;
  const sinCambios =
    !!estado && estado.modo === modo && (modo !== "plazo" || estado.plazo_titular_dias === nuevoPlazo);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (!estado || errDias || sinCambios) return;
    if (!confirmando && requiereConfirmacion(estado.plazo_titular_dias, nuevoPlazo, pendientesNuevo)) {
      setConfirmando(true);
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const r = await apiRetencion.cambiar(modo, modo === "plazo" ? Number(dias) : null);
      setEstado(r);
      setConfirmando(false);
      setAviso(
        r.modo === "desactivada"
          ? "Retención desactivada. El cambio quedó en el audit log."
          : `Plazo guardado: ${plazoLegible(r.plazo_titular_dias)}. Rige desde la próxima ejecución y quedó en el audit log.`,
      );
      await cargar(pagina);
    } catch (e2) {
      manejarError(e2);
    } finally {
      setGuardando(false);
    }
  }

  async function simular() {
    setTrabajando("simular");
    setError(null);
    try {
      setSimulacion(await apiRetencion.simular());
      await cargar(pagina);
    } catch (e2) {
      manejarError(e2);
    } finally {
      setTrabajando(null);
    }
  }

  async function ejecutar() {
    if (!entiendo) return;
    setTrabajando("ejecutar");
    setError(null);
    try {
      const r = await apiRetencion.ejecutar();
      setAviso(r.mensaje);
      setEntiendo(false);
      setSimulacion(null);
      // el worker la corre en segundo plano: se refresca el historial en unos segundos
      setTimeout(() => void cargar(pagina), 4000);
    } catch (e2) {
      manejarError(e2);
    } finally {
      setTrabajando(null);
    }
  }

  async function verMas() {
    const siguiente = pagina + 1;
    setPagina(siguiente);
    await cargar(siguiente);
  }

  const enCurso = estado?.ejecucion_en_curso_desde;

  return (
    <div className={a.pagina}>
      <BarraAdmin onActualizar={() => cargar(pagina)} alVolver />

      <main id="contenido" className={a.contenido}>
        <div>
          <h1 className="page-title">Retención de datos</h1>
          <p className="page-sub">
            Los datos personales de los usuarios temporales se conservan solo el tiempo necesario (Ley 21.719, principio de
            limitación de la conservación). Vencido el plazo, una tarea diaria los anonimiza con la misma rutina que una
            supresión ARCOP aprobada y conserva los puntajes para la comparativa sectorial. Cada ejecución queda en el audit log.
          </p>
        </div>

        {aviso ? (
          <p className="callout" role="status">
            <Icon name="check" aria-hidden="true" />
            <span>
              {aviso}{" "}
              <button type="button" className="link-btn" onClick={() => setAviso(null)}>Cerrar</button>
            </span>
          </p>
        ) : null}
        {error ? (
          <div className={a.alerta} role="alert">
            <strong>{error}</strong>
            <button type="button" className="link-btn" onClick={() => setError(null)}>Cerrar</button>
          </div>
        ) : null}

        {!estado ? (
          <p className={a.vacio}>Cargando la configuración de retención…</p>
        ) : (
          <>
            {/* ---------------------------------------------------------- estado actual */}
            <section className="card" aria-labelledby={`${id}-vig`}>
              <div className="card-head">
                <div>
                  <h2 id={`${id}-vig`} className="card-title">Plazo vigente</h2>
                  <p className="card-sub">{describirPlazo(estado)}</p>
                </div>
                {enCurso ? (
                  <span className="badge tone-medio">Ejecución en curso desde {fechaHoraChile(enCurso)}</span>
                ) : (
                  <span className={`badge ${estado.activa ? "tone-ok" : "tone-alto"}`}>
                    {estado.activa ? "Activa" : "Sin anonimización"}
                  </span>
                )}
              </div>
              <div className={a.rejilla}>
                <div className="kpi">
                  <span className="kpi-label"><Icon name="reloj" aria-hidden="true" /> Próxima ejecución</span>
                  <span className="kpi-value">{fechaHoraChile(estado.proxima_ejecucion)}</span>
                  <span className={a.sub}>Todos los días a las {String(estado.hora_utc).padStart(2, "0")}:00 UTC</span>
                </div>
                <div className="kpi">
                  <span className="kpi-label"><Icon name="escudo" aria-hidden="true" /> Se anonimizarían hoy</span>
                  <span className="kpi-value">{estado.pendientes ? estado.pendientes.titulares : "—"}</span>
                  <span className={a.sub}>
                    {estado.pendientes
                      ? `Vencidos antes del ${fechaChile(estado.pendientes.fecha_corte)}` +
                        (estado.pendientes.omitidos_por_arcop_abierta
                          ? ` · ${estado.pendientes.omitidos_por_arcop_abierta} en espera por una solicitud ARCOP abierta`
                          : "")
                      : "La regla no tiene plazo"}
                  </span>
                </div>
                <div className="kpi">
                  <span className="kpi-label"><Icon name="usuario" aria-hidden="true" /> Sin fecha de vencimiento</span>
                  <span className="kpi-value">{estado.usuarios_sin_vencimiento}</span>
                  <span className={a.sub}>Usuarios temporales sin fecha de expiración: la retención no los alcanza</span>
                </div>
              </div>
            </section>

            {/* ---------------------------------------------------------- cambiar plazo */}
            <section className="card" aria-labelledby={`${id}-cfg`}>
              <div className="card-head">
                <div>
                  <h2 id={`${id}-cfg`} className="card-title">Cambiar el plazo</h2>
                  <p className="card-sub">
                    Días que se conservan los datos después de que vence el acceso del usuario temporal. El cambio rige desde la
                    próxima ejecución y queda en el audit log con el valor anterior.
                  </p>
                </div>
              </div>
              <form onSubmit={guardar} noValidate className={a.formulario}>
                <fieldset className={a.grupo}>
                  <legend className="sr-only">Modo de la retención</legend>
                  <div className={a.modo} role="radiogroup">
                    <label>
                      <input type="radio" name={`${id}-modo`} checked={modo === "plazo"} onChange={() => setModo("plazo")} />
                      Plazo propio
                    </label>
                    <label>
                      <input type="radio" name={`${id}-modo`} checked={modo === "entorno"} onChange={() => setModo("entorno")} />
                      Valor del servidor ({plazoLegible(estado.valor_entorno_dias)})
                    </label>
                    <label>
                      <input
                        type="radio"
                        name={`${id}-modo`}
                        checked={modo === "desactivada"}
                        onChange={() => setModo("desactivada")}
                      />
                      Desactivada
                    </label>
                  </div>
                  {modo === "plazo" ? (
                    <div className={a.campo} style={{ maxWidth: 320 }}>
                      <label htmlFor={`${id}-dias`}>Días después del vencimiento</label>
                      <input
                        id={`${id}-dias`}
                        className={a.control}
                        inputMode="numeric"
                        value={dias}
                        placeholder="Ej.: 365"
                        onChange={(e) => setDias(e.target.value.replace(/[^\d]/g, "").slice(0, 5))}
                        aria-invalid={dias && errDias ? true : undefined}
                        aria-describedby={`${id}-dias-ayuda`}
                      />
                      <p id={`${id}-dias-ayuda`} className={dias && errDias ? a.errorCampo : a.ayuda} role={dias && errDias ? "alert" : undefined}>
                        {dias && errDias
                          ? errDias
                          : `Entre ${estado.limites.min_dias} y ${estado.limites.max_dias} días.` +
                            (dias ? ` ${plazoLegible(Number(dias))}.` : "")}
                      </p>
                    </div>
                  ) : null}
                  {modo === "plazo" && previa ? (
                    <p className={a.nota} aria-live="polite">
                      Con este plazo, hoy se anonimizarían <strong>{previa.titulares}</strong>{" "}
                      {previa.titulares === 1 ? "usuario temporal" : "usuarios temporales"} (vencidos antes del{" "}
                      {fechaChile(previa.fecha_corte)}).
                    </p>
                  ) : null}
                  {modo === "desactivada" ? (
                    <p className="callout callout-aviso">
                      <Icon name="alerta" aria-hidden="true" />
                      <span>
                        Sin retención, los datos de los usuarios temporales vencidos se conservan indefinidamente. Úsalo solo de
                        forma transitoria y deja constancia del motivo.
                      </span>
                    </p>
                  ) : null}
                </fieldset>

                {confirmando ? (
                  <div className={a.alerta} role="alertdialog" aria-labelledby={`${id}-conf`}>
                    <strong id={`${id}-conf`}>{textoConfirmacion(pendientesNuevo)}</strong>
                    <div className={a.acciones}>
                      <button type="submit" className="btn btn-primary btn-sm" disabled={guardando} aria-busy={guardando}>
                        Sí, guardar el plazo
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmando(false)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className={a.acciones}>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={guardando || sinCambios || (modo === "plazo" && !!errDias)}
                      aria-busy={guardando}
                    >
                      Guardar plazo
                    </button>
                    {sinCambios ? <span className={a.ayuda}>Es el plazo vigente.</span> : null}
                  </div>
                )}
              </form>
            </section>

            {/* ---------------------------------------------------------- ejecutar */}
            <section className="card" aria-labelledby={`${id}-run`}>
              <div className="card-head">
                <div>
                  <h2 id={`${id}-run`} className="card-title">Ejecutar ahora</h2>
                  <p className="card-sub">
                    La tarea corre sola todos los días. La simulación cuenta sin cambiar nada; la ejecución anonimiza de
                    inmediato con los plazos vigentes. Ambas quedan en el historial.
                  </p>
                </div>
              </div>
              <div className={a.formulario}>
                <div className={a.acciones}>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void simular()}
                    disabled={trabajando !== null}
                    aria-busy={trabajando === "simular"}
                  >
                    <Icon name="buscar" aria-hidden="true" /> Simular
                  </button>
                </div>
                {simulacion ? (
                  <p className={a.nota} role="status">
                    Simulación: {simulacion.titulares}{" "}
                    {simulacion.titulares === 1 ? "usuario temporal se anonimizaría" : "usuarios temporales se anonimizarían"}
                    {simulacion.titulares_omitidos_por_arcop_abierta
                      ? ` (${simulacion.titulares_omitidos_por_arcop_abierta} en espera por ARCOP abierta)`
                      : ""}
                    {simulacion.solicitudes_arcop + simulacion.eventos_seguridad + simulacion.conversaciones_tutor
                      ? `; además ${simulacion.solicitudes_arcop} solicitudes ARCOP, ${simulacion.eventos_seguridad} eventos de seguridad y ${simulacion.conversaciones_tutor} conversaciones del tutor.`
                      : "."}
                  </p>
                ) : null}
                <label className={a.modo}>
                  <input type="checkbox" className={a.casilla} checked={entiendo} onChange={(e) => setEntiendo(e.target.checked)} />
                  Entiendo que la anonimización no se puede deshacer
                </label>
                <div className={a.acciones}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void ejecutar()}
                    disabled={!entiendo || trabajando !== null || !!enCurso}
                    aria-busy={trabajando === "ejecutar"}
                  >
                    <Icon name="play" aria-hidden="true" /> Ejecutar ahora
                  </button>
                  {enCurso ? <span className={a.ayuda}>Hay una ejecución en curso.</span> : null}
                </div>
              </div>
            </section>

            {/* ---------------------------------------------------------- qué se borra */}
            <section className="card" aria-labelledby={`${id}-que`}>
              <div className="card-head">
                <div>
                  <h2 id={`${id}-que`} className="card-title">Qué se anonimiza y qué se conserva</h2>
                  <p className="card-sub">Misma rutina que una supresión ARCOP aprobada.</p>
                </div>
              </div>
              <div className={a.rejilla}>
                <div>
                  <h3 className={a.sub}>Se anonimiza</h3>
                  <ul>{SE_ANONIMIZA.map((x) => <li key={x}>{x}</li>)}</ul>
                </div>
                <div>
                  <h3 className={a.sub}>Se conserva</h3>
                  <ul>{SE_CONSERVA.map((x) => <li key={x}>{x}</li>)}</ul>
                </div>
              </div>
            </section>

            {/* ---------------------------------------------------------- historial */}
            <section className="card" aria-labelledby={`${id}-hist`}>
              <div className="card-head">
                <div>
                  <h2 id={`${id}-hist`} className="card-title">Historial de ejecuciones{total ? ` (${total})` : ""}</h2>
                  <p className="card-sub">Leído del audit log (acción retencion.ejecucion). Solo conteos, nunca datos personales.</p>
                </div>
              </div>
              {!historial.length ? (
                <p className={a.vacio}>Aún no hay ejecuciones registradas.</p>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Ejecuciones de la retención</caption>
                    <thead>
                      <tr>
                        <th scope="col">Fecha</th>
                        <th scope="col">Origen</th>
                        <th scope="col">Resultado</th>
                        <th scope="col">Plazo titulares</th>
                        <th scope="col">Detalle</th>
                        <th scope="col" className="num">Duración</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historial.map((f) => {
                        const r = etiquetaResultado(f);
                        return (
                          <tr key={f.id}>
                            <th scope="row">{fechaHoraChile(f.fecha)}</th>
                            <td>
                              {f.detalle ? ETIQUETA_ORIGEN[f.detalle.origen] ?? f.detalle.origen : "—"}
                              {f.actor_rol === "admin_therion" ? <span className={a.sub}>Admin #{f.actor_id}</span> : null}
                            </td>
                            <td><span className={`badge tone-${r.tono}`}>{r.texto}</span></td>
                            <td>{plazoLegible(f.detalle?.plazos_dias.titulares)}</td>
                            <td>{resumenEjecucion(f.detalle)}</td>
                            <td className="num">{f.detalle ? `${(f.detalle.duracion_ms / 1000).toFixed(1)} s` : "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {historial.length < total ? (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => void verMas()}>
                  Ver más ejecuciones
                </button>
              ) : null}
            </section>

            {estado.cambios_recientes.length ? (
              <section className="card" aria-labelledby={`${id}-camb`}>
                <div className="card-head">
                  <div>
                    <h2 id={`${id}-camb`} className="card-title">Últimos cambios del plazo</h2>
                  </div>
                </div>
                <ul className={a.nota}>
                  {estado.cambios_recientes.map((c) => (
                    <li key={c.id}>
                      {fechaHoraChile(c.fecha)} · Admin #{c.actor_id}:{" "}
                      {c.detalle ? `${textoModo(c.detalle.antes)} → ${textoModo(c.detalle.despues)}` : "cambio"}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

function textoModo(x: { modo: ModoRetencion; plazo_titular_dias: number | null }): string {
  if (x.modo === "desactivada") return "desactivada";
  if (x.modo === "entorno") return `valor del servidor (${plazoLegible(x.plazo_titular_dias)})`;
  return plazoLegible(x.plazo_titular_dias);
}
