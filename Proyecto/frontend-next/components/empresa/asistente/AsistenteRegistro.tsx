"use client";

/**
 * /empresa/asistente — Asistente de registro.
 *
 *   Recorrido    las seis áreas de la entrevista como una ruta, y cómo va tomando forma el registro.
 *   Conversación la pregunta actual en grande, con ejemplos, y el historial de la entrevista. También se
 *                puede subir un documento de la empresa para que proponga actividades.
 *   Propuestas   agrupadas por tipo (sistemas, flujos, actividades). Cada una se acepta, se edita o se
 *                descarta; nada entra al mapa ni al registro sin confirmación, y cada una muestra con qué
 *                modelo y versión de la guía se hizo.
 *   Revisión     alertas de lo ya guardado y el camino a los informes.
 *
 * Si la ayuda automática no está disponible, la entrevista sigue igual y todo se completa a mano.
 * Todo el texto se pinta como texto con React (nunca HTML).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { BrandMark, Icon, type IconName } from "@/components/ui/Icon";
import {
  ACCEPT_DOCUMENTO, AVISO_DOCUMENTO, CODIGO_AYUDA_NO_DISPONIBLE, ETIQUETA_ESTADO, ETIQUETA_INCONSISTENCIA, MOTIVOS_DESCARTE, NIVEL_CONFIANZA,
  aceptarPropuesta, agruparPropuestas, cambiarArea, cantidad, cargarAsistente, cerrarEntrevista, cuotaTexto,
  dependenciasPendientes, descartarPropuesta, diccionario, etiquetaIa, explicacionesSueltas, filasPropuesta,
  iniciarEntrevista, progresoEntrevista, responderPregunta, subirDocumento, tipoVisual, tituloTipo, tonoSeveridad,
  validarDocumento, validarRespuesta,
  type AreaApi, type CodigoArea, type Diccionario, type EstadoAsistente, type InconsistenciaApi, type MotivoDescarte,
  type PayloadPropuesta, type PropuestaApi, type TipoVisual,
} from "@/lib/asistente";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { cargarCatalogoMapa, type CatalogoMapa } from "@/lib/mapaDatos";
import { cargarCatalogoRat, type CatalogoRat } from "@/lib/registroActividades";
import { useEspacioEmpresa } from "../EspacioEmpresaContexto";
import { EditorPropuesta } from "./EditorPropuesta";
import a from "./asistente.module.css";

type Carga = { tipo: "cargando" } | { tipo: "listo" } | { tipo: "error"; mensaje: string };
type Ocupado = "" | "respuesta" | "documento" | "area";

const ICONO_TIPO: Record<TipoVisual, IconName> = {
  sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa", flujo: "flujo", actividad: "libro",
};
const CLASE_TIPO: Record<TipoVisual, string> = {
  sistema: a.tipoSistema, base_datos: a.tipoBase, tercero: a.tipoTercero, flujo: a.tipoFlujo, actividad: a.tipoActividad,
};

function mensaje(e: unknown, porDefecto: string): string {
  return e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : porDefecto;
}

export function AsistenteRegistro() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const [estado, setEstado] = useState<EstadoAsistente | null>(null);
  const [catMapa, setCatMapa] = useState<CatalogoMapa | null>(null);
  const [catRat, setCatRat] = useState<CatalogoRat | null>(null);
  const [aviso, setAviso] = useState("");
  const [nuevas, setNuevas] = useState<number[]>([]);
  const dic = useMemo<Diccionario>(() => diccionario(catMapa, catRat), [catMapa, catRat]);

  useEffect(() => {
    if (espacio.tipo !== "listo") return;
    Promise.all([cargarAsistente(), cargarCatalogoMapa().catch(() => null), cargarCatalogoRat().catch(() => null)])
      .then(([e, m, r]) => {
        setEstado(e);
        setCatMapa(m);
        setCatRat(r);
        setCarga({ tipo: "listo" });
      })
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
        }
        setCarga({ tipo: "error", mensaje: mensaje(e, "No pudimos cargar el asistente. Inténtalo de nuevo.") });
      });
  }, [espacio.tipo, router]);

  /** Aplica la respuesta de una acción: el backend siempre devuelve el estado completo. */
  function aplicar(e: EstadoAsistente, porDefecto = "") {
    setEstado(e);
    setNuevas(e.nuevas ?? []);
    setAviso(e.aviso ?? porDefecto);
  }

  const encabezado = (
    <header className={a.encabezado}>
      <h1 className="page-title">Asistente de registro</h1>
      <p className="page-sub">
        Cuéntanos cómo trabaja tu empresa y te proponemos el mapa de datos y el registro de actividades ya
        pre-llenados. Tú decides qué se guarda.
      </p>
    </header>
  );

  if (espacio.tipo === "cargando" || (espacio.tipo === "listo" && carga.tipo === "cargando")) {
    return (
      <>
        {encabezado}
        <div className="skeleton" style={{ height: 320 }} role="status" aria-label="Cargando el asistente" />
      </>
    );
  }
  if (espacio.tipo === "error" || carga.tipo === "error" || !estado) {
    return (
      <>
        {encabezado}
        <div className={a.alerta} role="alert">
          <strong>{espacio.tipo === "error" ? espacio.mensaje : carga.tipo === "error" ? carga.mensaje : ""}</strong>
        </div>
      </>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <>
        {encabezado}
        <p className="callout" role="status">
          El asistente es parte del servicio contratado y el de tu empresa no está activo. Contacta a Therion Labs para
          renovarlo.
        </p>
      </>
    );
  }

  return (
    <>
      {encabezado}
      {estado.sesion ? <Recorrido estado={estado} alCambiar={aplicar} /> : null}
      <div className={estado.sesion ? a.layout : a.layoutInicio}>
        <section className={a.conversacion} aria-labelledby="titulo-entrevista">
          {estado.sesion ? <Conversacion estado={estado} alCambiar={aplicar} /> : <Bienvenida estado={estado} alCambiar={aplicar} />}
        </section>
        <section className={a.panelPropuestas} aria-labelledby="titulo-propuestas">
          <Propuestas estado={estado} dic={dic} catMapa={catMapa} catRat={catRat} nuevas={nuevas} alCambiar={aplicar} />
        </section>
      </div>
      <Revision estado={estado} />

      <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
      {aviso ? (
        <p className={a.aviso} role="status" aria-hidden="true">
          <Icon name="info" /> <span>{aviso}</span>
          <button type="button" className={a.cerrarAviso} onClick={() => setAviso("")} aria-label="Cerrar aviso">
            <Icon name="cerrar" />
          </button>
        </p>
      ) : null}
    </>
  );
}

