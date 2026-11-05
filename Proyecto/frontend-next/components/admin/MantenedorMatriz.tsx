"use client";

/**
 * HU-24 · Mantenedor de la matriz normativa (panel interno de Therion Labs).
 *
 * Arriba, la versión vigente frente al borrador en edición: es la pregunta que el admin se
 * hace al entrar ("¿qué está usando hoy el cuestionario y qué cambié yo?"). Debajo, una
 * pestaña por cada parte de la matriz (controles, brechas, rutas, filtro inicial), el árbol
 * de aplicabilidad como una grilla control × pregunta de filtro con un simulador, y el
 * historial de versiones.
 *
 * Nada se edita en vivo: se trabaja sobre un borrador y se publica con etiqueta y nota. Las
 * evaluaciones cerradas siguen con la versión con que se respondieron; las en curso pasan a
 * la nueva. Cada cambio queda en el audit log (lo registra el backend).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import { comoErrorAdmin, type ErrorAdmin } from "@/lib/admin/api";
import {
  aplicables,
  apiMatriz,
  CAMPOS,
  controlesPorDimension,
  CRITICIDADES,
  datosDelFormulario,
  descripcion,
  erroresFormulario,
  estaActivo,
  estadosDe,
  ETIQUETA_ESTADO_FILA,
  etiqueta,
  fechaCorta,
  filtrosOrdenados,
  frasesCambios,
  huellaCorta,
  mensajeErrorMatriz,
  NIVELES,
  NOMBRE_ENTIDAD,
  valoresIniciales,
  type Borrador,
  type Contenido,
  type Control,
  type DetalleVersion,
  type Diferencias,
  type Entidad,
  type EstadoMatriz,
  type FichaVersion,
  type Problema,
  type Validacion,
} from "@/lib/admin/matriz";
import { BarraAdmin } from "./BarraAdmin";
import { RubrosMatriz } from "./RubrosMatriz";
import { notaVisible } from "@/lib/admin/rubros";
import a from "./admin.module.css";
import s from "./matriz.module.css";

type Pestana = Entidad | "arbol" | "historial" | "rubros";
type FiltroLista = "activos" | "cambios" | "retirados" | "todos";

const PESTANAS: [Pestana, string][] = [
  ["controles", "Controles"],
  ["brechas", "Brechas"],
  ["rutas", "Rutas formativas"],
  ["preguntas_filtro", "Filtro inicial"],
  ["arbol", "Árbol de aplicabilidad"],
  ["historial", "Historial de versiones"],
  // Correcciones 05-11: los rubros se gestionan aquí (no pasan por el borrador)
  ["rubros", "Rubros"],
];

type ErrorVista = ErrorAdmin & { problemas?: Problema[]; usado_por?: string[] };

export function MantenedorMatriz() {
  const router = useRouter();
  const [estado, setEstado] = useState<EstadoMatriz | null>(null);
  const [borrador, setBorrador] = useState<Borrador | null>(null);
  const [vigente, setVigente] = useState<DetalleVersion | null>(null);
  const [pestana, setPestana] = useState<Pestana>("controles");
  const [error, setError] = useState<ErrorVista | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [editando, setEditando] = useState<{ entidad: Entidad; item: Record<string, unknown> | null } | null>(null);
  const [publicando, setPublicando] = useState(false);
  // Correcciones 05-11: "Actualizar" de la barra también recarga la pestaña Rubros
  const [recarga, setRecarga] = useState(0);

  const manejarError = useCallback(
    (e: unknown): ErrorVista => {
      const err = comoErrorAdmin(e) as ErrorVista;
      const info = (e as { info?: Record<string, unknown> })?.info;
      if (info && Array.isArray(info.problemas)) err.problemas = info.problemas as Problema[];
      if (info && Array.isArray(info.usado_por)) err.usado_por = info.usado_por as string[];
      if (err.codigo === "SESION_EXPIRADA") router.replace("/admin/login?motivo=sesion");
      return err;
    },
    [router],
  );

  const cargar = useCallback(async () => {
    try {
      const est = await apiMatriz.estado();
      setEstado(est);
      if (est.borrador) {
        setBorrador(await apiMatriz.borrador());
      } else {
        setBorrador(null);
      }
      setVigente(await apiMatriz.version(est.vigente.id));
    } catch (e) {
      setError(manejarError(e));
    }
  }, [manejarError]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  /** Ejecuta una acción sobre el borrador y recarga; un conflicto de revisión recarga y avisa. */
  const accion = useCallback(
    async (fn: () => Promise<unknown>, exito?: string): Promise<boolean> => {
      setError(null);
      setOcupado(true);
      try {
        await fn();
        if (exito) setAviso(exito);
        await cargar();
        return true;
      } catch (e) {
        const err = manejarError(e);
        const conflicto = mensajeErrorMatriz(err.codigo);
        if (conflicto) {
          await cargar();
          setError({ ...err, mensaje: conflicto });
        } else {
          setError(err);
        }
        return false;
      } finally {
        setOcupado(false);
      }
    },
    [cargar, manejarError],
  );

  const contenido: Contenido | null = borrador?.contenido ?? vigente?.contenido ?? null;
  const editable = Boolean(borrador);
  const revision = borrador?.revision ?? 0;

  return (
    <div className={a.pagina}>
      <BarraAdmin
        onActualizar={async () => {
          setRecarga((n) => n + 1);
          await cargar();
        }}
      />

      <main id="contenido" className={a.contenido}>
        <div>
          <h1 className="page-title">Matriz normativa</h1>
          <p className="page-sub">
            Actualiza controles, brechas, rutas y reglas cuando cambie la normativa. Los cambios se preparan en un
            borrador y llegan al cuestionario solo al publicar una versión nueva.
          </p>
        </div>

        {aviso ? (
          <p className="callout" role="status">
            {aviso}{" "}
            <button type="button" className="link-btn" onClick={() => setAviso(null)}>Cerrar</button>
          </p>
        ) : null}
        {error ? <AvisoError error={error} cerrar={() => setError(null)} /> : null}

        {estado ? (
          <FranjaVersiones
            estado={estado}
            ocupado={ocupado}
            crear={() => accion(() => apiMatriz.crearBorrador(), "Borrador creado. Edita y publica cuando esté listo.")}
            descartar={() => {
              if (!window.confirm("¿Descartar el borrador? Se pierden los cambios sin publicar (queda registrado en el audit log).")) return;
              void accion(() => apiMatriz.descartar(revision), "Borrador descartado. El cuestionario sigue con la versión vigente.");
            }}
            publicar={() => setPublicando(true)}
          />
        ) : (
          <p className={s.vacio}>Cargando la matriz…</p>
        )}

        <div className={s.pestanas} role="tablist" aria-label="Partes de la matriz"
             onKeyDown={(e) => {
               // Patrón de pestañas WAI-ARIA: flechas, Inicio y Fin mueven y activan
               const i = PESTANAS.findIndex(([k]) => k === pestana);
               const destino = e.key === "ArrowRight" ? (i + 1) % PESTANAS.length
                 : e.key === "ArrowLeft" ? (i - 1 + PESTANAS.length) % PESTANAS.length
                   : e.key === "Home" ? 0 : e.key === "End" ? PESTANAS.length - 1 : -1;
               if (destino < 0) return;
               e.preventDefault();
               const clave = PESTANAS[destino][0];
               setPestana(clave);
               document.getElementById(`tab-${clave}`)?.focus();
             }}>
          {PESTANAS.map(([clave, texto]) => {
            const conCambios =
              clave !== "arbol" && clave !== "historial" && clave !== "rubros" &&
              Boolean(borrador?.conteo_cambios?.[clave as Entidad]);
            return (
              <button key={clave} id={`tab-${clave}`} role="tab" type="button" className={s.pestana}
                      aria-selected={pestana === clave} aria-controls={`panel-${clave}`}
                      tabIndex={pestana === clave ? 0 : -1}
                      onClick={() => setPestana(clave)}>
                {texto}
                {conCambios ? <span className={s.puntoCambio} aria-label="con cambios sin publicar" role="img" /> : null}
              </button>
            );
          })}
        </div>

        <section id={`panel-${pestana}`} role="tabpanel" aria-labelledby={`tab-${pestana}`}>
          {pestana === "rubros" ? (
            <RubrosMatriz recarga={recarga} onAviso={setAviso} onError={(e) => setError(e)} />
          ) : !contenido ? null : pestana === "arbol" ? (
            <ArbolAplicabilidad
              contenido={contenido}
              editable={editable}
              ocupado={ocupado}
              cambiar={(c, siempre, filtros) =>
                accion(() => apiMatriz.aplicabilidad(c.id, revision, siempre, filtros))
              }
            />
          ) : pestana === "historial" ? (
            <Historial
              vigenteId={estado?.vigente.id ?? 0}
              hayBorrador={editable}
              ocupado={ocupado}
              volverA={(v) => {
                if (!window.confirm(`¿Crear un borrador con el contenido de la versión ${v.etiqueta}? Lo agregado después quedará retirado en el borrador.`)) return;
                void accion(() => apiMatriz.crearBorrador(v.id), `Borrador creado desde la versión ${v.etiqueta}.`).then(
                  (ok) => ok && setPestana("controles"),
                );
              }}
              onError={(e) => setError(manejarError(e))}
            />
          ) : (
            <ListaEntidad
              entidad={pestana}
              contenido={contenido}
              diferencias={borrador?.diferencias ?? null}
              editable={editable}
              ocupado={ocupado}
              editar={(item) => setEditando({ entidad: pestana, item })}
              crear={() => setEditando({ entidad: pestana, item: null })}
              retirar={(item) => {
                const nuevo = Number(item.id) < 0;
                const txt = nuevo
                  ? `¿Quitar ${etiqueta(pestana, item)} del borrador?`
                  : `¿Retirar ${etiqueta(pestana, item)}? Dejará de aplicarse en la versión nueva; las evaluaciones anteriores lo conservan.`;
                if (!window.confirm(txt)) return;
                void accion(() => apiMatriz.retirar(pestana, Number(item.id), revision),
                  nuevo ? `${etiqueta(pestana, item)} se quitó del borrador.` : `${etiqueta(pestana, item)} quedó retirado en el borrador.`);
              }}
              restaurar={(item) =>
                void accion(() => apiMatriz.restaurar(pestana, Number(item.id), revision),
                  `${etiqueta(pestana, item)} vuelve a estar activo en el borrador.`)
              }
            />
          )}
        </section>
      </main>

      {editando && contenido ? (
        <EditorElemento
          entidad={editando.entidad}
          item={editando.item}
          contenido={contenido}
          soloLectura={!editable}
          cerrar={() => setEditando(null)}
          guardar={async (datos) => {
            const { entidad, item } = editando;
            const ok = await accion(
              () => (item ? apiMatriz.actualizar(entidad, Number(item.id), revision, datos) : apiMatriz.crear(entidad, revision, datos)),
              item ? `${etiqueta(entidad, item)}: cambios guardados en el borrador.` : `${NOMBRE_ENTIDAD[entidad].singular[0].toUpperCase()}${NOMBRE_ENTIDAD[entidad].singular.slice(1)} agregado al borrador.`,
            );
            if (ok) setEditando(null);
          }}
        />
      ) : null}

      {publicando && borrador && estado ? (
        <DialogoPublicar
          borrador={borrador}
          sugerida={estado.etiqueta_sugerida}
          cerrar={() => setPublicando(false)}
          publicar={async (etiquetaV, nota) => {
            const ok = await accion(() => apiMatriz.publicar(revision, etiquetaV, nota),
              `Versión ${etiquetaV} publicada. El cuestionario ya la usa en las evaluaciones nuevas y en curso.`);
            if (ok) setPublicando(false);
          }}
        />
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ avisos */
function AvisoError({ error, cerrar }: { error: ErrorVista; cerrar: () => void }) {
  return (
    <div className={s.alerta} role="alert">
      <strong>{error.mensaje}</strong>
      {error.usado_por?.length ? <p className={s.lectura}>Lo usan: {error.usado_por.join(", ")}.</p> : null}
      {error.problemas?.length ? <ListaProblemas problemas={error.problemas} /> : null}
      <button type="button" className="link-btn" onClick={cerrar}>Cerrar</button>
    </div>
  );
}

function ListaProblemas({ problemas }: { problemas: Problema[] }) {
  const orden = [...problemas].sort((x, y) => (x.nivel === y.nivel ? 0 : x.nivel === "error" ? -1 : 1));
  return (
    <ul className={s.problemas}>
      {orden.map((p, i) => (
        <li key={`${p.codigo}-${p.id}-${i}`} className={`${s.problema} ${p.nivel === "error" ? s.problemaError : s.problemaAviso}`}>
          <strong>{p.nivel === "error" ? "Error: " : "Advertencia: "}</strong>
          {p.mensaje}
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ franja de versiones */
function FranjaVersiones({
  estado, ocupado, crear, descartar, publicar,
}: {
  estado: EstadoMatriz; ocupado: boolean; crear: () => void; descartar: () => void; publicar: () => void;
}) {
  const v = estado.vigente;
  const b = estado.borrador;
  return (
    <section className={s.franja} aria-label="Versión vigente y borrador">
      <div className={s.vigente}>
        <span className={s.vigenteRotulo}>Versión vigente</span>
        <span className={s.etiquetaVersion}>{v.etiqueta}</span>
        <span className={s.huella} title="Huella SHA-256 del contenido (primeros 8 caracteres)">Huella {huellaCorta(v.huella)}</span>
        <dl className={s.datos}>
          <dt>Publicada</dt>
          <dd>{fechaCorta(v.fecha_publicacion)}{v.publicado_por?.email ? ` por ${v.publicado_por.email}` : ""}</dd>
          <dt>Contenido</dt>
          <dd>
            {v.resumen.controles.activos} controles, {v.resumen.brechas.activos} brechas, {v.resumen.rutas.activos} rutas,{" "}
            {v.resumen.preguntas_filtro.activos} preguntas de filtro
          </dd>
          <dt>Evaluaciones</dt>
          <dd>{v.evaluaciones === 1 ? "1 evaluación cerrada la usa" : `${v.evaluaciones} evaluaciones cerradas la usan`}</dd>
        </dl>
        {notaVisible(v.nota_cambio) ? <p className={s.nota}>{v.nota_cambio}</p> : null}
      </div>

      {b ? (
        <div className={`${s.borrador} ${s.borradorActivo}`}>
          <h2 className={s.borradorTitulo}>Borrador en edición</h2>
          <p className={s.lectura}>
            Creado el {fechaCorta(b.fecha_creacion)}{b.creado_por?.email ? ` por ${b.creado_por.email}` : ""}. Nadie más lo
            ve hasta que lo publiques.
          </p>
          {b.cambios ? (
            <ul className={s.cambios} aria-label="Cambios frente a la versión vigente">
              {frasesCambios(b.conteo_cambios).map((f) => <li key={f} className={s.cambio}>{f}</li>)}
            </ul>
          ) : (
            <p className={s.lectura}>Todavía es igual a la versión {v.etiqueta}.</p>
          )}
          <p className={s.salud}>
            {b.errores ? <span className={s.saludError}>{b.errores} {b.errores === 1 ? "error impide" : "errores impiden"} publicar</span>
              : <span className={s.saludOk}>Sin errores</span>}
            {b.advertencias ? <span className={s.saludAviso}>{b.advertencias} {b.advertencias === 1 ? "advertencia" : "advertencias"}</span> : null}
          </p>
          {b.base_desactualizada ? (
            <p className={s.saludError}>Se publicó otra versión después de crear este borrador: descártalo y crea uno nuevo.</p>
          ) : null}
          <div className={s.acciones}>
            <button className="btn btn-primary" type="button" onClick={publicar} disabled={ocupado || !b.cambios}>
              Revisar y publicar
            </button>
            <button className="btn btn-ghost" type="button" onClick={descartar} disabled={ocupado}>Descartar borrador</button>
          </div>
        </div>
      ) : (
        <div className={s.borrador}>
          <h2 className={s.borradorTitulo}>Sin borrador</h2>
          <p className={s.lectura}>
            Estás viendo la versión vigente en modo lectura. Para cambiarla, crea un borrador: el cuestionario seguirá con la
            versión {v.etiqueta} hasta que publiques.
          </p>
          <div className={s.acciones}>
            <button className="btn btn-primary" type="button" onClick={crear} disabled={ocupado}>
              <Icon name="mas" /> Crear borrador
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ listas */
function ListaEntidad({
  entidad, contenido, diferencias, editable, ocupado, editar, crear, retirar, restaurar,
}: {
  entidad: Entidad; contenido: Contenido; diferencias: Diferencias | null; editable: boolean; ocupado: boolean;
  editar: (item: Record<string, unknown>) => void; crear: () => void;
  retirar: (item: Record<string, unknown>) => void; restaurar: (item: Record<string, unknown>) => void;
}) {
  const [buscar, setBuscar] = useState("");
  const [filtro, setFiltro] = useState<FiltroLista>("activos");
  const idBuscar = useId();
  const estados = useMemo(() => estadosDe(diferencias, entidad), [diferencias, entidad]);
  const items = contenido[entidad] as unknown as Record<string, unknown>[];
  const dominios = new Map(contenido.dominios.map((d) => [d.id, d.nombre_dominio ?? `Dimensión ${d.id}`]));
  const brechas = new Map(contenido.brechas.map((b) => [b.id, b.codigo_brecha ?? `#${b.id}`]));
  const rutas = new Map(contenido.rutas.map((r) => [r.id, r.nombre ?? `#${r.id}`]));

  const visibles = items
    .filter((x) => {
      const activo = estaActivo(entidad, x);
      if (filtro === "activos") return activo;
      if (filtro === "retirados") return !activo;
      if (filtro === "cambios") return estados.has(Number(x.id));
      return true;
    })
    .filter((x) => {
      const q = buscar.trim().toLowerCase();
      return !q || `${etiqueta(entidad, x)} ${descripcion(entidad, x)}`.toLowerCase().includes(q);
    })
    .sort((x, y) =>
      entidad === "preguntas_filtro"
        ? Number(x.orden ?? 0) - Number(y.orden ?? 0)
        : etiqueta(entidad, x).localeCompare(etiqueta(entidad, y), "es"),
    );

  const nombre = NOMBRE_ENTIDAD[entidad];
  return (
    <div className="card">
      <div className={s.herramientas}>
        <div className={a.filtros}>
          <label htmlFor={idBuscar} className="sr-only">Buscar en {nombre.plural.toLowerCase()}</label>
          <input id={idBuscar} className={s.buscar} type="search" placeholder="Buscar por código o texto"
                 value={buscar} onChange={(e) => setBuscar(e.target.value)} />
          <div className="chip-group" role="group" aria-label="Mostrar">
            {([["activos", "Activos"], ["cambios", "Con cambios"], ["retirados", "Retirados"], ["todos", "Todos"]] as [FiltroLista, string][])
              .filter(([k]) => editable || k !== "cambios")
              .map(([k, t]) => (
                <button key={k} type="button" className="chip" aria-pressed={filtro === k} onClick={() => setFiltro(k)}>{t}</button>
              ))}
          </div>
        </div>
        {editable ? (
          <button className="btn btn-primary btn-sm" type="button" onClick={crear} disabled={ocupado}>
            <Icon name="mas" /> Agregar {nombre.singular}
          </button>
        ) : null}
      </div>

      {!visibles.length ? (
        <p className={s.vacio}>
          {buscar ? "Nada coincide con la búsqueda." : filtro === "cambios" ? "Sin cambios en esta parte del borrador." : "No hay elementos en esta vista."}
        </p>
      ) : (
        <div className="table-wrap" style={{ marginTop: "var(--sp-4)" }}>
          <table className="table">
            <caption className="sr-only">{nombre.plural} ({visibles.length})</caption>
            <thead>
              <tr>
                <th scope="col">{entidad === "rutas" ? "Ruta" : "Código"}</th>
                <th scope="col">{entidad === "controles" ? "Pregunta" : entidad === "brechas" ? "Comportamiento" : entidad === "rutas" ? "Objetivo" : "Pregunta"}</th>
                {entidad === "controles" ? <><th scope="col">Dimensión</th><th scope="col">Criticidad</th><th scope="col">Brecha</th></> : null}
                {entidad === "brechas" ? <><th scope="col">Criticidad</th><th scope="col">Ruta</th></> : null}
                {entidad === "rutas" ? <><th scope="col">Dimensión</th><th scope="col">Nivel</th><th scope="col" className="num">Horas</th></> : null}
                {entidad === "preguntas_filtro" ? <><th scope="col" className="num">Orden</th><th scope="col">Tipo</th></> : null}
                <th scope="col">Estado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((x) => {
                const activo = estaActivo(entidad, x);
                const est = estados.get(Number(x.id));
                const marca = est ?? (activo ? null : "retirado");
                return (
                  <tr key={String(x.id)} className={activo ? undefined : s.filaRetirada}>
                    <td className={entidad === "rutas" ? undefined : "code"}>{etiqueta(entidad, x)}</td>
                    <td><span className={s.texto}>{descripcion(entidad, x) || "—"}</span></td>
                    {entidad === "controles" ? (
                      <>
                        <td>{dominios.get(Number(x.dominio_id)) ?? "—"}</td>
                        <td>{String(x.criticidad ?? "—")}</td>
                        <td className="code">{x.brecha_id != null ? brechas.get(Number(x.brecha_id)) : "—"}</td>
                      </>
                    ) : null}
                    {entidad === "brechas" ? (
                      <>
                        <td>{String(x.criticidad ?? "—")}</td>
                        <td>{x.ruta_formativa_id != null ? rutas.get(Number(x.ruta_formativa_id)) : "—"}</td>
                      </>
                    ) : null}
                    {entidad === "rutas" ? (
                      <>
                        <td>{x.dominio_id != null ? dominios.get(Number(x.dominio_id)) : "—"}</td>
                        <td>{String(x.nivel ?? "—")}</td>
                        <td className="num">{x.horas != null ? String(x.horas) : "—"}</td>
                      </>
                    ) : null}
                    {entidad === "preguntas_filtro" ? (
                      <>
                        <td className="num">{String(x.orden ?? "—")}</td>
                        <td>{x.es_compuerta ? "Compuerta" : "Suma controles"}</td>
                      </>
                    ) : null}
                    <td>
                      {marca ? <span className={`badge tone-${ETIQUETA_ESTADO_FILA[marca].tono}`}>{ETIQUETA_ESTADO_FILA[marca].texto}</span>
                        : <span className={s.lectura}>Sin cambios</span>}
                    </td>
                    <td>
                      <div className={a.acciones}>
                        {editable && activo ? (
                          <>
                            <button type="button" className="link-btn" onClick={() => editar(x)} disabled={ocupado}
                                    aria-label={`Editar ${etiqueta(entidad, x)}`}>Editar</button>
                            <button type="button" className="link-btn" onClick={() => retirar(x)} disabled={ocupado}
                                    aria-label={`${Number(x.id) < 0 ? "Quitar" : "Retirar"} ${etiqueta(entidad, x)}`}>
                              {Number(x.id) < 0 ? "Quitar" : "Retirar"}
                            </button>
                          </>
                        ) : null}
                        {editable && !activo ? (
                          <button type="button" className="link-btn" onClick={() => restaurar(x)} disabled={ocupado}
                                  aria-label={`Restaurar ${etiqueta(entidad, x)}`}>Restaurar</button>
                        ) : null}
                        {!editable ? (
                          <button type="button" className="link-btn" onClick={() => editar(x)}
                                  aria-label={`Ver ${etiqueta(entidad, x)}`}>Ver</button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!editable ? (
        <p className={s.lectura} style={{ marginTop: "var(--sp-4)" }}>Modo lectura: crea un borrador para editar.</p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ editor (diálogo) */
function EditorElemento({
  entidad, item, contenido, soloLectura, cerrar, guardar,
}: {
  entidad: Entidad; item: Record<string, unknown> | null; contenido: Contenido; soloLectura: boolean;
  cerrar: () => void; guardar: (datos: Record<string, unknown>) => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titulo = useId();
  const [valores, setValores] = useState(() => valoresIniciales(entidad, item));
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  // Sin borrador el diálogo es de solo lectura (botón "Ver")
  const esNuevo = item === null || Number(item.id) < 0;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (soloLectura) return cerrar();
    const errs = erroresFormulario(entidad, valores, esNuevo);
    setErrores(errs);
    if (Object.keys(errs).length) return;
    const datos = datosDelFormulario(entidad, valores, item);
    if (!Object.keys(datos).length) return cerrar();
    setEnviando(true);
    await guardar(datos);
    setEnviando(false);
  }

  const dominios = contenido.dominios;
  const brechas = contenido.brechas.filter((b) => b.activo || b.id === Number(item?.brecha_id));
  const rutas = contenido.rutas.filter((r) => r.activo || r.id === Number(item?.ruta_formativa_id));
  const nombre = NOMBRE_ENTIDAD[entidad].singular;

  return (
    <dialog ref={ref} className={s.dialogo} aria-labelledby={titulo} onClose={cerrar} onCancel={cerrar}>
      <form className={s.dialogoForm} onSubmit={enviar} noValidate>
        <div className={s.dialogoCabeza}>
          <div>
            <h2 id={titulo} className={s.dialogoTitulo}>
              {soloLectura ? etiqueta(entidad, item ?? {}) : item ? `Editar ${etiqueta(entidad, item)}` : `Nuevo ${nombre}`}
            </h2>
            <p className={s.lectura}>
              {soloLectura ? "Versión vigente (solo lectura)." : "Los cambios quedan en el borrador hasta que publiques."}
            </p>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={cerrar} aria-label="Cerrar">
            <Icon name="cerrar" />
          </button>
        </div>
        <div className={s.dialogoCuerpo}>
          <div className={s.campos}>
            {CAMPOS[entidad].map((c) => {
              const id = `campo-${entidad}-${c.clave}`;
              const bloqueado = soloLectura || (Boolean(c.esCodigo) && !esNuevo);
              const v = valores[c.clave];
              const set = (nv: string | boolean) => setValores((o) => ({ ...o, [c.clave]: nv }));
              const err = errores[c.clave];
              const ancho = c.tipo === "textoLargo" || c.tipo === "si_no";
              const desc = [c.ayuda ? `${id}-ayuda` : "", err ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
              if (c.tipo === "si_no") {
                return (
                  <div key={c.clave} className={`${s.campo} ${s.campoAncho}`}>
                    <label className={s.casilla}>
                      <input type="checkbox" checked={v === true} disabled={bloqueado} onChange={(e) => set(e.target.checked)} />
                      {c.etiqueta}
                    </label>
                  </div>
                );
              }
              const comun = {
                id, className: s.control, disabled: bloqueado, "aria-invalid": err ? true : undefined,
                "aria-describedby": desc, "aria-required": c.requerido || undefined,
              } as const;
              let control: ReactNode;
              if (c.tipo === "textoLargo") {
                control = <textarea {...comun} value={String(v)} maxLength={c.max} onChange={(e) => set(e.target.value)} />;
              } else if (["criticidad", "nivel", "dominio", "brecha", "ruta"].includes(c.tipo)) {
                const opciones: [string, string][] =
                  c.tipo === "criticidad" ? CRITICIDADES.map((x): [string, string] => [x, x])
                    : c.tipo === "nivel" ? NIVELES.map((x): [string, string] => [x, x])
                      : c.tipo === "dominio" ? dominios.map((d): [string, string] => [String(d.id), d.nombre_dominio ?? `Dimensión ${d.id}`])
                        : c.tipo === "brecha" ? brechas.map((b): [string, string] => [String(b.id), `${b.codigo_brecha ?? b.id}: ${(b.comportamiento_detectado ?? "").slice(0, 60)}`])
                          : rutas.map((r): [string, string] => [String(r.id), r.nombre ?? `Ruta ${r.id}`]);
                // Una criticidad o nivel sembrado en minúsculas se muestra igual
                const actual = String(v);
                const conActual = actual && !opciones.some(([k]) => k === actual) ? [[actual, actual] as [string, string], ...opciones] : opciones;
                control = (
                  <select {...comun} value={actual} onChange={(e) => set(e.target.value)}>
                    <option value="">{c.requerido ? "Elige una opción" : "Sin asignar"}</option>
                    {conActual.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                  </select>
                );
              } else {
                control = (
                  <input {...comun} type="text" inputMode={c.tipo === "numero" ? "numeric" : undefined}
                         value={String(v)} maxLength={c.max} onChange={(e) => set(e.target.value)} />
                );
              }
              return (
                <div key={c.clave} className={`${s.campo} ${ancho ? s.campoAncho : ""}`}>
                  <label htmlFor={id}>{c.etiqueta}{c.requerido && !bloqueado ? <span aria-hidden="true"> *</span> : null}</label>
                  {control}
                  {c.esCodigo && !esNuevo ? (
                    <span className={s.ayuda} id={`${id}-ayuda`}>
                      El código de un elemento publicado no cambia: identifica sus respuestas en evaluaciones anteriores.
                    </span>
                  ) : c.ayuda ? <span className={s.ayuda} id={`${id}-ayuda`}>{c.ayuda}</span> : null}
                  {err ? <span className={s.errorCampo} id={`${id}-error`}>{err}</span> : null}
                </div>
              );
            })}
          </div>
          {entidad === "controles" && !soloLectura ? (
            <p className={s.ayuda}>Las reglas de cuándo se pregunta este control se editan en la pestaña Árbol de aplicabilidad.</p>
          ) : null}
        </div>
        <div className={s.dialogoPie}>
          <button type="button" className="btn btn-ghost" onClick={cerrar}>{soloLectura ? "Cerrar" : "Cancelar"}</button>
          {!soloLectura ? (
            <button type="submit" className="btn btn-primary" disabled={enviando}>
              {enviando ? "Guardando…" : item ? "Guardar cambios" : `Agregar ${nombre}`}
            </button>
          ) : null}
        </div>
      </form>
    </dialog>
  );
}

/* ------------------------------------------------------------------ árbol */
function ArbolAplicabilidad({
  contenido, editable, ocupado, cambiar,
}: {
  contenido: Contenido; editable: boolean; ocupado: boolean;
  cambiar: (c: Control, siempre: boolean, filtros: number[]) => Promise<boolean>;
}) {
  const filtros = filtrosOrdenados(contenido);
  const [respuestas, setRespuestas] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(filtros.map((f) => [f.codigo, f.es_compuerta])),
  );
  const grupos = controlesPorDimension(contenido);
  const total = grupos.reduce((n, g) => n + g.controles.length, 0);
  const aplican = aplicables(contenido, respuestas);
  const compuertas = filtros.filter((f) => f.es_compuerta);

  return (
    <div style={{ display: "grid", gap: "var(--sp-6)" }}>
      <section className="card" aria-labelledby="titulo-simulador">
        <div className={s.simulador}>
          <div>
            <h2 id="titulo-simulador" className="card-title">Prueba el filtro inicial</h2>
            <p className="card-sub">
              Marca lo que respondería una organización y mira cuántos controles le preguntaría el cuestionario
              {editable ? " con este borrador" : " con la versión vigente"}.
            </p>
          </div>
          <div className="chip-group" role="group" aria-label="Respuestas del filtro (marcado = SÍ)">
            {filtros.map((f) => (
              <button key={f.id} type="button" className="chip" aria-pressed={Boolean(respuestas[f.codigo])}
                      title={f.pregunta ?? ""}
                      onClick={() => setRespuestas((r) => ({ ...r, [f.codigo]: !r[f.codigo] }))}>
                {f.codigo} {respuestas[f.codigo] ? "Sí" : "No"}
              </button>
            ))}
          </div>
          <div className={s.simuladorResultado} aria-live="polite">
            <span className={s.simuladorCifra}>{aplican.length}</span>
            <span>de {total} controles se preguntarían</span>
            {compuertas.some((c) => !respuestas[c.codigo]) ? (
              <span className={s.saludAviso}>Una compuerta en NO deja el cuestionario vacío.</span>
            ) : null}
          </div>
          <div className={s.medidor} aria-hidden="true">
            <span style={{ width: `${total ? (aplican.length / total) * 100 : 0}%` }} />
          </div>
        </div>
      </section>

      <section aria-labelledby="titulo-reglas">
        <h2 id="titulo-reglas" className="card-title">Cuándo se pregunta cada control</h2>
        <p className="card-sub" style={{ marginBottom: "var(--sp-4)" }}>
          “Siempre” aplica a toda organización que pase las compuertas
          {compuertas.length ? ` (${compuertas.map((c) => c.codigo).join(", ")})` : ""}. Cada columna de filtro suma el control
          cuando la respuesta es SÍ. {editable ? "Haz clic en una celda para cambiar la regla." : "Crea un borrador para editar las reglas."}
        </p>
        <div className={s.rejilla}>
          <table>
            <caption className="sr-only">Reglas de aplicabilidad por control y pregunta de filtro</caption>
            <thead>
              <tr>
                <th scope="col">Control</th>
                <th scope="col">Siempre</th>
                {filtros.map((f) => (
                  <th key={f.id} scope="col" title={f.pregunta ?? ""}>
                    {f.codigo}
                    {f.es_compuerta ? <span className={s.compuerta}>compuerta</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grupos.map((g) => (
                <GrupoArbol key={g.dominio.id} nombre={g.dominio.nombre_dominio ?? `Dimensión ${g.dominio.id}`}
                            controles={g.controles} filtros={filtros} editable={editable} ocupado={ocupado} cambiar={cambiar} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function GrupoArbol({
  nombre, controles, filtros, editable, ocupado, cambiar,
}: {
  nombre: string; controles: Control[]; filtros: ReturnType<typeof filtrosOrdenados>; editable: boolean; ocupado: boolean;
  cambiar: (c: Control, siempre: boolean, filtros: number[]) => Promise<boolean>;
}) {
  return (
    <>
      <tr className={s.grupo}>
        <th scope="rowgroup" colSpan={filtros.length + 2}>{nombre} ({controles.length} controles)</th>
      </tr>
      {controles.map((c) => {
        const nunca = !c.aplica_siempre && c.filtros.length === 0;
        return (
          <tr key={c.id} className={nunca ? s.nunca : undefined}>
            <th scope="row">
              <span className={s.colCodigo}>{c.codigo_control}{nunca ? " (nunca se pregunta)" : ""}</span>
              <span className={s.colPregunta} title={c.pregunta_evaluacion ?? ""}>{c.pregunta_evaluacion}</span>
            </th>
            <td className={s.celda}>
              <Marca activa={c.aplica_siempre} editable={editable} ocupado={ocupado}
                     etiqueta={`${c.codigo_control} aplica siempre`}
                     alternar={() => cambiar(c, !c.aplica_siempre, c.filtros)} />
            </td>
            {filtros.map((f) => {
              const activa = c.filtros.includes(f.id);
              return (
                <td key={f.id} className={s.celda}>
                  <Marca activa={activa} editable={editable} ocupado={ocupado}
                         etiqueta={`${c.codigo_control} se suma si responden SÍ a ${f.codigo}`}
                         alternar={() => cambiar(c, c.aplica_siempre, activa ? c.filtros.filter((x) => x !== f.id) : [...c.filtros, f.id])} />
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}

function Marca({ activa, editable, ocupado, etiqueta: texto, alternar }: {
  activa: boolean; editable: boolean; ocupado: boolean; etiqueta: string; alternar: () => void;
}) {
  if (!editable) {
    return activa ? <Icon name="check" title={texto} width={16} height={16} /> : <span className="sr-only">No</span>;
  }
  return (
    <button type="button" className={s.marca} aria-pressed={activa} aria-label={texto} disabled={ocupado} onClick={alternar}>
      {activa ? <Icon name="check" /> : null}
    </button>
  );
}

/* ------------------------------------------------------------------ historial */
function Historial({
  vigenteId, hayBorrador, ocupado, volverA, onError,
}: {
  vigenteId: number; hayBorrador: boolean; ocupado: boolean;
  volverA: (v: FichaVersion) => void; onError: (e: unknown) => void;
}) {
  const [versiones, setVersiones] = useState<FichaVersion[] | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<Record<number, DetalleVersion>>({});
  // El padre pasa una función nueva en cada render: se guarda en una ref para no recargar en bucle
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    apiMatriz.versiones().then((r) => setVersiones(r.items)).catch((e) => onErrorRef.current(e));
  }, [vigenteId]);

  async function alternar(id: number) {
    if (abierta === id) return setAbierta(null);
    setAbierta(id);
    if (!detalle[id]) {
      try {
        const d = await apiMatriz.version(id);
        setDetalle((x) => ({ ...x, [id]: d }));
      } catch (e) {
        onError(e);
      }
    }
  }

  if (!versiones) return <p className={s.vacio}>Cargando historial…</p>;
  return (
    <div className="card">
      <p className="card-sub" style={{ marginBottom: "var(--sp-4)" }}>
        Cada versión publicada queda guardada completa y no cambia. Las evaluaciones cerradas siguen usando la versión con que
        se respondieron.
      </p>
      <ol className={s.lineaTiempo}>
        {versiones.map((v) => {
          const d = detalle[v.id];
          return (
            <li key={v.id} className={`${s.hito} ${v.id === vigenteId ? s.hitoVigente : ""}`}>
              <div className={s.hitoEje} aria-hidden="true"><span className={s.hitoPunto} /><span className={s.hitoLinea} /></div>
              <div className={s.hitoCuerpo}>
                <div className={s.hitoTitulo}>
                  <span className={s.hitoEtiqueta}>{v.etiqueta}</span>
                  <span className={`badge tone-${v.estado === "publicada" ? "ok" : "info"}`}>
                    {v.estado === "publicada" ? "Vigente" : "Reemplazada"}
                  </span>
                  <span className={s.huella}>{v.version_texto}</span>
                </div>
                <p className={s.lectura}>
                  Publicada el {fechaCorta(v.fecha_publicacion)}{v.publicado_por?.email ? ` por ${v.publicado_por.email}` : ""}.{" "}
                  {v.evaluaciones === 1 ? "La usa 1 evaluación cerrada." : `La usan ${v.evaluaciones} evaluaciones cerradas.`}
                </p>
                {notaVisible(v.nota_cambio) ? <p className={s.nota}>{v.nota_cambio}</p> : null}
                <div className={a.acciones}>
                  <button type="button" className="link-btn" aria-expanded={abierta === v.id} onClick={() => void alternar(v.id)}>
                    {abierta === v.id ? "Ocultar cambios" : "Ver qué cambió"}
                  </button>
                  {v.id !== vigenteId && !hayBorrador ? (
                    <button type="button" className="link-btn" disabled={ocupado} onClick={() => volverA(v)}>
                      Crear borrador desde esta versión
                    </button>
                  ) : null}
                </div>
                {abierta === v.id ? (
                  d ? <ResumenDiferencias dif={d.diferencias} anterior={d.anterior?.etiqueta ?? null} />
                    : <p className={s.lectura}>Cargando…</p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function ResumenDiferencias({ dif, anterior }: { dif: Diferencias | null; anterior: string | null }) {
  if (!dif) return <p className={s.lectura}>Es la primera versión registrada.</p>;
  const lineas: string[] = [];
  for (const e of ["controles", "brechas", "rutas", "preguntas_filtro"] as Entidad[]) {
    const g = dif[e];
    if (!g) continue;
    g.nuevos.forEach((x) => lineas.push(`Nuevo: ${x.etiqueta}`));
    g.modificados.forEach((x) => lineas.push(`Modificado: ${x.etiqueta} (${x.campos.join(", ")})`));
    g.retirados.forEach((x) => lineas.push(`Retirado: ${x.etiqueta}`));
    g.restaurados.forEach((x) => lineas.push(`Restaurado: ${x.etiqueta}`));
  }
  return (
    <div>
      <p className={s.lectura}>{dif.total} cambios frente a la versión {anterior}:</p>
      <ul className={s.difLista}>{lineas.slice(0, 60).map((l) => <li key={l}>{l}</li>)}</ul>
      {lineas.length > 60 ? <p className={s.lectura}>Y {lineas.length - 60} más.</p> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ publicar */
function DialogoPublicar({
  borrador, sugerida, cerrar, publicar,
}: {
  borrador: Borrador; sugerida: string; cerrar: () => void; publicar: (etiqueta: string, nota: string) => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titulo = useId();
  const [val, setVal] = useState<Validacion | null>(null);
  const [etiquetaV, setEtiqueta] = useState(sugerida);
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    apiMatriz.validacion().then(setVal).catch((e) => setFalla(comoErrorAdmin(e).mensaje));
    return () => d?.close();
  }, []);

  const etiquetaOk = /^[0-9A-Za-z][0-9A-Za-z._-]{0,29}$/.test(etiquetaV.trim());
  const notaOk = nota.trim().length >= 10;
  const puede = Boolean(val?.puede_publicar) && etiquetaOk && notaOk && !enviando;

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!puede) return;
    setEnviando(true);
    await publicar(etiquetaV.trim(), nota.trim());
    setEnviando(false);
  }

  return (
    <dialog ref={ref} className={s.dialogo} aria-labelledby={titulo} onClose={cerrar} onCancel={cerrar}>
      <form className={s.dialogoForm} onSubmit={enviar} noValidate>
        <div className={s.dialogoCabeza}>
          <div>
            <h2 id={titulo} className={s.dialogoTitulo}>Publicar versión nueva</h2>
            <p className={s.lectura}>Revisa los cambios antes de que lleguen al cuestionario.</p>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={cerrar} aria-label="Cerrar"><Icon name="cerrar" /></button>
        </div>
        <div className={s.dialogoCuerpo}>
          {falla ? <div className={s.alerta} role="alert"><strong>{falla}</strong></div> : null}
          {!val ? <p className={s.lectura}>Revisando el borrador…</p> : (
            <>
              <div>
                <h3 className="card-title">Qué cambia</h3>
                <ul className={s.cambios} style={{ marginTop: "var(--sp-2)" }}>
                  {frasesCambios(borrador.conteo_cambios).map((f) => <li key={f} className={s.cambio}>{f}</li>)}
                </ul>
              </div>
              {val.problemas.length ? (
                <div>
                  <h3 className="card-title">
                    {val.errores ? `Corrige ${val.errores === 1 ? "1 error" : `${val.errores} errores`} para publicar` : "Advertencias (puedes publicar igual)"}
                  </h3>
                  <ListaProblemas problemas={val.problemas} />
                </div>
              ) : <p className={s.saludOk}>El borrador no tiene errores ni advertencias.</p>}
              <div className={s.campos}>
                <div className={s.campo}>
                  <label htmlFor="pub-etiqueta">Etiqueta de la versión</label>
                  <input id="pub-etiqueta" className={s.control} value={etiquetaV} maxLength={30}
                         aria-invalid={!etiquetaOk || undefined} aria-describedby="pub-etiqueta-ayuda"
                         onChange={(e) => setEtiqueta(e.target.value)} />
                  <span className={s.ayuda} id="pub-etiqueta-ayuda">Se imprime en los informes. Letras, números, punto o guion.</span>
                </div>
                <div className={`${s.campo} ${s.campoAncho}`}>
                  <label htmlFor="pub-nota">Nota del cambio normativo</label>
                  <textarea id="pub-nota" className={s.control} value={nota} maxLength={1000}
                            aria-invalid={(nota.length > 0 && !notaOk) || undefined} aria-describedby="pub-nota-ayuda"
                            placeholder="Ejemplo: Ajuste por la circular N.º 3 de la Agencia de Protección de Datos"
                            onChange={(e) => setNota(e.target.value)} />
                  <span className={s.ayuda} id="pub-nota-ayuda">Mínimo 10 caracteres. Queda en el historial y en el audit log.</span>
                </div>
              </div>
              <p className={s.lectura}>
                Al publicar, las evaluaciones nuevas y las que están en curso usan esta versión. Las evaluaciones cerradas
                conservan la versión con que se respondieron.
              </p>
            </>
          )}
        </div>
        <div className={s.dialogoPie}>
          <button type="button" className="btn btn-ghost" onClick={cerrar}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={!puede}>
            {enviando ? "Publicando…" : `Publicar versión ${etiquetaV.trim() || ""}`.trim()}
          </button>
        </div>
      </form>
    </dialog>
  );
}
