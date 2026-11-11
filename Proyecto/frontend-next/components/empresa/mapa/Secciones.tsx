"use client";

/**
 * Pestañas secundarias del mapa de datos:
 *   Riesgos       hallazgos priorizados y lo que falta completar.
 *   Sugerencias   propuestas desde la evaluación y plantillas por rubro.
 *   Historial     versiones del mapa, sus cambios y la restauración.
 * Y la pantalla de inicio cuando el mapa está vacío.
 */
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { fechaHoraChile } from "@/lib/fechas";
import {
  cargarVersion, cargarVersiones, ETIQUETA_ACCION, ETIQUETA_CAMPO, ETIQUETA_TIPO, mensajeError, plural, SEVERIDADES,
  type CambioVersion, type ListaVersiones, type PlantillaMapa, type SugerenciaMapa, type SugerenciasApi,
  type TipoElemento, type VersionMapa, type VistaMapa,
} from "@/lib/mapaDatos";
import s from "./mapa.module.css";

const ICONO_TIPO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };

/* ============================================================ riesgos */

export function Riesgos({
  vista,
  onVer,
  onCompletar,
  onConfirmarTodo,
  ocupado,
}: {
  vista: VistaMapa;
  onVer: (tipo: "elemento" | "flujo", id: number) => void;
  onCompletar: (tipo: "elemento" | "flujo", id: number) => void;
  onConfirmarTodo: () => void;
  ocupado: boolean;
}) {
  const porConfirmar = vista.completitud.pendientes.filter((p) => p.por_confirmar).length;
  const incompletos = vista.completitud.pendientes.filter((p) => p.faltan.length);
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <section className={s.seccion} aria-labelledby="titulo-hallazgos">
        <div className={s.seccionCabeza}>
          <h2 id="titulo-hallazgos">Riesgos detectados en tu mapa</h2>
          <div className={s.resumenSev}>
            {SEVERIDADES.map((sev) =>
              vista.conteo_hallazgos[sev] ? (
                <span key={sev} className={s.sev} data-sev={sev} style={{ "--sev": `var(--${sev === "Crítica" ? "critico" : sev === "Alta" ? "naranja" : sev === "Media" ? "medio" : "bajo"})` } as CSSProperties}>
                  {vista.conteo_hallazgos[sev]} {sev.toLowerCase()}{vista.conteo_hallazgos[sev] === 1 ? "" : "s"}
                </span>
              ) : null,
            )}
          </div>
        </div>
        <p className="card-sub">
          Se calculan solos a partir de lo que registraste: transferencias sin garantía, terceros sin contrato, datos
          sensibles o de menores, cifrado y responsables. Se actualizan con cada cambio.
        </p>
        {vista.hallazgos.length ? (
          <ul className={s.hallazgos}>
            {vista.hallazgos.map((h) => (
              <li key={h.codigo} className={s.hallazgo} data-sev={h.severidad}>
                <div className={s.hallazgoCabeza}>
                  <h3>{h.titulo}</h3>
                  <span className={s.sev} data-sev={h.severidad}>{h.severidad}</span>
                </div>
                <p>{h.detalle}</p>
                <p className={s.queHacer}><strong>Qué hacer:</strong> {h.recomendacion}</p>
                <p className={s.referencia}>Referencia: {h.referencia}</p>
                <div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => (h.flujos.length ? onVer("flujo", h.flujos[0]) : onVer("elemento", h.elementos[0]))}
                  >
                    <Icon name="mapa" />
                    Ver en el mapa
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="callout" role="status">
            <Icon name="check" />
            <span>No detectamos riesgos con la información registrada. Mantén el mapa al día cuando cambien tus sistemas o proveedores.</span>
          </p>
        )}
      </section>

      <section className={s.seccion} aria-labelledby="titulo-pendientes">
        <div className={s.seccionCabeza}>
          <h2 id="titulo-pendientes">Para completar el mapa</h2>
          {porConfirmar ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onConfirmarTodo} disabled={ocupado}>
              <Icon name="check" />
              Confirmar todo lo revisado ({porConfirmar})
            </button>
          ) : null}
        </div>
        <p className="card-sub">
          Completitud del mapa: <strong>{vista.completitud.porcentaje} %</strong>. Mientras más completo, más precisos son
          los riesgos y más fácil será armar el registro de actividades de tratamiento.
        </p>
        {incompletos.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Elementos y flujos con información por completar</caption>
              <thead>
                <tr>
                  <th scope="col">Elemento o flujo</th>
                  <th scope="col">Falta</th>
                  <th scope="col"><span className="sr-only">Acción</span></th>
                </tr>
              </thead>
              <tbody>
                {incompletos.map((p) => (
                  <tr key={`${p.tipo}-${p.id}`}>
                    <td>
                      <div className={s.celdaNombre}>
                        <button type="button" onClick={() => onVer(p.tipo, p.id)}>{p.nombre}</button>
                        <small>{p.tipo === "flujo" ? "Flujo" : "Elemento"}{p.por_confirmar ? " · por confirmar" : ""}</small>
                      </div>
                    </td>
                    <td>{p.faltan.join(", ")}</td>
                    <td>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onCompletar(p.tipo, p.id)} disabled={ocupado}>
                        Completar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="card-sub">Todos los elementos y flujos tienen su información clave.</p>
        )}
      </section>
    </div>
  );
}

