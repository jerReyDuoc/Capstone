"use client";

/**
 * HU-32 · "Mis derechos": el titular ejerce sus derechos ARCOP desde la página web.
 *
 *   - Usuario temporal (perfil "encuestado"): entró con su N.º de evaluación + clave (/retomar
 *     o /mis-derechos) y lo usa desde /panel/mis-derechos.
 *   - Usuario definitivo (perfil "cliente"): lo usa desde /empresa/mis-derechos, con o sin
 *     contrato vigente (HU-30).
 *
 * La pantalla responde tres preguntas, en este orden:
 *   1. ¿Hay algo que deba hacer yo? → aviso arriba si una solicitud espera mi respuesta.
 *   2. ¿Qué quiero hacer? → seis tarjetas en lenguaje claro ("Corregir un dato", no
 *      "Rectificación"), y un formulario que se adapta al derecho elegido.
 *   3. ¿Cómo van mis solicitudes? → lista con estado, plazo y, al abrir una, su avance, la
 *      respuesta, la descarga de datos (acceso/portabilidad resuelta) y el historial.
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { descargarBlob } from "@/lib/exportar";
import { fechaChile } from "@/lib/fechas";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  DERECHOS, DESCRIPCION_MAX, DESCRIPCION_MIN, EFECTO_SUPRESION, ESTADOS, TIPOS_ARCOP,
  accionesTitular, apiTitular, errorTexto, exportable, mensajeError,
  type CatalogoArcop, type DetalleArcop, type FormatoExportacion, type PerfilTitular, type SolicitudArcop, type TipoArcop,
} from "@/lib/arcop";
import { Icon } from "@/components/ui/Icon";
import { BadgeEstadoArcop, CampoTexto, Historial, Plazo, Progreso } from "./Comunes";
import s from "./arcop.module.css";

type Estado = { tipo: "cargando" } | { tipo: "listo"; items: SolicitudArcop[] } | { tipo: "error"; mensaje: string };

const LOGIN_DE: Record<PerfilTitular, string> = {
  encuestado: "/mis-derechos?motivo=sesion",
  cliente: "/ingresar?motivo=sesion",
};

export function DerechosTitular({ perfil, evaluacionId }: { perfil: PerfilTitular; evaluacionId?: number | null }) {
  const router = useRouter();
  const api = useRef(apiTitular(perfil)).current;
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [catalogo, setCatalogo] = useState<CatalogoArcop | null>(null);
  const [elegido, setElegido] = useState<TipoArcop | null>(null);
  const [creada, setCreada] = useState<DetalleArcop | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const alExpirar = useCallback(
    (e: unknown) => {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace(LOGIN_DE[perfil]);
        return true;
      }
      return false;
    },
    [router, perfil],
  );

  const cargar = useCallback(async () => {
    try {
      const pagina = await api.listar();
      setEstado({ tipo: "listo", items: pagina.items });
    } catch (e) {
      if (alExpirar(e)) return;
      setEstado({ tipo: "error", mensaje: mensajeError(e, "No pudimos cargar tus solicitudes.") });
    }
  }, [api, alExpirar]);

  useEffect(() => {
    void cargar();
    api.catalogo().then(setCatalogo).catch(() => setCatalogo(null));
  }, [api, cargar]);

  function elegir(tipo: TipoArcop) {
    setCreada(null);
    setElegido((actual) => (actual === tipo ? null : tipo));
    // el formulario aparece debajo de las tarjetas: se lleva la vista y el foco ahí
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }

  async function alCrear(d: DetalleArcop) {
    setElegido(null);
    setCreada(d);
    await cargar();
  }

  const items = estado.tipo === "listo" ? estado.items : [];
  const esperandome = items.filter((x) => x.estado === "pendiente_informacion");

  return (
    <div className={s.pagina}>
      <header className="page-head">
        <div>
          <span className="eyebrow">Privacidad · Ley 21.719</span>
          <h1 className="page-title">Mis derechos sobre mis datos</h1>
          <p className="page-sub">
            Puedes pedir ver, corregir, llevarte o eliminar tus datos personales. Elige qué quieres hacer y un responsable
            de Therion Labs te responderá {catalogo?.plazo_respuesta_dias ? `en un plazo de ${catalogo.plazo_respuesta_dias} días corridos` : "dentro del plazo legal"}.
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-ghost" onClick={() => void cargar()} aria-label="Actualizar mis solicitudes">
            <Icon name="refrescar" />
            Actualizar
          </button>
        </div>
      </header>

      {esperandome.length ? (
        <div className="callout callout-aviso" role="status">
          <Icon name="alerta" aria-hidden="true" />
          <div>
            <strong>
              {esperandome.length === 1 ? "Una solicitud necesita tu respuesta" : `${esperandome.length} solicitudes necesitan tu respuesta`}
            </strong>
            <p style={{ marginTop: 4 }}>
              El responsable te pidió un antecedente para continuar.{" "}
              <button type="button" className="link-btn" onClick={() => setAbierta(esperandome[0].id_solicitud)}>
                Responder ahora
              </button>
            </p>
          </div>
        </div>
      ) : null}

      {/* ---------------------------------------------------------- 1. qué quieres hacer */}
      <section className="card" aria-labelledby="titulo-derechos" style={{ display: "grid", gap: 20 }}>
        <div>
          <h2 id="titulo-derechos" className="card-title">¿Qué quieres hacer?</h2>
          <p className="card-sub">Elige una opción. Te explicamos qué pasa antes de enviar.</p>
        </div>
        <ul className={s.derechos}>
          {TIPOS_ARCOP.map((tipo) => {
            const d = DERECHOS[tipo];
            return (
              <li key={tipo}>
                <button type="button" className={s.derecho} aria-pressed={elegido === tipo} onClick={() => elegir(tipo)}>
                  <span className={`${s.derechoIcono} ${tipo === "supresion" ? s.derechoIconoAlerta : ""}`} aria-hidden="true">
                    <Icon name={d.icono} />
                  </span>
                  <span className={s.derechoTitulo}>
                    {d.accion}
                    <span className={s.derechoNombre}>Derecho de {d.nombre.toLowerCase()}</span>
                  </span>
                  <span className={s.derechoTexto}>{d.descripcion}</span>
                </button>
              </li>
            );
          })}
        </ul>

        <div ref={formRef}>
          {elegido ? (
            <FormSolicitud
              key={elegido}
              tipo={elegido}
              perfil={perfil}
              catalogo={catalogo}
              crear={api.crear}
              onCreada={alCrear}
              onCerrar={() => setElegido(null)}
              onExpirada={alExpirar}
            />
          ) : creada ? (
            <SolicitudEnviada solicitud={creada} onVer={() => { setAbierta(creada.id_solicitud); setCreada(null); }} />
          ) : null}
        </div>
      </section>

      {/* ---------------------------------------------------------- 2. mis solicitudes */}
      <section aria-labelledby="titulo-mis-solicitudes" style={{ display: "grid", gap: 12 }}>
        <div>
          <h2 id="titulo-mis-solicitudes" className="card-title">Mis solicitudes</h2>
          <p className="card-sub">Abre una solicitud para ver en qué va, la respuesta y su historial.</p>
        </div>
        {estado.tipo === "cargando" ? (
          <div className="skeleton" style={{ height: 120 }} role="status" aria-label="Cargando tus solicitudes" />
        ) : estado.tipo === "error" ? (
          <div className="callout callout-aviso" role="alert">
            <Icon name="alerta" aria-hidden="true" />
            <div>
              <strong>{estado.mensaje}</strong>{" "}
              <button type="button" className="link-btn" onClick={() => void cargar()}>Reintentar</button>
            </div>
          </div>
        ) : !items.length ? (
          <div className={s.vacio}>
            <strong>Aún no tienes solicitudes</strong>
            <span>Cuando envíes una, aquí podrás seguir su avance.</span>
          </div>
        ) : (
          <ul className={s.lista}>
            {items.map((x) => (
              <ItemSolicitud
                key={x.id_solicitud}
                solicitud={x}
                abierta={abierta === x.id_solicitud}
                alternar={() => setAbierta((a) => (a === x.id_solicitud ? null : x.id_solicitud))}
                api={api}
                onCambio={cargar}
                onExpirada={alExpirar}
              />
            ))}
          </ul>
        )}
      </section>

      {/* ---------------------------------------------------------- 3. ayuda */}
      <section className={s.ayudas} aria-label="Ayuda">
        <div className={s.ayudaTarjeta}>
          <strong>Sigue tu solicitud sin ingresar</strong>
          <span>
            Cada solicitud tiene un código de seguimiento (ARC-XXXX-XXXX). Con él puedes consultar su estado en{" "}
            <a href="/mis-derechos#seguimiento">Mis derechos</a>, incluso si ya no tienes acceso.
          </span>
        </div>
        <div className={s.ayudaTarjeta}>
          <strong>¿Qué datos guardamos?</strong>
          <span>
            {perfil === "cliente"
              ? "Tu nombre, tu correo y tus accesos a la cuenta. Los textos que escribes se guardan sin datos personales."
              : `Tu rubro, tu correo si lo diste y tus respuestas${evaluacionId ? ` de la evaluación N.º ${evaluacionId}` : ""}. Los textos que escribes se guardan sin datos personales.`}{" "}
            Detalle en el <a href="/aviso-legal">aviso legal</a>.
          </span>
        </div>
      </section>
    </div>
  );
}

