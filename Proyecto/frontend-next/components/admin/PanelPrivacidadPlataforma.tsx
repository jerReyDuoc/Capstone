"use client";

/**
 * HU-41 · "Privacidad de la plataforma" del panel interno: el registro de cómo ComplianceAI trata los datos
 * personales, generado por el backend desde el inventario de datos y los plazos de retención configurados.
 *
 *   - Revisión interna: indicadores, hallazgos (con qué hacer) y revisiones automáticas.
 *   - Mapa de datos: quién opera, dónde se guardan los datos y qué proveedores los tratan (con país, garantía
 *     y contrato), y el PDF del mapa.
 *   - Actividades: las actividades de tratamiento con su base, sus plazos y una ficha con todo el detalle.
 *   - Informes: el RAT y el RoPA (PDF y Excel, mismo formato que los clientes), los datos de contacto que pide
 *     el RoPA, el historial de emisiones y la verificación de un código.
 * La autorización real (solo admin_therion) la hace FastAPI en cada llamada.
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent as EventoTeclado } from "react";
import { BarraAdmin } from "@/components/admin/BarraAdmin";
import { Icon } from "@/components/ui/Icon";
import { comoErrorAdmin } from "@/lib/admin/api";
import {
  NIVEL_HALLAZGO, apiPrivacidad, cambiosRopa, codigoBienFormado, columnaMapa, contarPlazos, descargarArchivo,
  estadoRegistro, filtrarHallazgos, mensajeCampoRopa, resumenHallazgos,
  type Actividad, type DatosRopa, type ElementoMapa, type FiltroNivel, type ResultadoVerificacion,
  type ResumenPrivacidad, type TipoInforme,
} from "@/lib/admin/privacidad";
import { fechaHoraChile } from "@/lib/fechas";
import a from "./admin.module.css";
import s from "./privacidad.module.css";

type Pestana = "revision" | "mapa" | "actividades" | "informes";
const PESTANAS: { id: Pestana; texto: string }[] = [
  { id: "revision", texto: "Revisión interna" },
  { id: "mapa", texto: "Mapa de datos" },
  { id: "actividades", texto: "Actividades" },
  { id: "informes", texto: "Informes" },
];
const FILTROS: { id: FiltroNivel; texto: string }[] = [
  { id: "todos", texto: "Todos" },
  { id: "critico", texto: "Críticos" },
  { id: "alto", texto: "Altos" },
  { id: "medio", texto: "Medios" },
  { id: "bajo", texto: "Informativos" },
];
const ICONO_REVISION = { ok: "✓", alerta: "!", error: "×" } as const;
const ROPA_VACIO: DatosRopa = { direccion: null, correo: null, telefono: null, tiene_dpo: null, dpo_cargo: null, dpo_correo: null };

export function PanelPrivacidadPlataforma() {
  const id = useId();
  const router = useRouter();
  const [datos, setDatos] = useState<ResumenPrivacidad | null>(null);
  const [pestana, setPestana] = useState<Pestana>("revision");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<FiltroNivel>("todos");
  const [nodo, setNodo] = useState<number | null>(null);
  const [ficha, setFicha] = useState<Actividad | null>(null);
  const [emitiendo, setEmitiendo] = useState<TipoInforme | null>(null);
  const [ropa, setRopa] = useState<DatosRopa>(ROPA_VACIO);
  const [rechazo, setRechazo] = useState<{ campo?: string; mensaje: string } | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [verificacion, setVerificacion] = useState<ResultadoVerificacion | null>(null);
  const [errorCodigo, setErrorCodigo] = useState<string | null>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const origenFicha = useRef<HTMLElement | null>(null);

  const manejarError = useCallback(
    (e: unknown) => {
      const err = comoErrorAdmin(e);
      if (err.status === 401) {
        router.replace("/admin/login?motivo=sesion");
        return null;
      }
      setError(err.mensaje);
      return err;
    },
    [router],
  );
  const alError = useRef(manejarError);
  alError.current = manejarError;

  const cargar = useCallback(async () => {
    try {
      const r = await apiPrivacidad.resumen();
      setDatos(r);
      setRopa({ ...ROPA_VACIO, ...r.ropa.datos });
      return r;
    } catch (e) {
      alError.current(e);
      return null;
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // ficha lateral: Escape cierra y el foco vuelve a la actividad
  useEffect(() => {
    if (!ficha) return;
    cerrarRef.current?.focus();
    const alTeclado = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrarFicha();
    };
    document.addEventListener("keydown", alTeclado);
    return () => document.removeEventListener("keydown", alTeclado);
  }, [ficha]);

  function abrirFicha(act: Actividad, origen: HTMLElement) {
    origenFicha.current = origen;
    setFicha(act);
  }
  function cerrarFicha() {
    setFicha(null);
    origenFicha.current?.focus();
  }

  function moverPestana(e: EventoTeclado, actual: Pestana) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = PESTANAS.findIndex((p) => p.id === actual);
    const sig = PESTANAS[(i + (e.key === "ArrowRight" ? 1 : -1) + PESTANAS.length) % PESTANAS.length].id;
    setPestana(sig);
    document.getElementById(`${id}-tab-${sig}`)?.focus();
  }

  async function emitir(tipo: TipoInforme, forzar = false) {
    setEmitiendo(tipo);
    setError(null);
    setAviso(null);
    try {
      const r = await apiPrivacidad.emitir(tipo, forzar);
      setAviso(r.mensaje);
      await cargar();
    } catch (e) {
      manejarError(e);
    } finally {
      setEmitiendo(null);
    }
  }

  async function descargar(url: string, respaldo: string) {
    setError(null);
    try {
      await descargarArchivo(url, respaldo);
    } catch (e) {
      manejarError(e);
    }
  }

  async function guardarRopa(ev: FormEvent) {
    ev.preventDefault();
    if (!datos) return;
    const cambios = cambiosRopa({ ...ROPA_VACIO, ...datos.ropa.datos }, ropa);
    if (!Object.keys(cambios).length) {
      setAviso("No hay cambios en los datos de contacto.");
      return;
    }
    setGuardando(true);
    setRechazo(null);
    setError(null);
    try {
      await apiPrivacidad.guardarRopa(cambios);
      setAviso("Guardamos los datos de contacto de Therion Labs.");
      await cargar();
    } catch (e) {
      const err = comoErrorAdmin(e);
      if (err.status === 422) setRechazo({ campo: err.campo, mensaje: err.mensaje });
      else manejarError(e);
    } finally {
      setGuardando(false);
    }
  }

  async function verificar(ev: FormEvent) {
    ev.preventDefault();
    setVerificacion(null);
    if (!codigoBienFormado(codigo)) {
      setErrorCodigo("Revisa el código: tiene la forma CIA-PLAT-REG-2026-000003-7.");
      return;
    }
    setErrorCodigo(null);
    try {
      setVerificacion(await apiPrivacidad.verificar(codigo));
    } catch (e) {
      const err = comoErrorAdmin(e);
      if (err.status === 404 || err.status === 422) setErrorCodigo(err.mensaje);
      else manejarError(e);
    }
  }

  const cambiar = (campo: keyof DatosRopa) => (valor: string | boolean | null) =>
    setRopa((r) => ({ ...r, [campo]: valor }));

  return (
    <div className={a.pagina}>
      <BarraAdmin onActualizar={cargar} alVolver />
      <main id="contenido" className={a.contenido}>
        <div className={s.encabezado}>
          <div>
            <h1 className="page-title">Privacidad de la plataforma</h1>
            <p className="page-sub" style={{ maxWidth: "76ch" }}>
              El registro de cómo ComplianceAI trata los datos personales, generado directamente del inventario de datos y de
              los plazos de retención configurados. Usa las mismas herramientas y los mismos informes que entregamos a las
              empresas cliente.
            </p>
          </div>
          {datos ? (
            <div className={s.estado}>
              <span className={`badge ${estadoRegistro(datos.registro).tono}`}>{estadoRegistro(datos.registro).texto}</span>
              {datos.registro.cambio_desde_ultima ? <span className="badge tone-medio">Cambió desde la última emisión</span> : null}
            </div>
          ) : null}
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

        {!datos ? (
          <p className={a.vacio}>Generando el registro de la plataforma…</p>
        ) : (
          <>
            <div className={a.pestanas} role="tablist" aria-label="Secciones de la privacidad de la plataforma">
              {PESTANAS.map((p) => (
                <button
                  key={p.id}
                  id={`${id}-tab-${p.id}`}
                  type="button"
                  role="tab"
                  className={a.pestana}
                  aria-selected={pestana === p.id}
                  aria-controls={`${id}-panel-${p.id}`}
                  tabIndex={pestana === p.id ? 0 : -1}
                  onClick={() => setPestana(p.id)}
                  onKeyDown={(e) => moverPestana(e, p.id)}
                >
                  {p.texto}
                  {p.id === "revision" && datos.revision.hallazgos.length ? ` (${datos.revision.hallazgos.length})` : ""}
                  {p.id === "actividades" ? ` (${datos.actividades.length})` : ""}
                </button>
              ))}
            </div>

            {/* ============================================================ revisión interna */}
            {pestana === "revision" ? (
              <section role="tabpanel" id={`${id}-panel-revision`} aria-labelledby={`${id}-tab-revision`} className={a.formulario}>
                <Indicadores datos={datos} />
                <div className={s.dos}>
                  <section className="card" aria-labelledby={`${id}-hall`}>
                    <div className="card-head">
                      <div>
                        <h2 id={`${id}-hall`} className="card-title">Hallazgos</h2>
                        <p className="card-sub">Lo que conviene resolver para que el tratamiento de la plataforma quede en regla.</p>
                      </div>
                      <div className="chip-group" role="group" aria-label="Filtrar por nivel">
                        {FILTROS.filter((f) => f.id === "todos" || datos.revision.conteo[f.id as keyof typeof datos.revision.conteo]).map((f) => (
                          <button key={f.id} type="button" className="chip" aria-pressed={filtro === f.id} onClick={() => setFiltro(f.id)}>
                            {f.texto}
                          </button>
                        ))}
                      </div>
                    </div>
                    <ul className={s.hallazgos}>
                      {filtrarHallazgos(datos.revision.hallazgos, filtro).map((h) => (
                        <li key={h.codigo} className={s.hallazgo}>
                          <div className={s.hallazgoCab}>
                            <span className={`badge ${NIVEL_HALLAZGO[h.nivel].tono}`}>{NIVEL_HALLAZGO[h.nivel].texto}</span>
                            <strong>{h.titulo}</strong>
                            {h.actividades.length ? <span className={s.ambito}>{h.actividades.join(", ")}</span> : null}
                          </div>
                          <p>{h.detalle}</p>
                          <p className={s.recomendacion}>
                            <b>Qué hacer:</b> {h.recomendacion}
                          </p>
                          {h.ajuste ? <span className={s.tecnico} title="Ajuste técnico para el equipo de plataforma">Ajuste técnico: {h.ajuste}</span> : null}
                        </li>
                      ))}
                      {!datos.revision.hallazgos.length ? <li className={a.vacio}>No hay hallazgos: el tratamiento de la plataforma está en regla.</li> : null}
                    </ul>
                  </section>
                  <section className="card" aria-labelledby={`${id}-rev`}>
                    <div className="card-head">
                      <div>
                        <h2 id={`${id}-rev`} className="card-title">Revisiones automáticas</h2>
                        <p className="card-sub">Se repiten cada vez que abres o actualizas esta página.</p>
                      </div>
                    </div>
                    <ul className={s.revisiones}>
                      {datos.revision.revisiones.map((r) => (
                        <li key={r.codigo}>
                          <span className={s.punto} data-estado={r.estado} aria-hidden="true">{ICONO_REVISION[r.estado]}</span>
                          <span>
                            <span className="sr-only">{r.estado === "ok" ? "Correcto: " : r.estado === "alerta" ? "Atención: " : "Problema: "}</span>
                            {r.titulo}
                            {r.detalle ? <span className={s.sub}>{r.detalle}</span> : null}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                </div>
                <section className="card" aria-labelledby={`${id}-plazos`}>
                  <div className="card-head">
                    <div>
                      <h2 id={`${id}-plazos`} className="card-title">Plazos de retención vigentes</h2>
                      <p className="card-sub">De aquí salen los plazos del registro. Se cambian en la configuración o, el de encuestados, en Retención de datos.</p>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="table">
                      <caption className="sr-only">Plazos de retención que usa el registro</caption>
                      <thead><tr><th scope="col">Regla</th><th scope="col">Plazo</th><th scope="col">Origen</th></tr></thead>
                      <tbody>
                        {datos.ajustes.map((x) => (
                          <tr key={x.clave}>
                            <td>{x.nombre}<span className={s.tecnico} style={{ display: "block" }}>{x.clave}</span></td>
                            <td>{x.activo ? `${x.dias} ${x.dias === 1 ? "día" : "días"}` : <span className="badge tone-alto">Desactivada</span>}</td>
                            <td>{x.fuente === "panel" ? "Fijado en Retención de datos" : "Configuración de la plataforma"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </section>
            ) : null}

            {/* ============================================================ mapa */}
            {pestana === "mapa" ? (
              <section role="tabpanel" id={`${id}-panel-mapa`} aria-labelledby={`${id}-tab-mapa`} className={a.formulario}>
                <section className="card" aria-labelledby={`${id}-mapa`}>
                  <div className="card-head">
                    <div>
                      <h2 id={`${id}-mapa`} className="card-title">Mapa de datos de ComplianceAI</h2>
                      <p className="card-sub">
                        Quién opera la plataforma, dónde se guardan los datos ({datos.registro.pais_alojamiento_nombre}) y los
                        proveedores que los tratan por cuenta de Therion Labs. Elige un elemento para ver qué actividades lo usan.
                      </p>
                    </div>
                    <button type="button" className="btn btn-ghost btn-sm"
                      onClick={() => void descargar(apiPrivacidad.urlMapa(), "mapa_datos_plataforma.pdf")}>
                      <Icon name="descargar" aria-hidden="true" /> Descargar mapa (PDF)
                    </button>
                  </div>
                  <div className={s.mapa}>
                    {(["operacion", "almacenamiento", "proveedores"] as const).map((col) => (
                      <div key={col} className={s.columna}>
                        <h3>{col === "operacion" ? "Operación" : col === "almacenamiento" ? "Almacenamiento" : "Proveedores (encargados)"}</h3>
                        {datos.mapa.elementos.filter((e) => columnaMapa(e) === col).map((e) => (
                          <NodoMapa key={e.id} e={e} activo={nodo === e.id} garantia={datos.mapa.flujos.find((f) => f.destino_id === e.id)?.garantia_nombre ?? null}
                            onClick={() => setNodo(nodo === e.id ? null : e.id)} />
                        ))}
                      </div>
                    ))}
                  </div>
                  <p className={s.detalleNodo} aria-live="polite">
                    {nodo != null ? detalleNodo(datos.mapa.elementos.find((e) => e.id === nodo)) : "Todos los datos salen de la plataforma hacia el almacenamiento y los proveedores."}
                  </p>
                </section>
                <section className="card" aria-labelledby={`${id}-prov`}>
                  <div className="card-head">
                    <div>
                      <h2 id={`${id}-prov`} className="card-title">Proveedores y transferencias internacionales</h2>
                      <p className="card-sub">Cada proveedor figura como encargado del tratamiento, con su país y la garantía que respalda la transferencia.</p>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="table">
                      <caption className="sr-only">Proveedores de la plataforma</caption>
                      <thead>
                        <tr><th scope="col">Proveedor</th><th scope="col">Para qué</th><th scope="col">País</th><th scope="col">Rol</th><th scope="col">Garantía de la transferencia</th><th scope="col">Contrato</th></tr>
                      </thead>
                      <tbody>
                        {datos.proveedores.map((p) => (
                          <tr key={p.clave}>
                            <td><b>{p.nombre}</b></td>
                            <td>{p.descripcion}</td>
                            <td>{p.pais_nombre ?? <span className="badge tone-alto">Sin declarar</span>}</td>
                            <td>{p.rol_nombre}</td>
                            <td>{p.garantia_valida ? <span className="badge tone-ok">{p.garantia_nombre}</span> : <span className="badge tone-alto">Sin garantía documentada</span>}</td>
                            <td>{p.contrato_confirmado ? <span className="badge tone-ok">Confirmado</span> : <span className="badge tone-medio">Por confirmar</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className={a.ayuda} style={{ marginTop: "var(--sp-3)" }}>
                    Solo aparecen los proveedores que usa la configuración actual. Si el modelo de lenguaje se ejecuta en un servidor
                    propio, el proveedor de IA deja de figurar.
                  </p>
                </section>
              </section>
            ) : null}

            {/* ============================================================ actividades */}
            {pestana === "actividades" ? (
              <section role="tabpanel" id={`${id}-panel-actividades`} aria-labelledby={`${id}-tab-actividades`} className={a.formulario}>
                <p className="callout">
                  <Icon name="info" aria-hidden="true" />
                  <span>
                    Estas actividades no se editan a mano: salen del inventario de datos de la plataforma. Los plazos se leen de la
                    retención vigente, así que si cambias un plazo en <strong>Retención de datos</strong>, el registro se actualiza solo.
                  </span>
                </p>
                <div className={s.listaAct}>
                  {datos.actividades.map((act) => (
                    <button key={act.clave} type="button" className={s.act} onClick={(e) => abrirFicha(act, e.currentTarget)}
                      aria-haspopup="dialog">
                      <span>
                        <span className={s.actNombre}>{act.nombre}</span>
                        <span className={s.actDesc}>{act.descripcion}</span>
                      </span>
                      <span><span className={s.sub}>Base de licitud</span>{act.base_nombre.split(" (")[0]}</span>
                      <span className={s.plazos}>
                        <span className={s.sub}>Plazo de conservación</span>
                        {act.plazos.map((p) => (
                          <span key={p.categoria}>{p.categoria_nombre}: <b>{p.texto}</b></span>
                        ))}
                      </span>
                      <span className={`badge ${act.completa ? "tone-ok" : "tone-medio"}`}>{act.completa ? "Completa" : "Falta completar"}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            {/* ============================================================ informes */}
            {pestana === "informes" ? (
              <section role="tabpanel" id={`${id}-panel-informes`} aria-labelledby={`${id}-tab-informes`} className={a.formulario}>
                {datos.registro.cambio_desde_ultima || datos.ropa.cambio_desde_ultima ? (
                  <p className="callout callout-aviso">
                    <Icon name="alerta" aria-hidden="true" />
                    <span>
                      <strong>El registro cambió desde la última emisión.</strong> Genera los informes de nuevo para que la versión
                      descargable quede al día.
                    </span>
                  </p>
                ) : null}
                <div className={s.informes}>
                  <article className={`card ${s.informe}`} aria-labelledby={`${id}-rat`}>
                    <div className="card-head" style={{ marginBottom: 0 }}>
                      <div>
                        <h2 id={`${id}-rat`} className="card-title">Registro de actividades de tratamiento</h2>
                        <p className="card-sub">El mismo informe que descargan las empresas cliente.</p>
                      </div>
                      <span className={`badge ${datos.registro.oficial ? "tone-ok" : "tone-medio"}`}>{datos.registro.oficial ? "Oficial" : "Saldrá como borrador"}</span>
                    </div>
                    <ul>
                      <li>{datos.actividades.length} actividades de tratamiento</li>
                      <li>Plazos de conservación y su fundamento</li>
                      <li>Proveedores, países y transferencias</li>
                      <li>Riesgos y medidas de seguridad</li>
                    </ul>
                    {!datos.registro.oficial ? (
                      <details>
                        <summary className={a.ayuda}>Por qué saldrá como borrador</summary>
                        <ul>{datos.registro.motivos_borrador.map((m) => <li key={m}>{m}</li>)}</ul>
                      </details>
                    ) : null}
                    <BotonesInforme tipo="rat" datos={datos} emitiendo={emitiendo} onEmitir={emitir} onDescargar={descargar} />
                  </article>
                  <article className={`card ${s.informe}`} aria-labelledby={`${id}-ropa`}>
                    <div className="card-head" style={{ marginBottom: 0 }}>
                      <div>
                        <h2 id={`${id}-ropa`} className="card-title">RoPA de la plataforma</h2>
                        <p className="card-sub">Registro de operaciones de tratamiento de Therion Labs como responsable.</p>
                      </div>
                      <span className={`badge ${datos.ropa.puede_emitir ? "tone-ok" : "tone-medio"}`}>{datos.ropa.puede_emitir ? "Listo para generar" : "Faltan datos"}</span>
                    </div>
                    <ul>
                      <li>Datos de contacto de Therion Labs y su delegado</li>
                      <li>Una ficha por actividad</li>
                      <li>Transferencias internacionales y plazos</li>
                    </ul>
                    {!datos.ropa.puede_emitir ? <p className={a.ayuda}>{datos.ropa.texto_faltantes.replace("los datos de la empresa", "los datos de Therion Labs")}</p> : null}
                    <BotonesInforme tipo="ropa" datos={datos} emitiendo={emitiendo} onEmitir={emitir} onDescargar={descargar} />
                  </article>
                </div>

                <section className="card" aria-labelledby={`${id}-datos`}>
                  <div className="card-head">
                    <div>
                      <h2 id={`${id}-datos`} className="card-title">Datos de Therion Labs para el RoPA</h2>
                      <p className="card-sub">Se piden una vez y quedan guardados para las próximas emisiones. Usa canales de la organización, no los de una persona.</p>
                    </div>
                    <span className={`badge ${datos.ropa.puede_emitir ? "tone-ok" : "tone-medio"}`}>{datos.ropa.puede_emitir ? "Completo" : "Falta completar"}</span>
                  </div>
                  <form onSubmit={guardarRopa} noValidate className={a.formulario}>
                    <div className={a.rejilla}>
                      <div className={a.campo}>
                        <label htmlFor={`${id}-razon`}>Razón social</label>
                        <input id={`${id}-razon`} className={a.control} value={datos.organizacion.razon_social} readOnly />
                      </div>
                      <CampoRopa id={`${id}-dir`} etiqueta="Dirección" valor={ropa.direccion} onCambio={cambiar("direccion")}
                        mensaje={mensajeCampoRopa(datos.ropa.faltantes, "direccion", rechazo)} placeholder="Calle, número, comuna" />
                      <CampoRopa id={`${id}-correo`} etiqueta="Correo de privacidad" tipo="email" valor={ropa.correo} onCambio={cambiar("correo")}
                        mensaje={mensajeCampoRopa(datos.ropa.faltantes, "correo", rechazo)} placeholder="privacidad@therionlabs.cl" />
                      <CampoRopa id={`${id}-tel`} etiqueta="Teléfono" opcional valor={ropa.telefono} onCambio={cambiar("telefono")}
                        mensaje={mensajeCampoRopa([], "telefono", rechazo)} placeholder="+56 2 2345 6789" />
                    </div>
                    <fieldset className={a.grupo}>
                      <legend style={{ fontSize: "var(--fs-sm)", fontWeight: 600, marginBottom: 0 }}>¿Therion Labs tiene delegado de protección de datos?</legend>
                      <div className={s.siNo}>
                        {([true, false] as const).map((v) => (
                          <label key={String(v)}>
                            <input type="radio" name={`${id}-dpo`} checked={ropa.tiene_dpo === v} onChange={() => cambiar("tiene_dpo")(v)} />
                            {v ? "Sí" : "No"}
                          </label>
                        ))}
                      </div>
                      {mensajeCampoRopa(datos.ropa.faltantes, "tiene_dpo", rechazo) ? (
                        <p className={a.errorCampo}>{mensajeCampoRopa(datos.ropa.faltantes, "tiene_dpo", rechazo)}</p>
                      ) : null}
                      {ropa.tiene_dpo ? (
                        <div className={a.rejilla}>
                          <CampoRopa id={`${id}-dpocargo`} etiqueta="Cargo o área del delegado" valor={ropa.dpo_cargo} onCambio={cambiar("dpo_cargo")}
                            mensaje={mensajeCampoRopa(datos.ropa.faltantes, "dpo_cargo", rechazo)} placeholder="Oficial de Protección de Datos"
                            ayuda="El cargo o el área, no el nombre de una persona." />
                          <CampoRopa id={`${id}-dpocorreo`} etiqueta="Correo del delegado" tipo="email" valor={ropa.dpo_correo} onCambio={cambiar("dpo_correo")}
                            mensaje={mensajeCampoRopa(datos.ropa.faltantes, "dpo_correo", rechazo)} placeholder="dpo@therionlabs.cl" />
                        </div>
                      ) : null}
                    </fieldset>
                    {rechazo && !rechazo.campo ? <p className={a.errorCampo} role="alert">{rechazo.mensaje}</p> : null}
                    <div className={a.acciones}>
                      <button type="submit" className="btn btn-ghost" disabled={guardando} aria-busy={guardando}>Guardar datos</button>
                    </div>
                  </form>
                </section>

                <section className="card" aria-labelledby={`${id}-hist`}>
                  <div className="card-head">
                    <div>
                      <h2 id={`${id}-hist`} className="card-title">Historial de emisiones</h2>
                      <p className="card-sub">Cada emisión conserva su PDF, su planilla y un código para verificarla.</p>
                    </div>
                  </div>
                  {datos.emisiones.length ? (
                    <div className="table-wrap">
                      <table className="table">
                        <caption className="sr-only">Emisiones de los informes de la plataforma</caption>
                        <thead>
                          <tr><th scope="col">Informe</th><th scope="col">Versión</th><th scope="col">Código</th><th scope="col">Fecha</th><th scope="col">Estado</th><th scope="col"><span className="sr-only">Descargas</span></th></tr>
                        </thead>
                        <tbody>
                          {datos.emisiones.map((x) => (
                            <tr key={x.id}>
                              <td>{x.tipo_nombre}</td>
                              <td>{x.version}</td>
                              <td className="code">{x.codigo}</td>
                              <td>{fechaHoraChile(x.fecha)}</td>
                              <td><span className={`badge ${x.oficial ? "tone-ok" : "tone-medio"}`}>{x.tipo === "ropa" ? "Emitido" : x.oficial ? "Oficial" : "Borrador"}</span></td>
                              <td>
                                <div className={a.acciones}>
                                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => void descargar(apiPrivacidad.urlDescarga(x.id, "pdf"), x.archivos.pdf.nombre)}
                                    aria-label={`Descargar PDF de ${x.tipo_nombre} versión ${x.version}`}>PDF</button>
                                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => void descargar(apiPrivacidad.urlDescarga(x.id, "xlsx"), x.archivos.xlsx.nombre)}
                                    aria-label={`Descargar Excel de ${x.tipo_nombre} versión ${x.version}`}>Excel</button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className={a.vacio}>Aún no se ha emitido ningún informe de la plataforma.</p>
                  )}
                  <form onSubmit={verificar} className={a.campo} style={{ marginTop: "var(--sp-5)" }} noValidate>
                    <label htmlFor={`${id}-codigo`}>Verificar un código</label>
                    <div className={s.verificar}>
                      <input id={`${id}-codigo`} className={a.control} value={codigo} placeholder="CIA-PLAT-REG-2026-000003-7"
                        onChange={(e) => setCodigo(e.target.value.slice(0, 45))} aria-invalid={errorCodigo ? true : undefined}
                        aria-describedby={`${id}-codigo-res`} />
                      <button type="submit" className="btn btn-ghost">Verificar</button>
                    </div>
                    <p id={`${id}-codigo-res`} className={errorCodigo ? a.errorCampo : a.ayuda} aria-live="polite">
                      {errorCodigo ?? (verificacion ? (
                        <>
                          <span className={`badge ${verificacion.sigue_al_dia ? "tone-ok" : "tone-medio"}`}>Auténtico</span>{" "}
                          {verificacion.informe.tipo_nombre}, versión {verificacion.informe.version}, emitido el {fechaHoraChile(verificacion.informe.fecha)}. {verificacion.mensaje}
                        </>
                      ) : "Confirma que un informe presentado fue emitido por la plataforma y si sigue al día.")}
                    </p>
                  </form>
                </section>
              </section>
            ) : null}
          </>
        )}
      </main>

      {ficha ? (
        <>
          <div className={s.velo} onClick={cerrarFicha} aria-hidden="true" />
          <aside className={s.ficha} role="dialog" aria-modal="true" aria-labelledby={`${id}-ficha`}>
            <div className={s.fichaCab}>
              <div>
                <h2 id={`${id}-ficha`} className="card-title">{ficha.nombre}</h2>
                <span className={s.sub}>Área: {ficha.area} · Therion Labs actúa como {ficha.rol_nombre.toLowerCase()}</span>
              </div>
              <button ref={cerrarRef} type="button" className="btn btn-ghost btn-sm" onClick={cerrarFicha}>Cerrar</button>
            </div>
            <FichaActividad act={ficha} />
          </aside>
        </>
      ) : null}
    </div>
  );
}

function Indicadores({ datos }: { datos: ResumenPrivacidad }) {
  const plazos = contarPlazos(datos.actividades);
  const completas = datos.actividades.filter((x) => x.completa).length;
  const conGarantia = datos.proveedores.filter((p) => p.garantia_valida).length;
  const indicadores = [
    { etiqueta: "Actividades", valor: String(completas), de: `de ${datos.actividades.length}`, pista: "completas", medida: (100 * completas) / Math.max(datos.actividades.length, 1) },
    { etiqueta: "Plazos automáticos", valor: String(plazos.automaticos), de: `de ${plazos.total}`, pista: "salen de un plazo configurado", medida: (100 * plazos.automaticos) / Math.max(plazos.total, 1) },
    { etiqueta: "Proveedores", valor: String(conGarantia), de: `de ${datos.proveedores.length}`, pista: "con garantía declarada", medida: (100 * conGarantia) / Math.max(datos.proveedores.length, 1) },
    { etiqueta: "Hallazgos", valor: String(datos.revision.hallazgos.length), de: "", pista: resumenHallazgos(datos.revision.conteo), medida: null },
  ];
  return (
    <div className={s.kpis}>
      {indicadores.map((k) => (
        <div key={k.etiqueta} className="card kpi">
          <span className="kpi-label">{k.etiqueta}</span>
          <span className="kpi-value">{k.valor}{k.de ? <small>{k.de}</small> : null}</span>
          <span className="kpi-hint">{k.pista}</span>
          {k.medida !== null ? <div className="meter" aria-hidden="true"><span style={{ width: `${Math.round(k.medida)}%` }} /></div> : null}
        </div>
      ))}
    </div>
  );
}

function NodoMapa({ e, activo, garantia, onClick }: { e: ElementoMapa; activo: boolean; garantia: string | null; onClick: () => void }) {
  return (
    <button type="button" className={s.nodo} data-tipo={e.tipo} aria-pressed={activo} onClick={onClick}>
      <span className={s.nodoNombre}>{e.nombre}</span>
      <span className={s.nodoMeta}>
        <span className={s.pais} title={e.pais_nombre ?? "País sin declarar"}>{e.pais ?? "?"}</span>
        {e.descripcion}
      </span>
      {e.tipo === "tercero" ? (
        <span className={`badge ${garantia ? "tone-ok" : "tone-alto"}`} style={{ justifySelf: "start" }}>{garantia ?? "Sin garantía declarada"}</span>
      ) : null}
    </button>
  );
}

function detalleNodo(e: ElementoMapa | undefined): string {
  if (!e) return "";
  const donde = e.pais_nombre ? ` Está en ${e.pais_nombre}.` : " Su país no está declarado.";
  return `${e.nombre} participa en ${e.actividades.length} actividad(es): ${e.actividades.join(" · ")}.${donde}` +
    (e.categorias.length ? ` Datos: ${e.categorias.join(", ")}.` : "");
}

function FichaActividad({ act }: { act: Actividad }) {
  return (
    <div className={s.fichaCuerpo}>
      <p style={{ fontSize: "var(--fs-sm)", color: "var(--text-muted)" }}>{act.descripcion}</p>
      {!act.completa ? (
        <p className="callout callout-aviso">
          <Icon name="alerta" aria-hidden="true" />
          <span><strong>Falta completar.</strong> {act.faltantes.join(" ")}</span>
        </p>
      ) : null}
      <div><h4>Finalidades</h4><ul>{act.finalidades.map((f) => <li key={f}>{f}</li>)}</ul></div>
      <div><h4>Base de licitud</h4><p style={{ fontSize: "var(--fs-sm)" }}>{act.base_nombre}</p></div>
      <div><h4>De dónde vienen los datos</h4><ul>{act.fuentes.map((f) => <li key={f}>{f}</li>)}</ul></div>
      <div><h4>Titulares</h4><div className={s.etiquetas}>{act.titulares.map((t) => <span key={t} className={s.etiqueta}>{t}</span>)}</div></div>
      <div><h4>Datos que se tratan</h4><div className={s.etiquetas}>{act.datos.map((t) => <span key={t} className={s.etiqueta}>{t}</span>)}</div></div>
      <div>
        <h4>Plazos de conservación</h4>
        <ul>
          {act.plazos.map((p) => (
            <li key={p.categoria}>
              {p.categoria_nombre}: <b>{p.texto}</b>
              <span className={s.sub}>{p.fundamento}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4>Proveedores y transferencias</h4>
        <ul>
          {act.proveedores.map((p) => (
            <li key={p.clave}>
              {p.nombre} · {p.pais_nombre ?? "país sin declarar"} · {p.garantia_valida ? p.garantia_nombre : "sin garantía documentada"}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4>Medidas de seguridad</h4>
        <ul>{Object.entries(act.medidas).map(([g, m]) => <li key={g}><b>{g}:</b> {m.join(", ")}</li>)}</ul>
      </div>
      <div><h4>Decisiones automatizadas</h4><p style={{ fontSize: "var(--fs-sm)" }}>{act.decisiones}</p></div>
      {act.advertencias.length ? (
        <div><h4>Para revisar</h4><ul>{act.advertencias.map((x) => <li key={x}>{x}</li>)}</ul></div>
      ) : null}
      <p className={a.ayuda}>Esta ficha es lo mismo que aparece en el informe descargable.</p>
    </div>
  );
}

function CampoRopa({ id, etiqueta, valor, onCambio, mensaje, placeholder, tipo = "text", opcional = false, ayuda }: {
  id: string; etiqueta: string; valor: string | null; onCambio: (v: string) => void; mensaje: string | null;
  placeholder?: string; tipo?: string; opcional?: boolean; ayuda?: string;
}) {
  return (
    <div className={a.campo}>
      <label htmlFor={id}>{etiqueta}{opcional ? <span className={a.ayuda}> (opcional)</span> : null}</label>
      <input id={id} type={tipo} className={a.control} value={valor ?? ""} placeholder={placeholder}
        onChange={(e) => onCambio(e.target.value)} aria-invalid={mensaje ? true : undefined}
        aria-describedby={mensaje || ayuda ? `${id}-msg` : undefined} />
      {mensaje ? <p id={`${id}-msg`} className={a.errorCampo}>{mensaje}</p> : ayuda ? <p id={`${id}-msg`} className={a.ayuda}>{ayuda}</p> : null}
    </div>
  );
}

function BotonesInforme({ tipo, datos, emitiendo, onEmitir, onDescargar }: {
  tipo: TipoInforme; datos: ResumenPrivacidad; emitiendo: TipoInforme | null;
  onEmitir: (tipo: TipoInforme, forzar?: boolean) => void; onDescargar: (url: string, nombre: string) => void;
}) {
  const ultima = datos.ultimas[tipo];
  const bloqueado = tipo === "ropa" && !datos.ropa.puede_emitir;
  return (
    <div style={{ display: "grid", gap: "var(--sp-3)" }}>
      <div className="acciones" style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}>
        <button type="button" className="btn btn-primary" disabled={emitiendo !== null || bloqueado} aria-busy={emitiendo === tipo}
          onClick={() => onEmitir(tipo)}>
          <Icon name={emitiendo === tipo ? "refrescar" : "documento"} aria-hidden="true" />
          {emitiendo === tipo ? "Generando…" : "Generar PDF y Excel"}
        </button>
        {ultima ? (
          <>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDescargar(apiPrivacidad.urlDescarga(ultima.id, "pdf"), ultima.archivos.pdf.nombre)}>
              <Icon name="pdf" aria-hidden="true" /> PDF
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDescargar(apiPrivacidad.urlDescarga(ultima.id, "xlsx"), ultima.archivos.xlsx.nombre)}>
              <Icon name="tabla" aria-hidden="true" /> Excel
            </button>
          </>
        ) : null}
      </div>
      <p style={{ fontSize: "var(--fs-xs)", color: "var(--text-muted)" }}>
        {ultima ? `Última emisión: versión ${ultima.version}, ${fechaHoraChile(ultima.fecha)} (${ultima.codigo}).` : "Aún no se ha emitido."}
      </p>
    </div>
  );
}
