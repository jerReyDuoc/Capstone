"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AvanceEmpresa } from "@/components/formacion/AvanceEmpresa";
import { TutorIA } from "@/components/formacion/TutorIA";
import { AccionesInforme } from "@/components/informe/AccionesInforme";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeNivel, EstadoPanel, Kpi } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { useAvanceFormativo } from "@/hooks/useAvanceFormativo";
import { usePlanFormativo } from "@/hooks/usePlanFormativo";
import { descargarTexto } from "@/lib/exportar";
import { accionModulo, ESTADO_MODULO, hrefModulo, hrefRemediacion } from "@/lib/formacion";
import { formatoPuntaje } from "@/lib/madurez";
import {
  dimensionPrioritaria,
  FILTROS_PLAN_VACIOS,
  filtrarDimension,
  horasTexto,
  NIVEL_FORMATIVO_INFO,
  NIVELES_FORMATIVOS,
  planACsv,
  PRIORIDAD_TEXTO,
  type FiltrosPlan,
} from "@/lib/planFormativo";
import { SEVERIDAD_TONO } from "@/lib/severidad";
import { slug } from "@/lib/slug";
import type {
  AvanceFormativoApi,
  DimensionPlanApi,
  ModuloAvanceApi,
  ModuloPlanApi,
  NivelFormativo,
  PanelVista,
  PlanFormativoApi,
} from "@/lib/types";

/**
 * HU-12 · Como encargado de capacitación, quiero recibir planes de estudio recomendados
 * según mis brechas, para elevar las competencias del personal en protección de datos y
 * uso responsable de IA.
 *
 *   C1 Mapeo automático brechas → catálogo formativo     franja "Cómo se armó" + "Cierra N brechas"
 *   C2 Niveles (Inicial/Intermedio/Avanzado) con objetivos  guía de niveles, nivel por dimensión y módulo
 *   C3 Panel organizado por dimensión normativa            una sección por dimensión
 *
 * HU-26 (usuario definitivo, modo "cliente"): el mismo panel muestra el avance de la empresa
 * (AvanceEmpresa), el estado de cada módulo con su acción (Empezar / Continuar / Constancia)
 * y marca las brechas cuya formación ya está hecha. El encuestado ve el plan y un aviso de
 * que los módulos se recorren con el servicio contratado.
 *
 * HU-15: el usuario definitivo tiene además el Agente IA Tutor (tarjeta "Hablar con el
 * tutor"), que conversa sobre todas las brechas de la evaluación vigente de su empresa.
 */
export function VistaCapacitacion() {
  const { evaluacionId } = usePanel();
  const [aviso, setAviso] = useState("");

  return (
    <>
      <PageHeader
        eyebrow="Plan de estudio recomendado"
        titulo="Capacitación"
        subtitulo="Rutas formativas para cerrar tus brechas en protección de datos y uso responsable de IA, con el nivel que necesita cada dimensión."
      >
        {evaluacionId ? <AccionesInforme evaluacionId={evaluacionId} onAviso={setAviso} tamano="md" /> : null}
      </PageHeader>
      <p className="aviso-accion" role="status" aria-live="polite" hidden={!aviso}>
        {aviso}
      </p>
      <EstadoPanel>{(p) => <Plan panel={p} onAviso={setAviso} />}</EstadoPanel>
    </>
  );
}

function Plan({ panel, onAviso }: { panel: PanelVista; onAviso: (t: string) => void }) {
  const estado = usePlanFormativo();

  if (estado.tipo === "cargando") {
    return (
      <div role="status" aria-live="polite" className="grid">
        <span className="sr-only">Cargando el plan formativo…</span>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton col-3 md-col-3" style={{ height: 132 }} />
        ))}
        <div className="skeleton col-12" style={{ height: 360 }} />
      </div>
    );
  }
  if (estado.tipo === "no-disponible" || estado.tipo === "error") {
    return (
      <div className="state" role={estado.tipo === "error" ? "alert" : "status"}>
        <Icon name="birrete" width={32} height={32} style={{ color: estado.tipo === "error" ? "var(--alto)" : "var(--medio)" }} />
        <h2>{estado.tipo === "error" ? "No pudimos cargar el plan" : "El plan aún no está disponible"}</h2>
        <p>{estado.mensaje}</p>
      </div>
    );
  }
  return <PlanListo plan={estado.plan} panel={panel} onAviso={onAviso} />;
}

