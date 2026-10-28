"use client";

/**
 * HU-17 · Cerrar brechas con evidencia (vista de remediación del usuario definitivo).
 *
 *   C1 Carga de archivos PDF, DOCX o TXT por control con brecha.
 *   C2 El análisis local (texto, NER y términos del control) lo hace el backend; aquí se
 *      muestran los términos encontrados.
 *   C3 Cuando la evidencia mejora el control, el puntaje global y el radar se recalculan:
 *      la vista consulta el resultado y recarga el panel.
 *
 * Es el único lugar donde cambia el puntaje de una evaluación migrada. Los controles cuya
 * formación ya está hecha (HU-26) van primero: es el paso que les falta.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { RadarMadurez } from "@/components/charts/RadarMadurez";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeSeveridad } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { esSinServicio, hrefModulo } from "@/lib/formacion";
import { SEVERIDAD_TONO } from "@/lib/severidad";
import { formatoPuntaje } from "@/lib/madurez";
import {
  ACCEPT,
  cargarRemediacion,
  consultarEvidencia,
  deltaTexto,
  esperaConsulta,
  ETIQUETA_ESTADO,
  estadosDeclarables,
  faseEvidencia,
  mensajeRemediacion,
  resultadoTexto,
  subirEvidencia,
  TONO_ESTADO,
  validarArchivo,
} from "@/lib/remediacion";
import type { ControlRemediacionApi, EvidenciaRemediacionApi, RemediacionApi } from "@/lib/types";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; datos: RemediacionApi }
  | { tipo: "sin-servicio" }
  | { tipo: "error"; mensaje: string };

export function VistaRemediacion() {
  const { evaluacionId, modo, recargar: recargarPanel, href, estado: panel } = usePanel();
  const params = useSearchParams();
  const enfocar = Number(params.get("control")) || null;
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [soloFormados, setSoloFormados] = useState(false);
  const [aviso, setAviso] = useState("");

  const cargar = useCallback(async () => {
    if (evaluacionId == null) return;
    try {
      setEstado({ tipo: "listo", datos: await cargarRemediacion(evaluacionId) });
    } catch (e) {
      setEstado(esSinServicio(e) && modo !== "cliente" ? { tipo: "sin-servicio" } : { tipo: "error", mensaje: mensajeRemediacion(e) });
    }
  }, [evaluacionId, modo]);

  useEffect(() => {
    if (modo === "detectando") return;
    if (modo !== "cliente") {
      setEstado({ tipo: "sin-servicio" });
      return;
    }
    void cargar();
  }, [cargar, modo]);

  const datos = estado.tipo === "listo" ? estado.datos : null;
  const visibles = useMemo(
    () => (datos ? datos.controles.filter((c) => !soloFormados || c.formacion_completada) : []),
    [datos, soloFormados],
  );
  const formados = datos?.controles.filter((c) => c.formacion_completada).length ?? 0;

  const alMejorar = (e: EvidenciaRemediacionApi) => {
    setAviso(resultadoTexto(e));
    recargarPanel(); // radar, barras y brechas con el puntaje nuevo
    void cargar();
  };

  return (
    <>
      <PageHeader
        eyebrow="Re-evaluación con evidencia"
        titulo="Cerrar brechas"
        subtitulo="Sube la evidencia de que un control ya se aplica. La IA la analiza y, si el control mejora, tu puntaje se actualiza sin repetir el autodiagnóstico."
      />
      <p className="aviso-accion" role="status" aria-live="polite">
        {aviso}
      </p>

      {estado.tipo === "cargando" ? (
        <div role="status" className="grid">
          <span className="sr-only">Cargando los controles con brecha…</span>
          <div className="skeleton col-12" style={{ height: 96 }} />
          <div className="skeleton col-12" style={{ height: 320 }} />
        </div>
      ) : null}
      {estado.tipo === "sin-servicio" ? (
        <div className="state" role="status">
          <Icon name="candado" width={32} height={32} style={{ color: "var(--medio)" }} />
          <h2>Cerrar brechas es parte del servicio contratado</h2>
          <p>
            Con la plataforma, tu empresa sube evidencia de cada control y su puntaje se actualiza sin repetir el
            autodiagnóstico.
          </p>
          {modo === "encuestado" ? (
            <Link href={href("/panel/contratar")} className="btn btn-primary">Ver cómo contratar</Link>
          ) : (
            <Link href="/ingresar" className="btn btn-primary">Ingresar con mi empresa</Link>
          )}
        </div>
      ) : null}
      {estado.tipo === "error" ? (
        <div className="state" role="alert">
          <Icon name="alerta" width={32} height={32} style={{ color: "var(--alto)" }} />
          <h2>No pudimos cargar los controles</h2>
          <p>{estado.mensaje}</p>
          <button type="button" className="btn btn-primary" onClick={() => void cargar()}>
            <Icon name="refrescar" />
            Reintentar
          </button>
        </div>
      ) : null}

      {datos ? (
        <>
          <MadurezEnVivo datos={datos} dominios={panel.tipo === "listo" ? panel.panel.dominios : []} />

          <div className="remed-filtro">
            <p className="card-sub">
              {datos.controles.length} {datos.controles.length === 1 ? "control con brecha" : "controles con brecha"} ·{" "}
              {formados} con la formación hecha · PDF, Word o texto de hasta {datos.max_mb} MB
            </p>
            <label className="check">
              <input type="checkbox" checked={soloFormados} onChange={(e) => setSoloFormados(e.target.checked)} />
              <span>Solo los que ya tienen la formación hecha</span>
            </label>
          </div>

          {datos.controles.length === 0 ? (
            <div className="state" role="status">
              <Icon name="check" width={32} height={32} style={{ color: "var(--accent)" }} />
              <h2>No quedan brechas abiertas</h2>
              <p>Todos los controles de esta evaluación están cumplidos o no aplican.</p>
            </div>
          ) : visibles.length === 0 ? (
            <p className="card-sub">Ningún control tiene la formación hecha todavía. Desmarca el filtro para verlos todos.</p>
          ) : (
            <ul className="remed-lista">
              {visibles.map((c) => (
                <ControlRemediacion
                  key={c.respuesta_id}
                  control={c}
                  maxMb={datos.max_mb}
                  abierto={c.respuesta_id === enfocar}
                  evaluacionId={datos.evaluacion_id}
                  onMejora={alMejorar}
                  onAviso={setAviso}
                />
              ))}
            </ul>
          )}
        </>
      ) : null}
    </>
  );
}

/**
 * HU-17 C3 · Madurez en vivo: el radar y el puntaje general se redibujan apenas una evidencia
 * mejora un control (la vista recarga el panel al recibir el resultado), con lo que subió desde
 * la primera remediación y cada mejora en orden.
 */