/* ================================================================== formulario */
function FormSolicitud({
  tipo, perfil, catalogo, crear, onCreada, onCerrar, onExpirada,
}: {
  tipo: TipoArcop;
  perfil: PerfilTitular;
  catalogo: CatalogoArcop | null;
  crear: (tipo: TipoArcop, descripcion: string) => Promise<DetalleArcop>;
  onCreada: (d: DetalleArcop) => void;
  onCerrar: () => void;
  onExpirada: (e: unknown) => boolean;
}) {
  const d = DERECHOS[tipo];
  const [texto, setTexto] = useState("");
  const [confirmado, setConfirmado] = useState(false);
  const [intentado, setIntentado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorCampo = intentado ? errorTexto(texto, DESCRIPCION_MIN, DESCRIPCION_MAX, "La descripción") : null;
  const esSupresion = tipo === "supresion";

  const plazo =
    tipo === "bloqueo" && catalogo?.plazo_bloqueo_dias_habiles
      ? `Te responderemos en ${catalogo.plazo_bloqueo_dias_habiles} días hábiles.`
      : catalogo?.plazo_respuesta_dias
        ? `Te responderemos en un máximo de ${catalogo.plazo_respuesta_dias} días corridos.`
        : "Te responderemos dentro del plazo legal.";

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setIntentado(true);
    if (errorTexto(texto, DESCRIPCION_MIN, DESCRIPCION_MAX) || (esSupresion && !confirmado) || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      onCreada(await crear(tipo, texto));
    } catch (err) {
      if (!onExpirada(err)) setError(mensajeError(err, "No pudimos enviar tu solicitud. Inténtalo de nuevo."));
      setEnviando(false);
    }
  }

  return (
    <form className={s.formulario} onSubmit={enviar} noValidate aria-labelledby="titulo-form-arcop">
      <div>
        <h3 id="titulo-form-arcop" className={s.formularioTitulo}>{d.accion}</h3>
        <p className={s.ayuda}>{d.descripcion} {plazo}</p>
      </div>

      <CampoTexto
        etiqueta="Cuéntanos tu solicitud"
        ayuda={d.guia}
        placeholder={`Ejemplo: ${d.ejemplo}`}
        valor={texto}
        onCambio={setTexto}
        max={DESCRIPCION_MAX}
        error={errorCampo}
      />

      {exportable(tipo) ? (
        <p className="callout" role="note">
          <Icon name="descargar" aria-hidden="true" />
          <span>Cuando se resuelva, podrás descargar tus datos aquí mismo en JSON (para traspasarlos a otro servicio) o CSV (para abrirlos en una planilla).</span>
        </p>
      ) : null}

      {esSupresion ? (
        <label className={s.confirmar}>
          <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} aria-describedby="efecto-supresion" />
          <span id="efecto-supresion">
            <strong>Entiendo que es definitivo.</strong> {EFECTO_SUPRESION[perfil]}
          </span>
        </label>
      ) : null}
      {esSupresion && intentado && !confirmado ? (
        <p className={s.error} role="alert">Marca la casilla para confirmar que entiendes que la eliminación es definitiva.</p>
      ) : null}

      {error ? <p className={s.error} role="alert">{error}</p> : null}

      <div className={s.acciones}>
        <button type="submit" className="btn btn-primary" disabled={enviando} aria-busy={enviando}>
          <Icon name="enviar" />
          {enviando ? "Enviando…" : "Enviar solicitud"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={enviando}>
          Elegir otra opción
        </button>
      </div>
      <p className={s.ayuda}>No incluyas contraseñas ni datos de otras personas.</p>
    </form>
  );
}