/* ============================================================ sugerencias y plantillas */

export function Sugerencias({
  sugerencias,
  plantillas,
  cargando,
  error,
  onAceptar,
  onDescartar,
  onRestablecer,
  onAplicarPlantilla,
  ocupado,
}: {
  sugerencias: SugerenciasApi | null;
  plantillas: PlantillaMapa[] | null;
  cargando: boolean;
  error: string;
  onAceptar: (s: SugerenciaMapa, origenId: number | null) => void;
  onDescartar: (s: SugerenciaMapa) => void;
  onRestablecer: () => void;
  onAplicarPlantilla: (p: PlantillaMapa) => void;
  ocupado: boolean;
}) {
  if (cargando) return <div className="skeleton" style={{ height: 260 }} role="status" aria-label="Cargando sugerencias" />;
  if (error) return <div className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></div>;
  return (
    <div style={{ display: "grid", gap: 28 }}>
      <section className={s.seccion} aria-labelledby="titulo-sugerencias">
        <div className={s.seccionCabeza}>
          <h2 id="titulo-sugerencias">Sugerencias desde tu evaluación</h2>
          {sugerencias?.descartadas ? (
            <button type="button" className="link-btn" onClick={onRestablecer} disabled={ocupado}>
              Volver a mostrar {plural(sugerencias.descartadas, "sugerencia descartada", "sugerencias descartadas")}
            </button>
          ) : null}
        </div>
        <p className="card-sub">
          Según cómo declaraste usar la IA en tu evaluación más reciente, tu mapa debería incluir estos elementos y flujos.
          Lo que aceptes queda «por confirmar» para que lo revises.
        </p>
        {sugerencias?.sin_evaluacion ? (
          <p className="callout"><Icon name="info" /><span>Tu empresa aún no tiene una evaluación completada para sugerir flujos.</span></p>
        ) : sugerencias && sugerencias.sugerencias.length === 0 ? (
          <p className="callout"><Icon name="check" /><span>No hay sugerencias pendientes: tu mapa ya refleja lo declarado en la evaluación.</span></p>
        ) : (
          <div className={s.tarjetas}>
            {sugerencias?.sugerencias.map((sug) => (
              <TarjetaSugerencia key={sug.clave} sugerencia={sug} onAceptar={onAceptar} onDescartar={onDescartar} ocupado={ocupado} />
            ))}
          </div>
        )}
      </section>

      <section className={s.seccion} aria-labelledby="titulo-plantillas">
        <div className={s.seccionCabeza}>
          <h2 id="titulo-plantillas">Plantillas por rubro</h2>
        </div>
        <p className="card-sub">
          Agregan los sistemas, terceros y flujos típicos de un rubro (más lo común a toda empresa, como remuneraciones y
          previsión). Nunca reemplazan lo que ya tienes: solo suman lo que falta.
        </p>
        <div className={s.tarjetas}>
          {(plantillas ?? []).map((p) => (
            <TarjetaPlantilla key={p.codigo} plantilla={p} onAplicar={onAplicarPlantilla} ocupado={ocupado} />
          ))}
        </div>
      </section>
    </div>
  );
}