function MadurezEnVivo({ datos, dominios }: { datos: RemediacionApi; dominios: import("@/lib/types").DominioVista[] }) {
  const inicial = datos.puntaje_inicial ?? datos.puntaje_general;
  const delta = deltaTexto(inicial, datos.puntaje_general);
  const subio = datos.puntaje_general > inicial;
  const [destello, setDestello] = useState(false);
  const previo = useRef(datos.puntaje_general);
  useEffect(() => {
    if (datos.puntaje_general !== previo.current) {
      previo.current = datos.puntaje_general;
      setDestello(true);
      const t = setTimeout(() => setDestello(false), 1600);
      return () => clearTimeout(t);
    }
  }, [datos.puntaje_general]);

  return (
    <section className="remed-madurez" aria-labelledby="madurez-titulo">
      <div className="card remed-puntaje-card" data-destello={destello || undefined}>
        <h2 className="card-title" id="madurez-titulo">Tu madurez ahora</h2>
        <p className="remed-cifra" aria-live="polite">
          <strong className="remed-puntaje">{formatoPuntaje(datos.puntaje_general)}</strong>
          <span className="remed-de"> / 100</span>
          {subio ? <span className="badge tone-ok remed-delta">{delta}</span> : null}
        </p>
        <p className="card-sub">
          {subio
            ? `Subió desde ${formatoPuntaje(inicial)} con ${datos.controles_mejorados ?? 0} ${
                (datos.controles_mejorados ?? 0) === 1 ? "control mejorado" : "controles mejorados"
              } por evidencia, sin repetir el autodiagnóstico.`
            : "Cada evidencia que la IA valide actualiza este puntaje y el radar al instante."}
        </p>
        {datos.evolucion?.length ? (
          <ol className="remed-evolucion" aria-label="Mejoras del puntaje por evidencia">
            {datos.evolucion.map((m, i) => (
              <li key={i}>
                <span className="remed-evolucion-paso">
                  {formatoPuntaje(m.antes)} → <strong>{formatoPuntaje(m.despues)}</strong>
                </span>
                <span className="remed-evolucion-delta">{deltaTexto(m.antes, m.despues)}</span>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
      <div className="card remed-radar">
        {dominios.length ? (
          <RadarMadurez dominios={dominios} />
        ) : (
          <p className="card-sub">El radar aparece cuando el panel termina de cargar.</p>
        )}
      </div>
    </section>
  );
}

function ControlRemediacion({
  control: c,
  maxMb,
  abierto: abiertoInicial,
  evaluacionId,
  onMejora,
  onAviso,
}: {
  control: ControlRemediacionApi;
  maxMb: number;
  abierto: boolean;
  evaluacionId: number;
  onMejora: (e: EvidenciaRemediacionApi) => void;
  onAviso: (t: string) => void;
}) {
  const id = useId();
  const declarables = estadosDeclarables(c.estado);
  const [abierto, setAbierto] = useState(abiertoInicial);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [declarado, setDeclarado] = useState(declarables[0]);
  const [justificacion, setJustificacion] = useState("");
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null);
  const [errorEnvio, setErrorEnvio] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [evidencia, setEvidencia] = useState<EvidenciaRemediacionApi | null>(c.ultima_evidencia);
  const item = useRef<HTMLLIElement>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (abiertoInicial) item.current?.scrollIntoView({ block: "center" });
  }, [abiertoInicial]);

  // Mientras se analiza, consulta el resultado con espera creciente
  useEffect(() => {
    if (!evidencia?.en_proceso) return;
    let intento = 0;
    let vigente = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const espera = esperaConsulta(intento++);
      if (espera == null || !vigente) return;
      timer = setTimeout(async () => {
        try {
          const e = await consultarEvidencia(evidencia.id_evidencia);
          if (!vigente) return;
          if (!e.en_proceso) {
            setEvidencia(e);
            if (e.mejoro) onMejora(e);
            else onAviso(resultadoTexto(e));
            return;
          }
        } catch {
          /* se reintenta en el siguiente ciclo */
        }
        void tick();
      }, espera);
    };
    void tick();
    return () => {
      vigente = false;
      clearTimeout(timer);
    };
  }, [evidencia?.id_evidencia, evidencia?.en_proceso]); // eslint-disable-line react-hooks/exhaustive-deps

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const err = validarArchivo(archivo, maxMb);
    setErrorArchivo(err);
    if (err) {
      inputArchivo.current?.focus();
      return;
    }
    setEnviando(true);
    setErrorEnvio("");
    try {
      const ev = await subirEvidencia(c.respuesta_id, archivo as File, declarado, justificacion);
      setEvidencia(ev);
      setArchivo(null);
      setJustificacion("");
      if (inputArchivo.current) inputArchivo.current.value = "";
      onAviso(`Recibimos ${ev.nombre_archivo}. La estamos analizando.`);
    } catch (er) {
      setErrorEnvio(mensajeRemediacion(er));
    } finally {
      setEnviando(false);
    }
  };

  const fase = evidencia ? faseEvidencia(evidencia) : null;
  const ocupado = fase === "analizando";

  return (
    <li ref={item} className={`card remed-item sev-${SEVERIDAD_TONO[c.severidad]}`}>
      <div className="remed-cabeza">
        <div className="remed-id">
          <span className="code">{c.control_codigo ?? c.codigo_brecha}</span>
          <BadgeSeveridad severidad={c.severidad} />
          <span className={`badge tone-${TONO_ESTADO[c.estado]}`}>{ETIQUETA_ESTADO[c.estado]}</span>
          {c.formacion_completada ? (
            <span className="remed-formado">
              <Icon name="check" />
              Formación hecha
            </span>
          ) : null}
        </div>
        <h3 className="remed-titulo">{c.obligacion ?? c.pregunta ?? "Control sin descripción"}</h3>
        {c.dominio ? <p className="card-sub">{c.dominio}</p> : null}
      </div>

      {c.evidencia_esperada ? (
        <p className="remed-espera">
          <Icon name="documento" />
          <span>
            <strong>Evidencia que sirve:</strong> {c.evidencia_esperada}
          </span>
        </p>
      ) : null}
      {!c.formacion_completada && c.ruta ? (
        <p className="card-sub">
          ¿Falta preparar al equipo? El módulo <Link href={hrefModulo(c.ruta.id, evaluacionId)}>{c.ruta.nombre}</Link> cubre
          este control.
        </p>
      ) : null}

      {evidencia ? <ResultadoEvidencia evidencia={evidencia} /> : null}
      {c.historial?.length ? (
        <details className="remed-historial">
          <summary>
            {c.historial.length} {c.historial.length === 1 ? "intento anterior" : "intentos anteriores"}
          </summary>
          <ul>
            {c.historial.map((h) => (
              <li key={h.id_evidencia}>
                <span className="remed-historial-archivo">{h.nombre_archivo}</span>
                <span className="card-sub">
                  {h.fecha_subida ?? ""} · {resultadoTexto(h)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {!abierto ? (
        <div className="remed-acciones">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setAbierto(true)}
            disabled={ocupado}
            aria-expanded={false}
            aria-controls={`${id}-form`}
          >
            <Icon name="subir" />
            {evidencia ? "Subir otra evidencia" : "Subir evidencia"}
            <span className="sr-only"> de {c.control_codigo}</span>
          </button>
        </div>
      ) : (
        <form id={`${id}-form`} className="remed-form" onSubmit={enviar} noValidate>
          <div className="field">
            <label className="field-label" htmlFor={`${id}-archivo`}>Archivo de la evidencia</label>
            <input
              ref={inputArchivo}
              id={`${id}-archivo`}
              type="file"
              className="archivo"
              accept={ACCEPT}
              aria-describedby={`${id}-archivo-ayuda${errorArchivo ? ` ${id}-archivo-error` : ""}`}
              aria-invalid={errorArchivo ? true : undefined}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setArchivo(f);
                setErrorArchivo(f ? validarArchivo(f, maxMb) : null);
              }}
            />
            <p className="field-ayuda" id={`${id}-archivo-ayuda`}>
              PDF con texto seleccionable, Word (.docx) o texto (.txt), hasta {maxMb} MB. Los datos personales se anonimizan antes del
              análisis.
            </p>
            {errorArchivo ? (
              <p className="dialogo-error" id={`${id}-archivo-error`}>
                <Icon name="alerta" />
                {errorArchivo}
              </p>
            ) : null}
          </div>

          <fieldset className="field remed-declarar">
            <legend className="field-label">¿A qué estado llegó el control?</legend>
            <div className="chip-group">
              {declarables.map((d) => (
                <label key={d} className="opcion opcion-chip">
                  <input type="radio" name={`${id}-declarado`} value={d} checked={declarado === d} onChange={() => setDeclarado(d)} />
                  <span>{ETIQUETA_ESTADO[d]}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="field">
            <label className="field-label" htmlFor={`${id}-just`}>
              Qué cambió <span className="field-opcional">(opcional)</span>
            </label>
            <textarea
              id={`${id}-just`}
              className="input input-plano textarea"
              rows={3}
              maxLength={2000}
              value={justificacion}
              placeholder="Ej.: El directorio aprobó la política de IA en septiembre y ya se aplica en todas las áreas."
              onChange={(e) => setJustificacion(e.target.value)}
            />
          </div>

          {errorEnvio ? (
            <p className="dialogo-error" role="alert">
              <Icon name="alerta" />
              {errorEnvio}
            </p>
          ) : null}

          <div className="remed-acciones">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAbierto(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={enviando || ocupado} aria-busy={enviando}>
              <Icon name="subir" />
              {enviando ? "Subiendo…" : "Analizar evidencia"}
            </button>
          </div>
        </form>
      )}
    </li>
  );
}

function ResultadoEvidencia({ evidencia: e }: { evidencia: EvidenciaRemediacionApi }) {
  const fase = faseEvidencia(e);
  const t = e.terminos_control;
  return (
    <div className="remed-resultado" data-fase={fase} role="status" aria-live="polite">
      <p className="remed-resultado-linea">
        <Icon name={fase === "mejoro" ? "check" : fase === "analizando" ? "reloj" : "info"} />
        <span>
          <strong>{e.nombre_archivo}</strong> · {resultadoTexto(e)}
        </span>
      </p>
      {t && t.terminos.length && fase !== "analizando" ? (
        <p className="remed-terminos">
          Términos del control encontrados: {t.encontrados.length} de {t.terminos.length}
          {t.encontrados.length ? (
            <span className="remed-terminos-lista">
              {t.encontrados.map((x) => (
                <span key={x} className="chip-termino">{x}</span>
              ))}
            </span>
          ) : null}
        </p>
      ) : null}
      {t?.rag?.aplicado && fase !== "analizando" ? (
        <p className="remed-terminos">
          El documento era largo: la IA analizó los {t.rag.pasajes_usados} pasajes más relacionados con el control (de{" "}
          {t.rag.pasajes_total}).
        </p>
      ) : null}
      {e.justificacion_llm && fase !== "analizando" ? <p className="remed-ia">{e.justificacion_llm}</p> : null}
    </div>
  );
}