/* ================================================================== recorrido (lo memorable) */
function Recorrido({ estado, alCambiar }: { estado: EstadoAsistente; alCambiar: (e: EstadoAsistente, aviso?: string) => void }) {
  const sesion = estado.sesion!;
  const [ocupado, setOcupado] = useState(false);
  const { hechas, total } = progresoEntrevista(sesion);
  // La línea avanza de estación en estación: llega hasta el área actual (o al final si terminó)
  const indice = sesion.terminada ? sesion.areas.length - 1 : Math.max(0, sesion.areas.findIndex((x) => x.actual));
  const avance = sesion.areas.length > 1 ? indice / (sesion.areas.length - 1) : 0;
  const pendientes = estado.propuestas.filter((p) => p.estado === "sugerida").length;
  const m = estado.mapa;

  async function irA(area: AreaApi) {
    if (ocupado || area.actual) return;
    setOcupado(true);
    try {
      alCambiar(await cambiarArea(sesion.id, area.codigo as CodigoArea));
    } catch (e) {
      alCambiar(estado, mensaje(e, "No pudimos cambiar de área."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <section className={a.recorrido} aria-label="Avance de la entrevista">
      <nav aria-label="Áreas de la entrevista" className={a.trayecto}>
        <ol style={{ ["--avance" as string]: String(avance) }}>
          {sesion.areas.map((x) => (
            <li key={x.codigo} className={`${a.estacion} ${x.completada ? a.hecha : ""} ${x.actual ? a.actual : ""}`}>
              <button type="button" onClick={() => irA(x)} disabled={ocupado || x.actual}
                aria-current={x.actual ? "step" : undefined}>
                <span className={a.punto} aria-hidden="true">{x.completada ? <Icon name="check" /> : null}</span>
                <span className={a.nombreEstacion}>{x.nombre}</span>
                <span className="sr-only">
                  {x.completada ? " (completada)" : x.actual ? " (área actual)" : ""}
                </span>
              </button>
            </li>
          ))}
        </ol>
        <p className={a.progreso}>{hechas} de {total} preguntas</p>
      </nav>
      <p className={a.registroVivo}>
        Tu registro tiene <strong>{cantidad(m.elementos, "elemento", "elementos")}</strong>,{" "}
        <strong>{cantidad(m.flujos, "flujo", "flujos")}</strong> y{" "}
        <strong>{cantidad(m.actividades, "actividad", "actividades")}</strong>.
        {pendientes ? <> <span className={a.esperan}>{cantidad(pendientes, "propuesta espera", "propuestas esperan")} tu revisión.</span></> : null}
      </p>
    </section>
  );
}

/* ================================================================== bienvenida */
function Bienvenida({ estado, alCambiar }: { estado: EstadoAsistente; alCambiar: (e: EstadoAsistente, aviso?: string) => void }) {
  const [ocupado, setOcupado] = useState<Ocupado>("");
  const [error, setError] = useState("");
  const total = estado.areas.reduce((n, x) => n + x.preguntas, 0);

  async function ejecutar(tipo: Ocupado, accion: () => Promise<EstadoAsistente>) {
    if (ocupado) return false;
    setOcupado(tipo);
    setError("");
    try {
      alCambiar(await accion());
      return true;
    } catch (e) {
      setError(mensaje(e, "No pudimos completar la acción. Inténtalo de nuevo."));
      return false;
    } finally {
      setOcupado("");
    }
  }

  return (
    <div className={a.bienvenida}>
      <BrandMark className={a.marcaGrande} />
      <h2 id="titulo-entrevista" className={a.titularBienvenida}>Armemos tu registro conversando</h2>
      <p className={a.textoBienvenida}>
        Son {total} preguntas cortas sobre cómo trabaja tu empresa. Puedes saltar las que no apliquen y seguir otro
        día: tu avance queda guardado.
      </p>
      <ol className={a.rutaInicio} aria-label="Áreas de la entrevista">
        {estado.areas.map((x) => (
          <li key={x.codigo}>
            <button type="button" disabled={!!ocupado} onClick={() => ejecutar("area", () => iniciarEntrevista(x.codigo))}>
              <strong>{x.nombre}</strong>
              <span>{x.descripcion}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className={a.acciones}>
        <button type="button" className="btn btn-primary" disabled={!!ocupado}
          onClick={() => ejecutar("area", () => iniciarEntrevista())}>
          <Icon name="play" /> {ocupado === "area" ? "Preparando…" : "Empezar la entrevista"}
        </button>
        <span className={a.nota}>o elige por dónde partir</span>
      </div>
      <SubirDocumento estado={estado} sesionId={null} ocupado={ocupado}
        alSubir={(archivo) => ejecutar("documento", () => subirDocumento(archivo, null))} />
      {error ? <p className={a.error} role="alert">{error}</p> : null}
    </div>
  );
}

/* ================================================================== conversación */
function Conversacion({ estado, alCambiar }: { estado: EstadoAsistente; alCambiar: (e: EstadoAsistente, aviso?: string) => void }) {
  const sesion = estado.sesion!;
  const [texto, setTexto] = useState("");
  const [error, setError] = useState("");
  const [fallaIa, setFallaIa] = useState("");
  const [ocupado, setOcupado] = useState<Ocupado>("");
  const log = useRef<HTMLDivElement>(null);
  const max = estado.limites.max_caracteres;
  const p = sesion.pregunta;

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [estado.mensajes.length, ocupado]);

  async function ejecutar(tipo: Ocupado, accion: () => Promise<EstadoAsistente>, porDefecto = "") {
    if (ocupado) return false;
    setOcupado(tipo);
    setError("");
    try {
      alCambiar(await accion(), porDefecto);
      return true;
    } catch (e) {
      setError(mensaje(e, "No pudimos completar la acción. Inténtalo de nuevo."));
      return false;
    } finally {
      setOcupado("");
    }
  }

  /** Envía la respuesta. Si la ayuda automática falla, el texto se conserva para reintentar o guardar sin ayuda. */
  async function mandar(sinIa: boolean) {
    const problema = validarRespuesta(texto, max);
    if (problema) {
      setError(problema);
      return;
    }
    if (ocupado) return;
    setOcupado("respuesta");
    setError("");
    setFallaIa("");
    try {
      alCambiar(await responderPregunta(sesion.id, texto.trim(), false, sinIa));
      setTexto("");
    } catch (e) {
      if (e instanceof ErrorBff && e.info.codigo === CODIGO_AYUDA_NO_DISPONIBLE) {
        setFallaIa(e.info.mensaje || "La ayuda automática no respondió esta vez.");
      } else {
        setError(mensaje(e, "No pudimos enviar tu respuesta. Inténtalo de nuevo."));
      }
    } finally {
      setOcupado("");
    }
  }

  function enviar(ev: FormEvent) {
    ev.preventDefault();
    void mandar(false);
  }

  return (
    <>
      <div className={a.cabeza}>
        <h2 className={a.tituloSeccion} id="titulo-entrevista">Conversación</h2>
        <button type="button" className="btn btn-ghost btn-sm" disabled={!!ocupado}
          onClick={() => ejecutar("area", () => cerrarEntrevista(sesion.id), "Terminaste la entrevista. Tus propuestas siguen disponibles.")}>
          Terminar entrevista
        </button>
      </div>

      <div className={a.log} ref={log} role="log" aria-live="polite" aria-relevant="additions"
        aria-label="Conversación con el asistente">
        {estado.mensajes.length === 0 ? (
          <p className={a.vacio}>Aquí verás lo que respondes y lo que el asistente entendió.</p>
        ) : null}
        {estado.mensajes.map((m) => (
          <div key={m.id} className={`${a.turno} ${m.rol === "usuario" ? a.turnoUsuario : a.turnoAsistente}`}>
            {m.rol === "asistente" ? <BrandMark className={a.avatar} /> : null}
            <div className={`${a.burbuja} ${m.bloqueado ? a.bloqueado : ""}`}>
              <span className="sr-only">{m.rol === "usuario" ? "Tú:" : "Asistente:"}</span>
              {m.contenido.split("\n\n").map((parrafo, i) => <p key={i}>{parrafo}</p>)}
            </div>
          </div>
        ))}
        {ocupado === "respuesta" ? (
          <div className={`${a.turno} ${a.turnoAsistente}`} role="status">
            <BrandMark className={a.avatar} />
            <div className={`${a.burbuja} ${a.escribiendo}`}>
              <span className={a.puntos} aria-hidden="true"><i /><i /><i /></span>
              <span className="sr-only">Analizando tu respuesta</span>
            </div>
          </div>
        ) : null}
      </div>

      {p ? (
        <form className={a.pregunta} onSubmit={enviar} noValidate>
          <p className={a.paso}>{sesion.area_nombre}, pregunta {sesion.paso + 1} de {sesion.total_pasos}</p>
          <label htmlFor="respuesta-asistente" className={a.textoPregunta}>{p.texto}</label>
          <p className={a.ayuda} id="ayuda-respuesta">{p.ayuda}</p>
          {p.ejemplos.length ? (
            <div className={a.ejemplos} role="group" aria-label="Usar una respuesta de ejemplo">
              {p.ejemplos.map((x) => (
                <button key={x} type="button" className={a.ejemplo} onClick={() => setTexto(x)} disabled={!!ocupado}>
                  {x}
                </button>
              ))}
            </div>
          ) : null}
          <div className={a.caja}>
            <textarea id="respuesta-asistente" className={a.texto} rows={3} value={texto} maxLength={max}
              aria-describedby="ayuda-respuesta contador-respuesta" disabled={!!ocupado}
              onChange={(e) => setTexto(e.target.value)} placeholder="Cuéntalo con tus palabras"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) (e.currentTarget.form as HTMLFormElement | null)?.requestSubmit();
              }} />
            <div className={a.barraCaja}>
              <span className={a.contador} id="contador-respuesta">{texto.length} / {max}</span>
              <button type="button" className="btn btn-ghost btn-sm" disabled={!!ocupado}
                onClick={() => ejecutar("respuesta", () => responderPregunta(sesion.id, "", true))}>
                Saltar pregunta
              </button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={!!ocupado || !texto.trim()}>
                <Icon name="enviar" /> {ocupado === "respuesta" ? "Analizando…" : "Enviar"}
              </button>
            </div>
          </div>
          {fallaIa ? (
            <div className={a.fallaIa} role="alert">
              <p><Icon name="reloj" /> {fallaIa}</p>
              <div className={a.acciones}>
                <button type="button" className="btn btn-primary btn-sm" disabled={!!ocupado} onClick={() => mandar(false)}>
                  <Icon name="refrescar" /> Volver a intentar
                </button>
                <button type="button" className="btn btn-ghost btn-sm" disabled={!!ocupado} onClick={() => mandar(true)}>
                  Guardar sin ayuda
                </button>
              </div>
            </div>
          ) : null}
        </form>
      ) : (
        <div className={a.fin} role="status">
          <Icon name="check" />
          <div>
            <strong>Terminaste la entrevista.</strong>
            <p>Revisa las propuestas pendientes y las alertas del registro. Si quieres agregar algo, elige un área en la ruta de arriba.</p>
          </div>
        </div>
      )}
      <p className={a.cuota}><Icon name="info" /> {cuotaTexto(estado)}</p>
      <SubirDocumento estado={estado} sesionId={sesion.id} ocupado={ocupado}
        alSubir={(archivo) => ejecutar("documento", () => subirDocumento(archivo, sesion.id))} />
      {error ? <p className={a.error} role="alert">{error}</p> : null}
    </>
  );
}

function SubirDocumento({
  estado, sesionId, ocupado, alSubir,
}: {
  estado: EstadoAsistente;
  sesionId: number | null;
  ocupado: string;
  alSubir: (archivo: File) => Promise<boolean>;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const id = `doc-asistente-${sesionId ?? "inicio"}`;

  async function subir(ev: FormEvent) {
    ev.preventDefault();
    const problema = validarDocumento(archivo, estado.limites.max_mb_documento);
    setError(problema ?? "");
    if (problema || !archivo) return;
    if (await alSubir(archivo)) {
      setArchivo(null);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className={a.documento}>
      <form onSubmit={subir} noValidate className={a.zona}>
        <Icon name="documento" className={a.iconoZona} />
        <div className={a.textoZona}>
          <label htmlFor={id}><strong>¿Tienes una política, un contrato con un proveedor o un aviso de privacidad?</strong></label>
          <span>Lo leemos para proponerte actividades y no guardamos el archivo. PDF, Word o texto, hasta {estado.limites.max_mb_documento} MB.</span>
          <input id={id} ref={input} type="file" accept={ACCEPT_DOCUMENTO} disabled={!!ocupado} className={a.archivo}
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </div>
        <button type="submit" className="btn btn-ghost btn-sm" disabled={!!ocupado || !archivo}>
          <Icon name="subir" /> {ocupado === "documento" ? "Leyendo…" : "Analizar"}
        </button>
      </form>
      {error ? <p className={a.error} role="alert">{error}</p> : null}
      {estado.documentos.length ? (
        <ul className={a.documentos} aria-label="Documentos analizados">
          {estado.documentos.slice(0, 4).map((d) => (
            <li key={d.id} className={d.estado === "listo" ? a.docOk : a.docAviso}>
              <span className={a.nombreDoc}>{d.nombre_archivo}</span>
              <span className={a.metaDoc}>{d.tipo_documento_nombre}, {AVISO_DOCUMENTO[d.estado].toLowerCase()}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ================================================================== propuestas */
function Propuestas({
  estado, dic, catMapa, catRat, nuevas, alCambiar,
}: {
  estado: EstadoAsistente;
  dic: Diccionario;
  catMapa: CatalogoMapa | null;
  catRat: CatalogoRat | null;
  nuevas: number[];
  alCambiar: (e: EstadoAsistente, aviso?: string) => void;
}) {
  const [vista, setVista] = useState<"pendientes" | "revisadas">("pendientes");
  const pendientes = estado.propuestas.filter((p) => p.estado === "sugerida");
  const revisadas = estado.propuestas.filter((p) => p.estado !== "sugerida");
  const grupos = agruparPropuestas(vista === "pendientes" ? pendientes : revisadas);

  return (
    <>
      <div className={a.cabeza}>
        <h2 className={a.tituloSeccion} id="titulo-propuestas">Propuestas</h2>
        <div className={a.pestanas} role="group" aria-label="Qué propuestas ver">
          <button type="button" aria-pressed={vista === "pendientes"} onClick={() => setVista("pendientes")}>
            Por revisar <span className={a.contadorPestana}>{pendientes.length}</span>
          </button>
          <button type="button" aria-pressed={vista === "revisadas"} onClick={() => setVista("revisadas")}>
            Revisadas <span className={a.contadorPestana}>{revisadas.length}</span>
          </button>
        </div>
      </div>
      <p className={a.ayuda}>Nada se guarda en tu mapa ni en tu registro hasta que lo aceptes.</p>
      {grupos.length === 0 ? (
        <div className={a.sinPropuestas}>
          <Icon name="chispa" />
          <p>
            {vista === "pendientes"
              ? "Responde una pregunta o sube un documento y aquí aparecerán los sistemas, flujos y actividades que te proponemos."
              : "Las propuestas que aceptes o descartes quedarán aquí."}
          </p>
        </div>
      ) : (
        grupos.map((g) => (
          <section key={g.tipo} className={a.grupo} aria-label={g.titulo}>
            <h3 className={a.tituloGrupo}>{g.titulo} <span>{g.propuestas.length}</span></h3>
            <ul className={a.propuestas}>
              {g.propuestas.map((p) => (
                <li key={p.id}>
                  <TarjetaPropuesta propuesta={p} estado={estado} dic={dic} catMapa={catMapa} catRat={catRat}
                    nueva={nuevas.includes(p.id)} alCambiar={alCambiar} />
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </>
  );
}

function Confianza({ nivel }: { nivel: PropuestaApi["confianza"] }) {
  const c = NIVEL_CONFIANZA[nivel];
  return (
    <span className={`${a.confianza} ${nivel === "baja" ? a.confianzaBaja : ""}`} title={c.texto}>
      <span className={a.segmentos} aria-hidden="true">
        {[1, 2, 3].map((i) => <i key={i} className={i <= c.segmentos ? a.lleno : ""} />)}
      </span>
      <span className="sr-only">{c.texto}</span>
      {nivel === "baja" ? <span aria-hidden="true">Revísala con cuidado</span> : null}
    </span>
  );
}

function TarjetaPropuesta({
  propuesta: p, estado, dic, catMapa, catRat, nueva, alCambiar,
}: {
  propuesta: PropuestaApi;
  estado: EstadoAsistente;
  dic: Diccionario;
  catMapa: CatalogoMapa | null;
  catRat: CatalogoRat | null;
  nueva: boolean;
  alCambiar: (e: EstadoAsistente, aviso?: string) => void;
}) {
  const [modo, setModo] = useState<"ver" | "editar" | "descartar">("ver");
  const [motivo, setMotivo] = useState<MotivoDescarte>("no_aplica");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const filas = filasPropuesta(p, dic, estado.referencias);
  const sueltas = explicacionesSueltas(p, filas);
  const deps = dependenciasPendientes(p, estado.propuestas);
  const pendiente = p.estado === "sugerida";
  const titulo = p.nombre || tituloTipo(p);
  const visual = tipoVisual(p);

  async function aceptar(payload?: PayloadPropuesta) {
    setOcupado(true);
    setError("");
    try {
      alCambiar(await aceptarPropuesta(p.id, estado.mapa.version, payload),
        p.tipo === "actividad"
          ? `Agregamos «${titulo}» a tu registro como borrador. Revísala allí antes de dejarla vigente.`
          : `Agregamos «${titulo}» a tu mapa de datos.`);
      setModo("ver");
    } catch (e) {
      setError(mensaje(e, "No pudimos guardar la propuesta. Inténtalo de nuevo."));
    } finally {
      setOcupado(false);
    }
  }

  async function descartar(ev: FormEvent) {
    ev.preventDefault();
    setOcupado(true);
    setError("");
    try {
      alCambiar(await descartarPropuesta(p.id, motivo), `Descartaste «${titulo}».`);
    } catch (e) {
      setError(mensaje(e, "No pudimos descartar la propuesta."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <article className={`${a.tarjeta} ${CLASE_TIPO[visual]} ${nueva ? a.nueva : ""} ${pendiente ? "" : a.decidida}`}
      aria-labelledby={`propuesta-${p.id}`}>
      <div className={a.tituloTarjeta}>
        <span className={a.iconoTipo} aria-hidden="true"><Icon name={ICONO_TIPO[visual]} /></span>
        <div className={a.nombreTarjeta}>
          <h4 id={`propuesta-${p.id}`}>{titulo}</h4>
          <span className={a.tipo}>{tituloTipo(p)}</span>
        </div>
        <div className={a.badges}>
          {p.riesgo_nivel ? <span className={`badge ${tonoSeveridad(p.riesgo_nivel)}`}>Riesgo {p.riesgo_nivel.toLowerCase()}</span> : null}
          {!pendiente ? <span className="badge tone-info">{ETIQUETA_ESTADO[p.estado]}</span> : null}
        </div>
      </div>
      <div className={a.procedencia}>
        <span className={a.etiquetaIa}><Icon name="chispa" /> {etiquetaIa(p)}</span>
        {pendiente ? <Confianza nivel={p.confianza} /> : null}
      </div>

      {modo === "editar" && catMapa && catRat ? (
        <EditorPropuesta propuesta={p} referencias={estado.referencias} catMapa={catMapa} catRat={catRat}
          ocupado={ocupado} alGuardar={aceptar} alCancelar={() => setModo("ver")} />
      ) : (
        <>
          <dl className={a.filas}>
            {filas.map((f) => (
              <div key={f.campo} className={a.fila}>
                <dt>{f.etiqueta}</dt>
                <dd>
                  {f.valor}
                  {f.explicacion ? (
                    <details className={a.porque}>
                      <summary>¿Por qué?</summary>
                      <p>{f.explicacion}</p>
                    </details>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          {sueltas.length ? (
            <details className={a.porque}>
              <summary>Más explicaciones</summary>
              <ul>{sueltas.map(([k, v]) => <li key={k}>{v}</li>)}</ul>
            </details>
          ) : null}
        </>
      )}

      {pendiente && p.inconsistencias.length ? <Alertas items={p.inconsistencias} titulo="Antes de aceptar" compacta /> : null}
      {pendiente && deps.length ? (
        <p className={a.dependencia} role="note">
          <Icon name="candado" /> Primero acepta {deps.map((d) => `«${d.nombre ?? tituloTipo(d)}»`).join(" y ")}: esta propuesta lo usa.
        </p>
      ) : null}

      {pendiente && modo === "ver" ? (
        <div className={a.accionesTarjeta}>
          <button type="button" className="btn btn-primary btn-sm" disabled={ocupado || deps.length > 0} onClick={() => aceptar()}>
            <Icon name="check" /> {ocupado ? "Guardando…" : "Aceptar"}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" disabled={ocupado || !catMapa || !catRat}
            onClick={() => setModo("editar")}>
            <Icon name="editar" /> Editar
          </button>
          <button type="button" className={a.botonDescartar} disabled={ocupado} onClick={() => setModo("descartar")}>
            Descartar
          </button>
        </div>
      ) : null}
      {pendiente && modo === "descartar" ? (
        <form className={a.descartar} onSubmit={descartar}>
          <label htmlFor={`motivo-${p.id}`}>¿Por qué la descartas?</label>
          <select id={`motivo-${p.id}`} value={motivo} onChange={(e) => setMotivo(e.target.value as MotivoDescarte)}>
            {MOTIVOS_DESCARTE.map((m) => <option key={m.codigo} value={m.codigo}>{m.nombre}</option>)}
          </select>
          <button type="submit" className="btn btn-ghost btn-sm" disabled={ocupado}>Descartar</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setModo("ver")}>Volver</button>
        </form>
      ) : null}
      {p.estado === "aceptada" || p.estado === "editada" ? (
        <p className={a.destino}>
          {p.entidad_destino === "rat_actividad"
            ? <Link href="/empresa/registro-actividades">Ver en el registro de actividades</Link>
            : <Link href="/empresa/mapa-datos">Ver en el mapa de datos</Link>}
          {p.estado === "editada" ? <span>La editaste antes de aceptarla.</span> : null}
        </p>
      ) : null}
      {error ? <p className={a.error} role="alert">{error}</p> : null}
    </article>
  );
}

function Alertas({ items, titulo, compacta }: { items: InconsistenciaApi[]; titulo: string; compacta?: boolean }) {
  return (
    <div className={`${a.alertas} ${compacta ? a.alertasCompactas : ""}`} role="note" aria-label={titulo}>
      <p className={a.alertasTitulo}><Icon name="alerta" /> {titulo}</p>
      <ul>
        {items.map((i, n) => (
          <li key={`${i.codigo}-${n}`} className={i.severidad === "Crítica" || i.severidad === "Alta" ? a.alertaAlta : a.alertaMedia}>
            <strong>{ETIQUETA_INCONSISTENCIA[i.codigo] ?? "Alerta"}</strong>
            <span>{i.texto}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ================================================================== revisión e informes */
function Revision({ estado }: { estado: EstadoAsistente }) {
  const sinAyuda = !estado.ia.habilitada || estado.ia.cuota.respuestas.restantes === 0;
  return (
    <section className={a.revision} aria-labelledby="titulo-revision">
      <div className={a.revisionTexto}>
        <h2 className={a.tituloSeccion} id="titulo-revision">Revisión de tu registro</h2>
        {estado.revision.length ? (
          <p className={a.ayuda}>
            Encontramos {cantidad(estado.revision.length, "punto", "puntos")} por resolver en lo que ya guardaste.
          </p>
        ) : (
          <p className={a.ayuda}>Lo que ya guardaste no tiene alertas.</p>
        )}
        {sinAyuda ? (
          <p className={a.ayuda}>
            Sin la ayuda automática puedes completar todo a mano: en el mapa de datos hay sugerencias según tu evaluación
            y plantillas para tu rubro.
          </p>
        ) : null}
        <div className={a.enlaces}>
          <Link className="btn btn-ghost btn-sm" href="/empresa/mapa-datos"><Icon name="mapa" /> Mapa de datos</Link>
          <Link className="btn btn-ghost btn-sm" href="/empresa/registro-actividades"><Icon name="lista" /> Registro de actividades</Link>
          <Link className="btn btn-ghost btn-sm" href="/empresa/mapa-datos"><Icon name="pdf" /> Informe del mapa</Link>
          <Link className="btn btn-ghost btn-sm" href="/empresa/registro-actividades"><Icon name="pdf" /> Informe del registro</Link>
        </div>
      </div>
      {estado.revision.length ? <Alertas items={estado.revision.slice(0, 12)} titulo="Lo que conviene resolver" /> : null}
    </section>
  );
}