function SolicitudEnviada({ solicitud, onVer }: { solicitud: DetalleArcop; onVer: () => void }) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(solicitud.codigo_seguimiento);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }
  return (
    <div className={s.exito} role="status">
      <p className={s.exitoTitulo}>
        <Icon name="check" aria-hidden="true" />
        Recibimos tu solicitud de {DERECHOS[solicitud.tipo].nombre.toLowerCase()}
      </p>
      <p className={s.ayuda}>Guarda tu código de seguimiento. Sirve para consultar el estado aunque no ingreses.</p>
      <div className={s.codigo}>
        <span className={s.codigoValor} aria-label={`Código de seguimiento ${solicitud.codigo_seguimiento.split("").join(" ")}`}>
          {solicitud.codigo_seguimiento}
        </span>
        <button type="button" className="btn btn-sm" onClick={copiar}>
          <Icon name={copiado ? "check" : "copiar"} />
          {copiado ? "Copiado" : "Copiar código"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onVer}>
          Ver mi solicitud
          <Icon name="flecha" />
        </button>
      </div>
      <Plazo solicitud={solicitud} />
    </div>
  );
}

/* ================================================================== una solicitud */
type Api = ReturnType<typeof apiTitular>;

function ItemSolicitud({
  solicitud, abierta, alternar, api, onCambio, onExpirada,
}: {
  solicitud: SolicitudArcop;
  abierta: boolean;
  alternar: () => void;
  api: Api;
  onCambio: () => Promise<void>;
  onExpirada: (e: unknown) => boolean;
}) {
  const d = DERECHOS[solicitud.tipo];
  const idCuerpo = `solicitud-${solicitud.id_solicitud}`;
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (abierta) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [abierta]);

  return (
    <li ref={ref} className={s.item} data-atencion={solicitud.estado === "pendiente_informacion"}>
      <button type="button" className={s.itemBoton} aria-expanded={abierta} aria-controls={idCuerpo} onClick={alternar}>
        <span className={`${s.derechoIcono} ${solicitud.tipo === "supresion" ? s.derechoIconoAlerta : ""}`} aria-hidden="true">
          <Icon name={d.icono} />
        </span>
        <span className={s.itemTexto}>
          <span className={s.itemTitulo}>{d.accion}</span>
          <span className={s.itemMeta}>
            <span className={s.mono}>{solicitud.codigo_seguimiento}</span>
            <span>Enviada el {fechaChile(solicitud.fecha_creacion)}</span>
            <Plazo solicitud={solicitud} />
          </span>
        </span>
        <span className={s.itemLado}>
          <BadgeEstadoArcop estado={solicitud.estado} />
          <Icon name="flecha" className={s.chevron} aria-hidden="true" />
        </span>
      </button>
      {abierta ? (
        <div id={idCuerpo} className={s.cuerpo}>
          <DetalleTitular id={solicitud.id_solicitud} api={api} onCambio={onCambio} onExpirada={onExpirada} />
        </div>
      ) : null}
    </li>
  );
}