function TarjetaSugerencia({ sugerencia, onAceptar, onDescartar, ocupado }: {
  sugerencia: SugerenciaMapa;
  onAceptar: (s: SugerenciaMapa, origenId: number | null) => void;
  onDescartar: (s: SugerenciaMapa) => void;
  ocupado: boolean;
}) {
  const [origen, setOrigen] = useState<number | "">(sugerencia.usa_existente ?? "");
  const idSel = `origen-${sugerencia.clave}`;
  const conector = sugerencia.conector ? sugerencia.elementos.find((e) => e.clave === sugerencia.conector) : null;
  return (
    <article className={s.tarjeta} data-destacada="true">
      <div className={s.tarjetaCabeza}>
        <h3>{sugerencia.titulo}</h3>
        <Icon name="chispa" width={20} height={20} style={{ color: "var(--accent)", flex: "none" }} />
      </div>
      <p className={s.motivo}>
        <Icon name="diagnostico" />
        <span>{sugerencia.motivo}</span>
      </p>
      <p>{sugerencia.descripcion}</p>
      <ul className={s.propuesta} aria-label="Se agregará">
        {sugerencia.elementos.map((e) => (
          <li key={e.clave}>
            <Icon name={ICONO_TIPO[e.tipo]} />
            <span>
              <strong>{e.nombre}</strong> · {ETIQUETA_TIPO[e.tipo].toLowerCase()}
              {e.pais && e.pais !== "CL" ? ` (${e.pais})` : ""}
            </span>
          </li>
        ))}
        {sugerencia.flujos.map((f, i) => (
          <li key={`f${i}`}>
            <Icon name="flujo" />
            <span>Flujo: {f.origen.nombre} → {f.destino.nombre}</span>
          </li>
        ))}
      </ul>
      {sugerencia.conector && sugerencia.candidatos.length ? (
        <div className={s.campo}>
          <label htmlFor={idSel}>¿Desde qué sistema de tu mapa?</label>
          <select id={idSel} className={`select ${s.control}`} value={origen} onChange={(e) => setOrigen(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Crear «{conector?.nombre ?? "nuevo sistema"}»</option>
            {sugerencia.candidatos.map((c) => (
              <option key={c.id} value={c.id}>{c.nombre}</option>
            ))}
          </select>
        </div>
      ) : null}
      <div className={s.tarjetaPie}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDescartar(sugerencia)} disabled={ocupado}>
          Descartar
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => onAceptar(sugerencia, origen || null)} disabled={ocupado}>
          <Icon name="mas" />
          Agregar al mapa
        </button>
      </div>
    </article>
  );
}

function TarjetaPlantilla({ plantilla, onAplicar, ocupado }: {
  plantilla: PlantillaMapa;
  onAplicar: (p: PlantillaMapa) => void;
  ocupado: boolean;
}) {
  return (
    <article className={s.tarjeta} data-destacada={plantilla.recomendada || undefined}>
      <div className={s.tarjetaCabeza}>
        <h3>{plantilla.nombre}</h3>
        {plantilla.recomendada ? <span className={s.etiqueta} data-tono="ok">Recomendada para tu rubro</span> : null}
      </div>
      <p>{plantilla.descripcion}</p>
      <div className={s.cifrasPlantilla}>
        <span>{plural(plantilla.sistemas, "sistema", "sistemas")}</span>
        <span>{plural(plantilla.bases_datos, "base de datos", "bases de datos")}</span>
        <span>{plural(plantilla.terceros, "tercero", "terceros")}</span>
        <span>{plural(plantilla.flujos, "flujo", "flujos")}</span>
      </div>
      <details>
        <summary className="link-btn" style={{ cursor: "pointer" }}>Ver qué incluye</summary>
        <ul className={s.propuesta} style={{ marginTop: 8 }}>
          {plantilla.elementos.map((e) => (
            <li key={e.clave}>
              <Icon name={ICONO_TIPO[e.tipo]} />
              <span>{e.nombre}</span>
            </li>
          ))}
        </ul>
      </details>
      <div className={s.tarjetaPie}>
        <span />
        <button type="button" className={`btn btn-sm ${plantilla.recomendada ? "btn-primary" : "btn-ghost"}`} onClick={() => onAplicar(plantilla)} disabled={ocupado}>
          Usar esta plantilla
        </button>
      </div>
    </article>
  );
}

