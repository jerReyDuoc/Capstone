"use client";

/**
 * HU-27 · Panel interno de Therion Labs.
 *
 *   Solicitudes  — las de contratación (HU-31). Se marcan contratadas y se eligen las que
 *                  pasarán a una empresa (solo contratadas, autorizadas y completadas).
 *   Alta         — empresa nueva (razón social, RUT, rubro, contrato) + usuario definitivo
 *                  (nombre, email; rol único cliente), o asociar a una empresa existente.
 *                  Una sola operación en el backend: si algo falla no queda nada a medias.
 *   Empresas     — contrato, estado del usuario y reenvío del enlace de activación.
 *   Bitácora     — lo que quedó registrado (HU-09).
 *
 * El admin nunca ve ni define la contraseña: el enlace va solo al correo del usuario.
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { BrandMark } from "@/components/ui/Icon";
import {
  api,
  comoErrorAdmin,
  ETIQUETA_ESTADO_SOLICITUD,
  ETIQUETA_ESTADO_USUARIO,
  formatearRut,
  rutValido,
  seleccionable,
  type Empresa,
  type ErrorAdmin,
  type EstadoSolicitud,
  type FilaBitacora,
  type ResultadoAlta,
  type Solicitud,
} from "@/lib/admin/api";
import { pedir } from "@/lib/encuesta/cliente";
import s from "./admin.module.css";

type Pestana = "solicitudes" | "empresas" | "bitacora";
const FILTROS: (EstadoSolicitud | "todas")[] = ["contratada", "pendiente", "migrada", "descartada", "todas"];

const hoyISO = () => new Date().toISOString().slice(0, 10);
const enUnAnio = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
};
const fecha = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString("es-CL") : "—");

function Estado({ texto, tono }: { texto: string; tono: string }) {
  return <span className={`badge tone-${tono}`}>{texto}</span>;
}

export function PanelClientes() {
  const router = useRouter();
  const [pestana, setPestana] = useState<Pestana>("solicitudes");
  const [filtro, setFiltro] = useState<EstadoSolicitud | "todas">("contratada");
  const [solicitudes, setSolicitudes] = useState<Solicitud[] | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [bitacora, setBitacora] = useState<FilaBitacora[] | null>(null);
  const [rubros, setRubros] = useState<{ id: number; nombre: string }[]>([]);
  const [seleccion, setSeleccion] = useState<number[]>([]);
  const [error, setError] = useState<ErrorAdmin | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const manejarError = useCallback(
    (e: unknown) => {
      const err = comoErrorAdmin(e);
      if (err.codigo === "SESION_EXPIRADA") {
        router.replace("/admin/login?motivo=sesion");
        return;
      }
      setError(err);
    },
    [router],
  );

  const cargarSolicitudes = useCallback(async () => {
    try {
      const r = await api.solicitudes(filtro === "todas" ? undefined : filtro);
      setSolicitudes(r.items);
    } catch (e) {
      manejarError(e);
    }
  }, [filtro, manejarError]);

  const cargarEmpresas = useCallback(async () => {
    try {
      setEmpresas((await api.empresas()).items);
    } catch (e) {
      manejarError(e);
    }
  }, [manejarError]);

  const cargarBitacora = useCallback(async () => {
    try {
      setBitacora((await api.bitacora()).items);
    } catch (e) {
      manejarError(e);
    }
  }, [manejarError]);

  useEffect(() => {
    void cargarSolicitudes();
  }, [cargarSolicitudes]);
  useEffect(() => {
    void cargarEmpresas();
    api
      .rubros()
      .then((r) => setRubros(r.map((x) => ({ id: x.id, nombre: x.nombre_rubro?.trim() || `Rubro ${x.id}` }))))
      .catch(manejarError);
  }, [cargarEmpresas, manejarError]);
  useEffect(() => {
    if (pestana === "bitacora") void cargarBitacora();
  }, [pestana, cargarBitacora]);

  const elegidas = useMemo(
    () => (solicitudes ?? []).filter((x) => seleccion.includes(x.id)),
    [solicitudes, seleccion],
  );

  async function cambiarEstado(id: number, estado: EstadoSolicitud) {
    setError(null);
    try {
      await api.cambiarEstado(id, estado);
      setAviso(`Solicitud #${id}: ${ETIQUETA_ESTADO_SOLICITUD[estado].texto.toLowerCase()}.`);
      setSeleccion((sel) => sel.filter((x) => x !== id));
      await cargarSolicitudes();
    } catch (e) {
      manejarError(e);
    }
  }

  async function reenviar(empresa: Empresa) {
    setError(null);
    try {
      const r = await api.reenviar(empresa.id);
      setAviso(`${empresa.razon_social}: ${r.activacion.mensaje}`);
      await cargarEmpresas();
    } catch (e) {
      manejarError(e);
    }
  }

  async function salir() {
    await pedir("/bff/admin/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/admin/login");
  }

  function alTerminarAlta(texto: string) {
    setAviso(texto);
    setSeleccion([]);
    void cargarSolicitudes();
    void cargarEmpresas();
  }

  return (
    <div className={s.pagina}>
      <header className={s.barra}>
        <div className={s.marca}>
          <BrandMark aria-hidden="true" />
          <span>
            ComplianceAI
            <span className={s.marcaSub}>Panel interno · Therion Labs</span>
          </span>
        </div>
        <button className="btn btn-ghost btn-sm" type="button" onClick={salir}>
          Cerrar sesión
        </button>
      </header>

      <main id="contenido" className={s.contenido}>
        <div>
          <h1 className="page-title">Empresas cliente</h1>
          <p className="page-sub">
            Da de alta a la empresa que contrató, crea su usuario definitivo y traspásale la evaluación que hizo como
            usuario temporal, sin repetir el autodiagnóstico.
          </p>
        </div>

        {aviso ? (
          <p className="callout" role="status">
            {aviso}{" "}
            <button type="button" className="link-btn" onClick={() => setAviso(null)}>
              Cerrar
            </button>
          </p>
        ) : null}
        {error ? (
          <div className={s.alerta} role="alert">
            <strong>{error.mensaje}</strong>
            <span className={s.mono}>{error.codigo}</span>
          </div>
        ) : null}

        <div className={s.pestanas} role="tablist" aria-label="Secciones del panel">
          {(
            [
              ["solicitudes", "Solicitudes de contratación"],
              ["empresas", "Empresas"],
              ["bitacora", "Bitácora"],
            ] as [Pestana, string][]
          ).map(([clave, texto]) => (
            <button key={clave} role="tab" type="button" className={s.pestana} aria-selected={pestana === clave}
                    onClick={() => setPestana(clave)}>
              {texto}
            </button>
          ))}
        </div>

        {pestana === "solicitudes" ? (
          <>
            <section className="card" aria-labelledby="titulo-solicitudes">
              <div className="card-head">
                <div>
                  <h2 id="titulo-solicitudes" className="card-title">Solicitudes</h2>
                  <p className="card-sub">
                    Marca como contratadas las que cerraron acuerdo y elige las evaluaciones que pasarán a la empresa.
                  </p>
                </div>
                <div className={s.filtros} role="group" aria-label="Filtrar por estado">
                  {FILTROS.map((f) => (
                    <button key={f} type="button" className="chip" aria-pressed={filtro === f}
                            onClick={() => { setFiltro(f); setSeleccion([]); }}>
                      {f === "todas" ? "Todas" : ETIQUETA_ESTADO_SOLICITUD[f].texto}
                    </button>
                  ))}
                </div>
              </div>
              <TablaSolicitudes solicitudes={solicitudes} seleccion={seleccion}
                                alternar={(id) => setSeleccion((sel) => sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id])}
                                cambiarEstado={cambiarEstado} />
            </section>
            <FormAlta elegidas={elegidas} rubros={rubros} empresas={empresas ?? []}
                      onError={manejarError} onListo={alTerminarAlta} limpiarError={() => setError(null)} />
          </>
        ) : null}

        {pestana === "empresas" ? <TablaEmpresas empresas={empresas} reenviar={reenviar} /> : null}
        {pestana === "bitacora" ? <TablaBitacora filas={bitacora} /> : null}
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ solicitudes */
function TablaSolicitudes({
  solicitudes, seleccion, alternar, cambiarEstado,
}: {
  solicitudes: Solicitud[] | null;
  seleccion: number[];
  alternar: (id: number) => void;
  cambiarEstado: (id: number, estado: EstadoSolicitud) => void;
}) {
  if (!solicitudes) return <p className={s.vacio}>Cargando…</p>;
  if (!solicitudes.length) return <p className={s.vacio}>No hay solicitudes con este estado.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Solicitudes de contratación</caption>
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">Elegir</span></th>
            <th scope="col">Solicitud</th>
            <th scope="col">Contacto</th>
            <th scope="col">Evaluación</th>
            <th scope="col">Autoriza traspaso</th>
            <th scope="col">Estado</th>
            <th scope="col">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {solicitudes.map((x) => {
            const puede = seleccionable(x);
            const e = ETIQUETA_ESTADO_SOLICITUD[x.estado];
            return (
              <tr key={x.id}>
                <td>
                  <input type="checkbox" className={s.casilla} disabled={!puede} checked={seleccion.includes(x.id)}
                         onChange={() => alternar(x.id)}
                         aria-label={`Elegir solicitud ${x.id} para el alta`}
                         title={puede ? "" : "Solo contratadas, con autorización y evaluación completada"} />
                </td>
                <td>
                  #{x.id}
                  <span className={s.sub}>{fecha(x.fecha_creacion)}</span>
                  {x.razon_social_declarada ? <span className={s.sub}>{x.razon_social_declarada}</span> : null}
                </td>
                <td>
                  {x.contacto.nombre ?? "—"}
                  <span className={s.sub}>{x.contacto.email ?? (x.estado === "migrada" ? "Traspasado al usuario definitivo" : "Borrado")}</span>
                  {x.contacto.telefono ? <span className={s.sub}>{x.contacto.telefono}</span> : null}
                </td>
                <td>
                  #{x.evaluacion.id} · {x.evaluacion.rubro ?? "sin rubro"}
                  <span className={s.sub}>
                    {x.evaluacion.completada ? "Completada" : "En progreso"}
                    {x.evaluacion.puntaje_general != null ? ` · ${x.evaluacion.puntaje_general} / 100` : ""}
                  </span>
                </td>
                <td>{x.autoriza_migracion ? "Sí" : "No"}</td>
                <td><Estado texto={e.texto} tono={e.tono} /></td>
                <td>
                  <div className={s.acciones}>
                    {x.estado === "pendiente" ? (
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => cambiarEstado(x.id, "contratada")}>
                        Marcar contratada
                      </button>
                    ) : null}
                    {x.estado === "contratada" ? (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => cambiarEstado(x.id, "pendiente")}>
                        Volver a pendiente
                      </button>
                    ) : null}
                    {x.estado === "pendiente" || x.estado === "contratada" ? (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => cambiarEstado(x.id, "descartada")}>
                        Descartar
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ alta */
function FormAlta({
  elegidas, rubros, empresas, onError, onListo, limpiarError,
}: {
  elegidas: Solicitud[];
  rubros: { id: number; nombre: string }[];
  empresas: Empresa[];
  onError: (e: unknown) => void;
  onListo: (texto: string) => void;
  limpiarError: () => void;
}) {
  const id = useId();
  const [modo, setModo] = useState<"nueva" | "existente">("nueva");
  const [razon, setRazon] = useState("");
  const [rut, setRut] = useState("");
  const [rubro, setRubro] = useState<number | "">("");
  const [inicio, setInicio] = useState(hoyISO);
  const [termino, setTermino] = useState(enUnAnio);
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoAlta | null>(null);

  // Prellenado desde la primera solicitud elegida (el admin puede corregir todo)
  const primera = elegidas[0];
  useEffect(() => {
    if (!primera) return;
    setRazon((v) => v || primera.razon_social_declarada || "");
    setNombre((v) => v || primera.contacto.nombre || "");
    setEmail((v) => v || primera.contacto.email || "");
    setRubro((v) => v || primera.evaluacion.rubro_id || "");
  }, [primera]);

  function validar(): Record<string, string> {
    const e: Record<string, string> = {};
    if (!elegidas.length) e.solicitudes = "Elige al menos una solicitud contratada en la tabla.";
    if (modo === "existente") {
      if (!empresaId) e.empresa = "Elige la empresa.";
      return e;
    }
    if (razon.trim().length < 2) e.razon_social = "Escribe la razón social.";
    if (!rutValido(rut)) e.rut = "RUT inválido (ejemplo: 76.123.456-7).";
    if (!rubro) e.rubro_id = "Elige el rubro.";
    if (!inicio || !termino) e.fecha_termino_contrato = "Indica las fechas del contrato.";
    else if (termino < inicio) e.fecha_termino_contrato = "El término debe ser igual o posterior al inicio.";
    if (nombre.trim().length < 2) e.nombre = "Escribe el nombre del usuario.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/.test(email.trim())) e.email = "Revisa el correo.";
    return e;
  }

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    if (enviando) return;
    const e = validar();
    setErrores(e);
    if (Object.keys(e).length) return;
    setEnviando(true);
    setResultado(null);
    limpiarError();
    const ids = elegidas.map((x) => x.id);
    try {
      if (modo === "existente") {
        const r = await api.asociar(Number(empresaId), ids);
        const emp = empresas.find((x) => x.id === Number(empresaId));
        onListo(`${r.evaluaciones_migradas.length} evaluación(es) traspasadas a ${emp?.razon_social ?? "la empresa"}.`);
      } else {
        const r = await api.alta({
          empresa: { razon_social: razon.trim(), rut: rut.trim(), rubro_id: Number(rubro),
                     fecha_inicio_contrato: inicio, fecha_termino_contrato: termino },
          usuario: { nombre: nombre.trim(), email: email.trim() },
          solicitudes_ids: ids,
        });
        setResultado(r);
        setRazon(""); setRut(""); setNombre(""); setEmail(""); setRubro("");
        onListo(`Empresa ${r.empresa.razon_social} creada.`);
      }
    } catch (err) {
      const info = comoErrorAdmin(err);
      if (info.campo) setErrores({ [info.campo]: info.mensaje });
      onError(err);
    } finally {
      setEnviando(false);
    }
  }

  const err = (campo: string) =>
    errores[campo] ? <span id={`${id}-${campo}-err`} className={s.errorCampo}>{errores[campo]}</span> : null;
  const invalido = (campo: string) => (errores[campo] ? { "aria-invalid": true, "aria-describedby": `${id}-${campo}-err` } : {});

  return (
    <section className="card" aria-labelledby={`${id}-titulo`}>
      <div className="card-head">
        <div>
          <h2 id={`${id}-titulo`} className="card-title">Alta de empresa y usuario definitivo</h2>
          <p className="card-sub">
            En una sola operación: se crea la empresa y su usuario (rol cliente), se traspasan las evaluaciones elegidas
            con sus respuestas, evidencias, resultados, plan formativo e informes, se cierra el acceso temporal y se envía
            el enlace de activación.
          </p>
        </div>
      </div>

      {resultado ? <ResumenAlta r={resultado} /> : null}

      <form className={s.formulario} onSubmit={enviar} noValidate>
        <div className={s.campo}>
          <span className="field-label">Evaluaciones que pasan a la empresa</span>
          {elegidas.length ? (
            <div className={s.seleccionadas}>
              {elegidas.map((x) => (
                <span key={x.id} className={s.pildora}>
                  Solicitud #{x.id} · evaluación #{x.evaluacion.id}
                </span>
              ))}
            </div>
          ) : (
            <p className={s.ayuda}>Elige una o más solicitudes contratadas en la tabla de arriba.</p>
          )}
          {err("solicitudes")}
        </div>

        <div className={s.modo} role="radiogroup" aria-label="Destino">
          <label><input type="radio" name="modo" checked={modo === "nueva"} onChange={() => setModo("nueva")} /> Empresa nueva</label>
          <label><input type="radio" name="modo" checked={modo === "existente"} onChange={() => setModo("existente")} /> Empresa existente</label>
        </div>

        {modo === "existente" ? (
          <div className={s.campo}>
            <label htmlFor={`${id}-empresa`}>Empresa</label>
            <select id={`${id}-empresa`} className={s.control} value={empresaId}
                    onChange={(e) => setEmpresaId(e.target.value ? Number(e.target.value) : "")} {...invalido("empresa")}>
              <option value="">Elige…</option>
              {empresas.map((x) => (
                <option key={x.id} value={x.id}>{x.razon_social} ({formatearRut(x.rut)})</option>
              ))}
            </select>
            {err("empresa")}
          </div>
        ) : (
          <>
            <fieldset className={s.grupo}>
              <legend>Empresa</legend>
              <div className={s.rejilla}>
                <div className={s.campo}>
                  <label htmlFor={`${id}-razon`}>Razón social</label>
                  <input id={`${id}-razon`} className={s.control} value={razon} maxLength={150}
                         onChange={(e) => setRazon(e.target.value)} {...invalido("razon_social")} />
                  {err("razon_social")}
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-rut`}>RUT de la empresa</label>
                  <input id={`${id}-rut`} className={s.control} value={rut} maxLength={12} inputMode="text"
                         placeholder="76.123.456-7" onChange={(e) => setRut(e.target.value)} {...invalido("rut")} />
                  {err("rut")}
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-rubro`}>Rubro</label>
                  <select id={`${id}-rubro`} className={s.control} value={rubro}
                          onChange={(e) => setRubro(e.target.value ? Number(e.target.value) : "")} {...invalido("rubro_id")}>
                    <option value="">Elige…</option>
                    {rubros.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                  </select>
                  {err("rubro_id")}
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-inicio`}>Inicio del contrato</label>
                  <input id={`${id}-inicio`} type="date" className={s.control} value={inicio}
                         onChange={(e) => setInicio(e.target.value)} />
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-termino`}>Término del contrato</label>
                  <input id={`${id}-termino`} type="date" className={s.control} value={termino} min={inicio}
                         onChange={(e) => setTermino(e.target.value)} {...invalido("fecha_termino_contrato")} />
                  {err("fecha_termino_contrato")}
                </div>
              </div>
            </fieldset>
            <fieldset className={s.grupo}>
              <legend>Usuario definitivo</legend>
              <p className={s.ayuda}>
                Uno por empresa, con el único rol <strong>cliente</strong>. Recibirá un enlace de un solo uso para definir su
                contraseña; nunca se envía una contraseña.
              </p>
              <div className={s.rejilla}>
                <div className={s.campo}>
                  <label htmlFor={`${id}-nombre`}>Nombre</label>
                  <input id={`${id}-nombre`} className={s.control} value={nombre} maxLength={120} autoComplete="off"
                         onChange={(e) => setNombre(e.target.value)} {...invalido("nombre")} />
                  {err("nombre")}
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-email`}>Correo</label>
                  <input id={`${id}-email`} type="email" className={s.control} value={email} maxLength={100}
                         autoComplete="off" onChange={(e) => setEmail(e.target.value)} {...invalido("email")} />
                  {err("email")}
                </div>
              </div>
            </fieldset>
          </>
        )}

        <div className={s.acciones}>
          <button type="submit" className="btn btn-primary" disabled={enviando || !elegidas.length}>
            {enviando ? "Procesando…" : modo === "nueva" ? "Crear empresa y traspasar" : "Traspasar a la empresa"}
          </button>
        </div>
        <p className={s.nota}>
          Al traspasar, la clave temporal deja de funcionar y el usuario temporal queda cerrado: su correo y el contacto de
          la solicitud se eliminan (el contacto queda solo en el usuario definitivo).
        </p>
      </form>
    </section>
  );
}

function ResumenAlta({ r }: { r: ResultadoAlta }) {
  return (
    <div className={s.exito} role="status">
      <strong>
        {r.empresa.razon_social} ({formatearRut(r.empresa.rut)}) quedó creada con su usuario {r.usuario.nombre}.
      </strong>
      <ul>
        {r.evaluaciones_migradas.map((m) => (
          <li key={m.evaluacion_id}>
            Evaluación #{m.evaluacion_id}: {m.respuestas} respuestas, {m.evidencias} evidencias, {m.dimensiones_resumen} dimensiones
            de resultados{m.plan_formativo ? ", plan formativo e informe disponibles" : ""}.
          </li>
        ))}
      </ul>
      <span className={s.nota}>{r.activacion.mensaje}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ empresas */
function TablaEmpresas({ empresas, reenviar }: { empresas: Empresa[] | null; reenviar: (e: Empresa) => void }) {
  return (
    <section className="card" aria-labelledby="titulo-empresas">
      <div className="card-head">
        <div>
          <h2 id="titulo-empresas" className="card-title">Empresas cliente</h2>
          <p className="card-sub">Si el enlace venció o no llegó, reenvíalo: el anterior deja de servir.</p>
        </div>
      </div>
      {!empresas ? (
        <p className={s.vacio}>Cargando…</p>
      ) : !empresas.length ? (
        <p className={s.vacio}>Aún no hay empresas cliente.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Empresas cliente</caption>
            <thead>
              <tr>
                <th scope="col">Empresa</th>
                <th scope="col">Contrato</th>
                <th scope="col">Usuario definitivo</th>
                <th scope="col">Evaluaciones</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {empresas.map((e) => {
                const u = e.usuario;
                const est = u ? ETIQUETA_ESTADO_USUARIO[u.estado] : null;
                return (
                  <tr key={e.id}>
                    <td>{e.razon_social}<span className={s.sub}>{formatearRut(e.rut)}</span></td>
                    <td>
                      {fecha(e.fecha_inicio_contrato)} – {fecha(e.fecha_termino_contrato)}
                      <span className={s.sub}>
                        <Estado texto={e.contrato_vigente ? "Vigente" : "No vigente"} tono={e.contrato_vigente ? "ok" : "alto"} />
                      </span>
                    </td>
                    <td>
                      {u ? <>{u.nombre}<span className={s.sub}>{u.email}</span></> : "—"}
                      {est ? <span className={s.sub}><Estado texto={est.texto} tono={est.tono} /></span> : null}
                    </td>
                    <td>{e.evaluaciones ?? 0}</td>
                    <td>
                      {u?.estado === "pendiente_activacion" ? (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => reenviar(e)}>
                          Reenviar activación
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ bitácora */
function TablaBitacora({ filas }: { filas: FilaBitacora[] | null }) {
  return (
    <section className="card" aria-labelledby="titulo-bitacora">
      <div className="card-head">
        <div>
          <h2 id="titulo-bitacora" className="card-title">Bitácora de auditoría</h2>
          <p className="card-sub">Registro de solo inserción (últimas 100 acciones). No contiene datos personales.</p>
        </div>
      </div>
      {!filas ? (
        <p className={s.vacio}>Cargando…</p>
      ) : !filas.length ? (
        <p className={s.vacio}>Sin registros.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Bitácora de auditoría</caption>
            <thead>
              <tr>
                <th scope="col">Fecha (UTC)</th>
                <th scope="col">Actor</th>
                <th scope="col">Acción</th>
                <th scope="col">Entidad</th>
                <th scope="col">Resultado</th>
                <th scope="col">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.id}>
                  <td className={s.mono}>{f.fecha.replace("T", " ").slice(0, 19)}</td>
                  <td>{f.actor_rol}{f.actor_id != null ? ` #${f.actor_id}` : ""}</td>
                  <td className={s.mono}>{f.accion}</td>
                  <td>{f.entidad}{f.entidad_id != null ? ` #${f.entidad_id}` : ""}</td>
                  <td><Estado texto={f.resultado} tono={f.resultado === "ok" ? "ok" : "alto"} /></td>
                  <td className={`${s.mono} ${s.detalle}`}>{f.detalle ? JSON.stringify(f.detalle) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