function DetalleTitular({
  id, api, onCambio, onExpirada,
}: { id: number; api: Api; onCambio: () => Promise<void>; onExpirada: (e: unknown) => boolean }) {
  const [d, setD] = useState<DetalleArcop | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setD(await api.detalle(id));
      setError(null);
    } catch (e) {
      if (!onExpirada(e)) setError(mensajeError(e, "No pudimos abrir la solicitud."));
    }
  }, [api, id, onExpirada]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function alActualizar(nuevo: DetalleArcop, texto: string) {
    setD(nuevo);
    setAviso(texto);
    await onCambio();
  }

  if (error) return <p className={s.error} role="alert">{error}</p>;
  if (!d) return <div className="skeleton" style={{ height: 96 }} role="status" aria-label="Cargando la solicitud" />;

  const acciones = accionesTitular(d);
  const pedido = [...d.historial].reverse().find((e) => e.estado_nuevo === "pendiente_informacion" && e.comentario);

  return (
    <>
      <Progreso estado={d.estado} />
      <div className={s.estado}>
        <p className={s.estadoFrase}>{ESTADOS[d.estado].titular}</p>
        <Plazo solicitud={d} />
      </div>

      {aviso ? <p className="callout" role="status"><Icon name="check" aria-hidden="true" /><span>{aviso}</span></p> : null}

      {acciones.aportar ? (
        <FormInformacion pedido={pedido?.comentario ?? null} enviar={(t) => api.aportar(d.id_solicitud, t)}
                         onEnviada={(n) => alActualizar(n, "Enviamos tu información. El responsable seguirá con tu solicitud.")}
                         onExpirada={onExpirada} />
      ) : null}

      {d.respuesta ? (
        <div className={s.bloque}>
          <p className={s.bloqueTitulo}>Respuesta del responsable</p>
          <blockquote className={`${s.cita} ${s.citaRespuesta}`}>{d.respuesta}</blockquote>
        </div>
      ) : null}

      {acciones.descargar ? <DescargaDatos id={d.id_solicitud} api={api} onExpirada={onExpirada} /> : null}

      <div className={s.bloque}>
        <p className={s.bloqueTitulo}>Lo que pediste</p>
        <blockquote className={s.cita}>{d.descripcion}</blockquote>
      </div>

      <Historial eventos={d.historial} paraTitular />

      {acciones.cancelar ? (
        <Cancelar cancelar={(m) => api.cancelar(d.id_solicitud, m)}
                  onCancelada={(n) => alActualizar(n, "Cancelaste la solicitud.")} onExpirada={onExpirada} />
      ) : null}
    </>
  );
}