/* ============================================================ historial de versiones */

const ICONO_OP: Record<CambioVersion["operacion"], IconName> = { creado: "mas", editado: "editar", eliminado: "basura" };
const TEXTO_OP: Record<CambioVersion["operacion"], string> = { creado: "Se agregó", editado: "Se editó", eliminado: "Se eliminó" };

export function Historial({ versionActual, onRestaurar, ocupado }: {
  versionActual: number;
  onRestaurar: (numero: number) => void;
  ocupado: boolean;
}) {
  const [lista, setLista] = useState<ListaVersiones | null>(null);
  const [pagina, setPagina] = useState(1);
  const [elegida, setElegida] = useState<{ version: VersionMapa; es_actual: boolean; verificada: boolean } | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async (p: number) => {
    try {
      setError("");
      setLista(await cargarVersiones(p));
    } catch (e) {
      setError(mensajeError(e, "No pudimos cargar el historial. Inténtalo de nuevo."));
    }
  }, []);

  useEffect(() => {
    void cargar(pagina);
  }, [cargar, pagina, versionActual]);

  const abrir = async (numero: number) => {
    try {
      setElegida(await cargarVersion(numero));
    } catch (e) {
      setError(mensajeError(e, "No pudimos abrir esa versión."));
    }
  };

  if (error) return <div className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></div>;
  if (!lista) return <div className="skeleton" style={{ height: 260 }} role="status" aria-label="Cargando el historial" />;
  if (!lista.items.length) {
    return <p className="callout"><Icon name="info" /><span>El historial aparecerá con el primer cambio que hagas en el mapa.</span></p>;
  }

  return (
    <div className={s.zonaHistorial}>
      <section className="card" aria-labelledby="titulo-versiones" style={{ display: "grid", gap: 12 }}>
        <div>
          <h2 id="titulo-versiones" className="card-title">Versiones del mapa</h2>
          <p className="card-sub">Cada cambio crea una versión que no se puede alterar. {plural(lista.total, "versión", "versiones")} en total.</p>
        </div>
        <ol className={s.lineaTiempo}>
          {lista.items.map((v) => (
            <li key={v.numero}>
              <button type="button" className={s.version} aria-current={elegida?.version.numero === v.numero || undefined} onClick={() => abrir(v.numero)}>
                <span className={s.versionNum}>{v.numero}</span>
                <strong>
                  {ETIQUETA_ACCION[v.accion] ?? "Cambio"}
                  {v.numero === lista.version_actual ? " · actual" : ""}
                </strong>
                <small>{fechaHoraChile(v.fecha)} · {plural(v.elementos, "elemento", "elementos")}, {plural(v.flujos, "flujo", "flujos")}</small>
              </button>
            </li>
          ))}
        </ol>
        {lista.paginas > 1 ? (
          <div className={s.acciones} style={{ justifyContent: "space-between" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPagina((p) => Math.max(1, p - 1))} disabled={pagina <= 1}>
              <Icon name="flechaIzq" />
              Más recientes
            </button>
            <span className="card-sub">Página {lista.pagina} de {lista.paginas}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPagina((p) => Math.min(lista.paginas, p + 1))} disabled={pagina >= lista.paginas}>
              Más antiguas
              <Icon name="flecha" />
            </button>
          </div>
        ) : null}
      </section>

      <section className="card" aria-live="polite" style={{ display: "grid", gap: 16, alignContent: "start" }}>
        {!elegida ? (
          <p className="card-sub">Elige una versión para ver qué cambió y, si lo necesitas, volver a ella.</p>
        ) : (
          <>
            <div className={s.seccionCabeza}>
              <div>
                <h2 className="card-title">Versión {elegida.version.numero}</h2>
                <p className="card-sub">{fechaHoraChile(elegida.version.fecha)} · {elegida.version.resumen}</p>
              </div>
              {!elegida.es_actual ? (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onRestaurar(elegida.version.numero)} disabled={ocupado}>
                  <Icon name="historial" />
                  Volver a esta versión
                </button>
              ) : (
                <span className={s.etiqueta} data-tono="ok">Versión actual</span>
              )}
            </div>
            <ul className={s.cambios}>
              {(elegida.version.cambios ?? []).map((c, i) => (
                <li key={i} className={s.cambio} data-op={c.operacion}>
                  <Icon name={ICONO_OP[c.operacion]} />
                  <span>
                    {TEXTO_OP[c.operacion]} {c.entidad === "flujo" ? "el flujo" : c.tipo ? `${ETIQUETA_TIPO[c.tipo].toLowerCase()}` : "el elemento"}{" "}
                    <strong>«{c.nombre}»</strong>
                    {c.campos.length ? ` (${c.campos.map((x) => ETIQUETA_CAMPO[x] ?? x).join(", ")})` : ""}
                  </span>
                </li>
              ))}
              {elegida.version.cambios_total > (elegida.version.cambios?.length ?? 0) ? (
                <li className={s.ayuda}>Y otros cambios menores.</li>
              ) : null}
            </ul>
            <div style={{ display: "grid", gap: 4 }}>
              <span className="field-label">Huella de la versión</span>
              <span className={s.huella}>{elegida.version.huella}</span>
              <span className={s.etiqueta} data-tono={elegida.verificada ? "ok" : "sensible"} style={{ justifySelf: "start" }}>
                {elegida.verificada ? "Íntegra: el contenido coincide con su huella" : "La huella no coincide: avisa a Therion Labs"}
              </span>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

/* ============================================================ inicio (mapa vacío) */

export function InicioMapa({
  plantillas,
  sugerencias,
  onPlantilla,
  onVerSugerencias,
  onAgregar,
  ocupado,
}: {
  plantillas: PlantillaMapa[] | null;
  sugerencias: SugerenciasApi | null;
  onPlantilla: (p: PlantillaMapa) => void;
  onVerSugerencias: () => void;
  onAgregar: () => void;
  ocupado: boolean;
}) {
  const recomendada = plantillas?.find((p) => p.recomendada) ?? plantillas?.[0];
  const nSug = sugerencias?.sugerencias.length ?? 0;
  return (
    <div className={s.inicio}>
      <section className={s.inicioHero} aria-labelledby="titulo-inicio">
        <div>
          <h2 id="titulo-inicio">Arma el mapa de los datos personales de tu empresa</h2>
          <p>
            Registra en qué sistemas y bases de datos tratas datos personales, de quiénes son, dónde están alojados y con
            quién los compartes. Será la base de tu registro de actividades de tratamiento.
          </p>
          <ol className={s.pasosInicio}>
            <li>Parte con una plantilla de tu rubro o con lo que declaraste en tu evaluación.</li>
            <li>Revisa, ajusta y completa cada sistema, tercero y flujo.</li>
            <li>Atiende los riesgos detectados y descarga o envía el informe.</li>
          </ol>
        </div>
        <svg className={s.ilustracion} viewBox="0 0 320 200" aria-hidden="true">
          <defs>
            <linearGradient id="ilu-g" x1="0" x2="1">
              <stop offset="0" stopColor="#14d89e" />
              <stop offset="1" stopColor="#8fa3ff" />
            </linearGradient>
          </defs>
          <path d="M80 52 C 108 52, 100 100, 128 100" stroke="#6f8a80" strokeWidth="2" fill="none" />
          <path d="M80 148 C 108 148, 100 100, 128 100" stroke="#ff5c7a" strokeWidth="2.4" fill="none" />
          <path d="M192 100 C 220 100, 216 52, 244 52" stroke="#f2b53f" strokeWidth="2.4" strokeDasharray="6 4" fill="none" />
          <path d="M192 100 C 220 100, 216 148, 244 148" stroke="#6f8a80" strokeWidth="2" fill="none" />
          <rect x="8" y="32" width="72" height="40" rx="9" fill="#0d231b" stroke="#14d89e" />
          <rect x="8" y="128" width="72" height="40" rx="9" fill="#0d231b" stroke="#14d89e" />
          <rect x="128" y="80" width="64" height="40" rx="9" fill="#131a34" stroke="#8fa3ff" />
          <rect x="244" y="32" width="68" height="40" rx="9" fill="#28180c" stroke="#f58a4b" />
          <rect x="244" y="128" width="68" height="40" rx="9" fill="#28180c" stroke="#f58a4b" />
          <rect x="16" y="44" width="40" height="5" rx="2.5" fill="#14d89e" opacity="0.7" />
          <rect x="16" y="140" width="40" height="5" rx="2.5" fill="#14d89e" opacity="0.7" />
          <rect x="136" y="92" width="36" height="5" rx="2.5" fill="#8fa3ff" opacity="0.7" />
          <rect x="252" y="44" width="40" height="5" rx="2.5" fill="#f58a4b" opacity="0.7" />
          <rect x="252" y="140" width="40" height="5" rx="2.5" fill="#f58a4b" opacity="0.7" />
          <circle cx="160" cy="16" r="6" fill="url(#ilu-g)" opacity="0.7" />
        </svg>
      </section>

      <div className={s.opcionesInicio}>
        <article className={s.opcion} data-destacada="true">
          <span className={s.opcionIcono}><Icon name="lista" /></span>
          <h3>Usar la plantilla de tu rubro</h3>
          <p>
            {recomendada
              ? `${recomendada.nombre}: ${plural(recomendada.sistemas + recomendada.bases_datos + recomendada.terceros, "elemento", "elementos")} y ${plural(recomendada.flujos, "flujo", "flujos")} típicos, listos para revisar.`
              : "Los sistemas, terceros y flujos típicos de tu rubro, listos para revisar."}
          </p>
          <button type="button" className="btn btn-primary" onClick={() => recomendada && onPlantilla(recomendada)} disabled={!recomendada || ocupado}>
            Usar plantilla
          </button>
        </article>
        <article className={s.opcion}>
          <span className={s.opcionIcono}><Icon name="chispa" /></span>
          <h3>Partir desde tu evaluación</h3>
          <p>
            {sugerencias?.sin_evaluacion
              ? "Cuando tengas una evaluación completada, te sugeriremos los flujos según cómo usas la IA."
              : nSug
                ? `Tenemos ${plural(nSug, "sugerencia", "sugerencias")} según cómo declaraste usar la IA (por ejemplo, el flujo hacia tu proveedor de modelos de lenguaje).`
                : "Revisaremos tus respuestas para sugerirte flujos según cómo usas la IA."}
          </p>
          <button type="button" className="btn btn-ghost" onClick={onVerSugerencias} disabled={ocupado}>
            Ver sugerencias
          </button>
        </article>
        <article className={s.opcion}>
          <span className={s.opcionIcono}><Icon name="mas" /></span>
          <h3>Empezar desde cero</h3>
          <p>Agrega tu primer sistema, base de datos o tercero y construye el mapa a tu medida.</p>
          <button type="button" className="btn btn-ghost" onClick={onAgregar} disabled={ocupado}>
            Agregar el primer elemento
          </button>
        </article>
      </div>
    </div>
  );
}