function PlanListo({ plan, panel, onAviso }: { plan: PlanFormativoApi; panel: PanelVista; onAviso: (t: string) => void }) {
  const { href, modo, evaluacionId } = usePanel();
  const { estado: estadoAvance } = useAvanceFormativo();
  const avance: AvanceFormativoApi | null = estadoAvance.tipo === "listo" ? estadoAvance.avance : null;
  const [filtros, setFiltros] = useState<FiltrosPlan>(FILTROS_PLAN_VACIOS);
  const r = plan.resumen;
  const prioritaria = dimensionPrioritaria(plan);
  const porBrechas = plan.dimensiones.reduce((s, d) => s + d.modulos.filter((m) => m.motivo === "brechas").length, 0);
  const visibles = useMemo(
    () => plan.dimensiones.map((d) => [d, filtrarDimension(d, filtros)] as const),
    [plan, filtros],
  );
  const totalVisibles = visibles.reduce((s, [, m]) => s + m.length, 0);
  const hayFiltros = filtros.nivel != null || filtros.soloBrechas;

  const exportarCsv = () => {
    descargarTexto(planACsv(plan), `plan_formativo_evaluacion-${plan.evaluacion_id}.csv`);
    onAviso(`Descargamos el plan (${r.modulos} módulos) en CSV, listo para tu planilla o LMS.`);
  };

  return (
    <>
      {avance ? <AvanceEmpresa avance={avance} evaluacionId={evaluacionId} /> : null}
      {/* HU-15: Agente IA Tutor con todas las brechas de la evaluación vigente (solo cliente) */}
      {avance ? <TutorIA variante="tarjeta" /> : null}
      {estadoAvance.tipo === "cargando" ? (
        <div className="skeleton" style={{ height: 220 }} role="status" aria-label="Cargando el avance de tu empresa" />
      ) : null}
      {estadoAvance.tipo === "error" ? (
        <p className="callout callout-aviso" role="alert">
          <Icon name="alerta" />
          <span>
            <strong>No pudimos cargar el avance de tu empresa.</strong> {estadoAvance.mensaje}
          </span>
        </p>
      ) : null}
      {modo === "encuestado" ? (
        <p className="callout">
          <Icon name="candado" />
          <span>
            <strong>Los módulos se recorren con el servicio contratado.</strong> El plan es tuyo y gratis; con la plataforma
            tu empresa hace cada módulo, registra su avance y obtiene constancias.{" "}
            <Link href={href("/panel/contratar")}>Ver cómo contratar</Link>
          </span>
        </p>
      ) : null}

      <div className="grid">
        <Kpi
          className="col-3 md-col-3 card-glow"
          icono="birrete"
          etiqueta="Módulos recomendados"
          valor={r.modulos}
          pista={`${porBrechas} cierran brechas · ${r.modulos - porBrechas} base de nivel`}
        />
        <Kpi
          className="col-3 md-col-3"
          icono="reloj"
          etiqueta="Horas de formación"
          valor={r.horas}
          sufijo="h"
          pista={r.horas ? `Unas ${Math.max(1, Math.round(r.horas / 8))} jornadas de 8 horas` : "Sin módulos con duración"}
        />
        <Kpi
          className="col-3 md-col-3"
          icono="check"
          etiqueta="Brechas con ruta"
          valor={`${r.brechas_mapeadas}/${r.brechas_total}`}
          medidor={r.cobertura_mapeo}
          pista={
            r.brechas_total === 0
              ? "Sin brechas abiertas"
              : plan.brechas_sin_ruta.length
                ? `${plan.brechas_sin_ruta.length} sin ruta en el catálogo`
                : "Todas tienen una ruta del catálogo"
          }
        />
        <Kpi
          className="col-3 md-col-3"
          icono="diana"
          etiqueta="Empieza por"
          valor={<span className="kpi-texto">{prioritaria?.dominio ?? "Mantener el nivel"}</span>}
          pista={
            prioritaria
              ? `Nivel ${prioritaria.nivel_asignado} · ${prioritaria.brechas} ${prioritaria.brechas === 1 ? "brecha" : "brechas"}`
              : "Ninguna brecha requiere capacitación"
          }
        />
      </div>

      {/* C1: de dónde sale el plan */}
      <p className="analisis">
        <Icon name="chispa" />
        <span className="analisis-flujo">
          <span>
            <strong>{r.brechas_total}</strong> brechas detectadas
          </span>
          <span className="sep" aria-hidden="true">→</span>
          <span>
            <strong>{r.brechas_mapeadas}</strong> asociadas a una ruta del catálogo formativo
          </span>
          <span className="sep" aria-hidden="true">→</span>
          <span>
            <strong>{r.modulos}</strong> módulos en <strong>{r.dimensiones}</strong> dimensiones
          </span>
        </span>
      </p>

      {/* C2: cómo se asigna el nivel + filtros */}
      <section className="card" aria-labelledby="niveles-titulo" style={{ display: "grid", gap: 16 }}>
        <div className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h2 className="card-title" id="niveles-titulo">Cómo asignamos el nivel</h2>
            <p className="card-sub">Cada dimensión recibe el nivel que corresponde a su puntaje; las brechas suman los módulos que las cierran.</p>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={exportarCsv}>
            <Icon name="tabla" />
            Exportar plan CSV
          </button>
        </div>
        <ol className="niveles-guia">
          {NIVELES_FORMATIVOS.map((n, i) => (
            <li key={n} className={`nivel-${slug(n)}`}>
              <span className="nivel-paso" aria-hidden="true">{i + 1}</span>
              <span>
                <strong>{n}</strong> <span className="nivel-rango">{NIVEL_FORMATIVO_INFO[n].rango}</span>
                <span className="nivel-enfoque">{NIVEL_FORMATIVO_INFO[n].enfoque}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="toolbar" role="group" aria-label="Filtrar módulos">
          <div className="chip-group" role="group" aria-label="Nivel">
            <button type="button" className="chip" aria-pressed={filtros.nivel == null} onClick={() => setFiltros((f) => ({ ...f, nivel: null }))}>
              Todos los niveles
            </button>
            {NIVELES_FORMATIVOS.map((n) => (
              <button
                key={n}
                type="button"
                className="chip"
                aria-pressed={filtros.nivel === n}
                onClick={() => setFiltros((f) => ({ ...f, nivel: f.nivel === n ? null : n }))}
              >
                {n}
              </button>
            ))}
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={filtros.soloBrechas}
              onChange={(e) => setFiltros((f) => ({ ...f, soloBrechas: e.target.checked }))}
            />
            <span>Solo los módulos que cierran brechas</span>
          </label>
          <p className="card-sub" role="status" aria-live="polite" style={{ marginLeft: "auto", alignSelf: "center" }}>
            {hayFiltros ? `Mostrando ${totalVisibles} de ${r.modulos} módulos` : `${r.modulos} módulos`}
          </p>
        </div>
      </section>

      {/* C3: por dimensión normativa */}
      {visibles.map(([d, modulos]) => (
        <Dimension
          key={d.dominio}
          dimension={d}
          modulos={modulos}
          hrefBrechas={href("/panel/brechas", { dominio: d.dominio })}
          panel={panel}
          avance={avance}
        />
      ))}

      {plan.brechas_sin_ruta.length ? (
        <p className="callout callout-aviso">
          <Icon name="alerta" />
          <span>
            <strong>
              {plan.brechas_sin_ruta.length} {plan.brechas_sin_ruta.length === 1 ? "brecha no tiene" : "brechas no tienen"} ruta en el catálogo:
            </strong>{" "}
            {plan.brechas_sin_ruta.map((b) => b.codigo).join(", ")}. Pide al equipo de cumplimiento asociarles una ruta formativa
            para que entren al plan.
          </span>
        </p>
      ) : null}
    </>
  );
}

const PASOS: NivelFormativo[] = NIVELES_FORMATIVOS;

function Dimension({
  dimension: d,
  modulos,
  hrefBrechas,
  panel,
  avance,
}: {
  dimension: DimensionPlanApi;
  modulos: ModuloPlanApi[];
  hrefBrechas: string;
  panel: PanelVista;
  avance: AvanceFormativoApi | null;
}) {
  const id = `cap-${slug(d.dominio)}`;
  const dominioPanel = panel.dominios.find((x) => x.nombre === d.dominio);
  return (
    <section className="card dimension" aria-labelledby={`${id}-t`} id={id}>
      <header className="dimension-head">
        <div style={{ display: "grid", gap: 6 }}>
          <h2 className="card-title" id={`${id}-t`}>{d.dominio}</h2>
          <p className="card-sub">
            {d.puntaje != null ? <>Puntaje {formatoPuntaje(d.puntaje)} / 100 · </> : null}
            {d.brechas} {d.brechas === 1 ? "brecha" : "brechas"} · {horasTexto(d.horas)} de formación
            {dominioPanel && dominioPanel.diferenciaMeta < 0 ? <> · faltan {formatoPuntaje(-dominioPanel.diferenciaMeta)} pts para la meta</> : null}
          </p>
        </div>
        <div className="dimension-nivel">
          {d.nivel_madurez ? (
            <span className="dimension-dato">
              <span className="dimension-dato-label">Madurez</span>
              <BadgeNivel nivel={d.nivel_madurez} />
            </span>
          ) : null}
          <span className="dimension-dato">
            <span className="dimension-dato-label">Nivel del plan</span>
          <div className="nivel-track" role="img" aria-label={`Nivel de capacitación asignado: ${d.nivel_asignado}`}>
            {PASOS.map((n) => (
              <span key={n} className="nivel-track-paso" data-activo={n === d.nivel_asignado || undefined} data-pasado={PASOS.indexOf(n) < PASOS.indexOf(d.nivel_asignado) || undefined}>
                {n}
              </span>
            ))}
          </div>
          </span>
        </div>
      </header>
      <p className="dimension-objetivo">
        <Icon name="diana" />
        <span>
          <strong>Objetivo del nivel {d.nivel_asignado}:</strong> {d.objetivo_nivel}
        </span>
      </p>

      {modulos.length === 0 ? (
        <p className="card-sub">Ningún módulo de esta dimensión coincide con el filtro.</p>
      ) : (
        <ul className="modulo-grid">
          {modulos.map((m) => (
            <Modulo
              key={m.ruta.id}
              modulo={m}
              dominio={d.dominio}
              asignado={d.nivel_asignado}
              progreso={avance?.modulos.find((x) => x.ruta_id === m.ruta.id) ?? null}
            />
          ))}
        </ul>
      )}

      {d.brechas > 0 ? (
        <div className="chart-foot">
          <span>
            <strong style={{ color: "var(--text)" }}>{d.brechas}</strong> {d.brechas === 1 ? "brecha abierta" : "brechas abiertas"} en {d.dominio}
          </span>
          <Link href={hrefBrechas} className="btn btn-ghost btn-sm">
            Ver brechas<span className="sr-only"> de {d.dominio}</span>
            <Icon name="flecha" />
          </Link>
        </div>
      ) : null}
    </section>
  );
}

function Modulo({
  modulo: m,
  dominio,
  asignado,
  progreso,
}: {
  modulo: ModuloPlanApi;
  dominio: string;
  asignado: NivelFormativo;
  /** HU-26: avance de la empresa en este módulo (solo el usuario definitivo). */
  progreso: ModuloAvanceApi | null;
}) {
  const despues = PASOS.indexOf(m.nivel) > PASOS.indexOf(asignado);
  const { href, evaluacionId } = usePanel();
  const completado = progreso?.estado === "completado";
  const tituloId = `mod-${m.ruta.id}`;
  const urgente = m.motivo === "brechas" && m.prioridad !== "Sin clasificar";
  return (
    <li className={`modulo ${m.motivo === "brechas" ? `sev-${SEVERIDAD_TONO[m.prioridad as keyof typeof SEVERIDAD_TONO] ?? "info"}` : "modulo-base"}`}>
      <article aria-labelledby={tituloId} className="modulo-cuerpo">
        <div className="modulo-top">
          <span className="nivel-chip" data-nivel={m.nivel}>
            <span aria-hidden="true" className="nivel-puntos">
              {PASOS.map((n) => (
                <i key={n} data-on={PASOS.indexOf(n) <= PASOS.indexOf(m.nivel) || undefined} />
              ))}
            </span>
            {m.nivel}
          </span>
          {m.motivo === "brechas" ? (
            <span className={`badge tone-${SEVERIDAD_TONO[m.prioridad as keyof typeof SEVERIDAD_TONO] ?? "info"}`}>
              <span className="sr-only">Prioridad </span>
              {PRIORIDAD_TEXTO[m.prioridad]}
            </span>
          ) : (
            <span className="badge tone-info">{PRIORIDAD_TEXTO.Complementario}</span>
          )}
        </div>
        <h3 className="modulo-titulo" id={tituloId}>{m.ruta.nombre}</h3>
        {despues ? (
          <p className="modulo-secuencia">
            <Icon name="info" />
            Tómalo después del nivel {asignado}: lo pide una brecha concreta, pero se apoya en esas bases.
          </p>
        ) : null}
        {m.ruta.objetivo ? <p className="modulo-objetivo">{m.ruta.objetivo}</p> : null}
        <p className="modulo-meta">
          <span>
            <Icon name="reloj" />
            {horasTexto(m.ruta.horas)}
          </span>
          {m.ruta.modalidad ? <span>{m.ruta.modalidad}</span> : null}
          {m.ruta.publico_objetivo ? (
            <span>
              <Icon name="usuario" />
              {m.ruta.publico_objetivo}
            </span>
          ) : null}
        </p>

        {m.ruta.objetivos_especificos.length || m.ruta.contenidos.length ? (
          <details className="modulo-detalle">
            <summary>Objetivos y contenidos</summary>
            {m.ruta.objetivos_especificos.length ? (
              <>
                <p className="modulo-subtitulo">Al terminar, el equipo podrá:</p>
                <ul>
                  {m.ruta.objetivos_especificos.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {m.ruta.contenidos.length ? (
              <>
                <p className="modulo-subtitulo">Contenidos</p>
                <ul>
                  {m.ruta.contenidos.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </details>
        ) : null}

        <div className="modulo-pie">
          {m.motivo === "brechas" ? (
            <>
              <p className="modulo-subtitulo">
                {urgente ? "Cierra" : "Relacionado con"} {m.brechas.length} {m.brechas.length === 1 ? "brecha" : "brechas"}
              </p>
              <ul className="chips-brechas">
                {m.brechas.map((b) => (
                  <li key={`${b.codigo}-${b.prioridad}`}>
                    <Link
                      href={href("/panel/brechas", { q: b.codigo })}
                      className={`chip-brecha sev-${SEVERIDAD_TONO[b.severidad]}`}
                      aria-label={`${b.codigo}, severidad ${b.severidad}${b.dominio !== dominio ? `, de ${b.dominio}` : ""}${completado ? ", formación completada" : ""}. Ver en el listado de brechas.`}
                    >
                      {completado ? <Icon name="check" className="chip-brecha-check" /> : null}
                      <span className="code">{b.codigo}</span>
                      {b.dominio !== dominio ? <span className="chip-brecha-dom">{b.dominio}</span> : null}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="card-sub">Base del nivel asignado a la dimensión: refuerza al equipo aunque no haya brechas que lo exijan.</p>
          )}
          {completado && m.brechas.length ? (
            <p className="modulo-formado">
              Formación hecha. Para cerrar {m.brechas.length === 1 ? "esta brecha" : "estas brechas"}, sube evidencia nueva.{" "}
              <Link href={hrefRemediacion(evaluacionId, m.brechas[0]?.respuesta_id)}>Subir evidencia</Link>
            </p>
          ) : null}
        </div>

        {progreso ? (
          <div className="modulo-progreso" data-estado={progreso.estado}>
            <div className="modulo-progreso-dato">
              <span className={`badge tone-${ESTADO_MODULO[progreso.estado].tono}`}>{ESTADO_MODULO[progreso.estado].etiqueta}</span>
              <span className="modulo-progreso-texto">
                {completado
                  ? `Constancia ${progreso.codigo_constancia ?? ""}`.trim()
                  : `${progreso.lecciones_vistas} de ${progreso.lecciones_total} lecciones`}
              </span>
            </div>
            {!completado ? (
              <div
                className="meter"
                role="progressbar"
                aria-label={`Lecciones de ${m.ruta.nombre}`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(progreso.porcentaje_lecciones)}
              >
                <span style={{ width: `${progreso.porcentaje_lecciones}%` }} />
              </div>
            ) : null}
            <Link
              href={hrefModulo(m.ruta.id, evaluacionId)}
              className={`btn ${progreso.estado === "completado" ? "btn-ghost" : "btn-primary"} btn-sm modulo-accion`}
            >
              {progreso.estado === "no_iniciado" ? <Icon name="play" /> : progreso.estado === "completado" ? <Icon name="constancia" /> : null}
              {accionModulo(progreso)}
              <span className="sr-only">: {m.ruta.nombre}</span>
            </Link>
          </div>
        ) : null}
      </article>
    </li>
  );
}