function FormInformacion({
  pedido, enviar, onEnviada, onExpirada,
}: {
  pedido: string | null;
  enviar: (texto: string) => Promise<DetalleArcop>;
  onEnviada: (d: DetalleArcop) => void;
  onExpirada: (e: unknown) => boolean;
}) {
  const [texto, setTexto] = useState("");
  const [intentado, setIntentado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorCampo = intentado ? errorTexto(texto, DESCRIPCION_MIN, DESCRIPCION_MAX, "Tu respuesta") : null;

  async function mandar(e: FormEvent) {
    e.preventDefault();
    setIntentado(true);
    if (errorTexto(texto, DESCRIPCION_MIN, DESCRIPCION_MAX) || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      onEnviada(await enviar(texto));
    } catch (err) {
      if (!onExpirada(err)) setError(mensajeError(err));
      setEnviando(false);
    }
  }

  return (
    <form className={s.formulario} onSubmit={mandar} noValidate aria-label="Responder al responsable">
      {pedido ? (
        <div className={s.bloque}>
          <p className={s.bloqueTitulo}>El responsable te pidió</p>
          <blockquote className={`${s.cita} ${s.citaPedido}`}>{pedido}</blockquote>
        </div>
      ) : null}
      <CampoTexto etiqueta="Tu respuesta" valor={texto} onCambio={setTexto} max={DESCRIPCION_MAX} error={errorCampo} corto
                  ayuda="Al enviarla, tu solicitud vuelve a revisión." />
      {error ? <p className={s.error} role="alert">{error}</p> : null}
      <div className={s.acciones}>
        <button type="submit" className="btn btn-primary" disabled={enviando} aria-busy={enviando}>
          <Icon name="enviar" />
          {enviando ? "Enviando…" : "Enviar respuesta"}
        </button>
      </div>
    </form>
  );
}

function DescargaDatos({ id, api, onExpirada }: { id: number; api: Api; onExpirada: (e: unknown) => boolean }) {
  const [ocupado, setOcupado] = useState<FormatoExportacion | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  async function bajar(formato: FormatoExportacion) {
    setOcupado(formato);
    setMensaje(null);
    try {
      const { blob, nombre } = await api.descargar(id, formato);
      descargarBlob(blob, nombre);
      setMensaje(`Descargamos ${nombre}.`);
    } catch (e) {
      if (!onExpirada(e)) setMensaje(mensajeError(e, "No pudimos descargar tus datos."));
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className={s.descarga}>
      <p className={s.descargaTitulo}>
        <Icon name="descargar" aria-hidden="true" />
        Tus datos están listos para descargar
      </p>
      <p className={s.ayuda}>
        JSON es el formato para traspasar tus datos a otro servicio. CSV se abre en Excel u otra planilla.
      </p>
      <div className={s.acciones}>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => bajar("json")} disabled={ocupado !== null}
                aria-busy={ocupado === "json"}>
          <Icon name="descargar" />
          Descargar JSON
        </button>
        <button type="button" className="btn btn-sm" onClick={() => bajar("csv")} disabled={ocupado !== null}
                aria-busy={ocupado === "csv"}>
          <Icon name="tabla" />
          Descargar CSV
        </button>
      </div>
      <p className={s.ayuda} aria-live="polite">{mensaje ?? ""}</p>
    </div>
  );
}

function Cancelar({
  cancelar, onCancelada, onExpirada,
}: { cancelar: (motivo?: string) => Promise<DetalleArcop>; onCancelada: (d: DetalleArcop) => void; onExpirada: (e: unknown) => boolean }) {
  const [abierto, setAbierto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmar() {
    setOcupado(true);
    setError(null);
    try {
      onCancelada(await cancelar(motivo));
      setAbierto(false);
    } catch (e) {
      if (!onExpirada(e)) setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  if (!abierto) {
    return (
      <div>
        <button type="button" className="link-btn" onClick={() => setAbierto(true)}>Ya no la necesito: cancelar solicitud</button>
      </div>
    );
  }
  return (
    <div className={s.formulario} role="group" aria-label="Cancelar la solicitud">
      <p className={s.formularioTitulo}>¿Cancelar esta solicitud?</p>
      <p className={s.ayuda}>Se cerrará y no se atenderá. Si cambias de opinión, puedes enviar una nueva.</p>
      <CampoTexto etiqueta="Motivo" obligatorio={false} valor={motivo} onCambio={setMotivo} max={2000} corto />
      {error ? <p className={s.error} role="alert">{error}</p> : null}
      <div className={s.acciones}>
        <button type="button" className={`btn ${s.btnPeligro}`} onClick={confirmar} disabled={ocupado} aria-busy={ocupado}>
          Sí, cancelar solicitud
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => setAbierto(false)} disabled={ocupado}>
          No, mantenerla
        </button>
      </div>
    </div>
  );
}
