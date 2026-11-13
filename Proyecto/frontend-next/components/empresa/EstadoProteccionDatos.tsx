"use client";

/**
 * "Mi empresa" · Protección de datos personales: el registro de actividades conectado con el resto.
 *
 *   - Estado del mapa de datos y del registro de actividades.
 *   - Las actividades de mayor riesgo (matriz de riesgos del registro) y las evaluaciones de impacto
 *     recomendadas, con acceso directo para generarlas ya pre-llenadas.
 *   - Lo que el registro aporta a la evaluación: con el registro vigente y completo, los controles de
 *     protección de datos que respalda (nunca baja un control) y el botón para usarlo como evidencia.
 *   - Las brechas que genera el registro (sin base de licitud, sin plazo, transferencia sin garantía,
 *     envío sin actividad) con su ruta: corregir, módulo de formación y re-evaluar el control.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarCumplimiento, rutaRemediacion, textoEstadoRegistro, TONO_RIESGO, usarRegistroComoEvidencia,
  type CumplimientoRegistro,
} from "@/lib/registroActividades";
import c from "./cumplimiento.module.css";

const TONO_SEVERIDAD: Record<string, string> = { Crítica: "tone-critico", Alta: "tone-alto", Media: "tone-medio", Baja: "tone-ok" };
const MAX_LISTA = 5;

export function EstadoProteccionDatos() {
  const [datos, setDatos] = useState<CumplimientoRegistro | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ tono: "ok" | "info"; texto: string } | null>(null);
  const [todas, setTodas] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setDatos(await cargarCumplimiento());
      setError("");
    } catch (e) {
      if (e instanceof ErrorBff && e.status === 401) {
        window.location.assign("/ingresar?motivo=sesion");
        return;
      }
      setError("No pudimos cargar el estado de tu registro de actividades.");
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const usarComoEvidencia = async () => {
    setOcupado(true);
    try {
      const r = await usarRegistroComoEvidencia();
      setAviso({ tono: r.aplicado ? "ok" : "info", texto: r.mensaje });
      await cargar();
    } catch {
      setAviso({ tono: "info", texto: "No pudimos usar el registro como evidencia. Inténtalo de nuevo." });
    } finally {
      setOcupado(false);
    }
  };

  if (error) {
    return <p className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></p>;
  }
  if (!datos) {
    return <div className="skeleton" style={{ height: 180 }} role="status" aria-label="Cargando tu registro de actividades" />;
  }

  const { mapa, registro, riesgos, brechas, evidencia } = datos;
  const respaldados = evidencia.controles.filter((x) => x.respaldado_por_registro).length;
  const brechasVisibles = todas ? brechas : brechas.slice(0, MAX_LISTA);

  return (
    <section className={`card ${c.seccion}`} aria-labelledby="titulo-proteccion">
      <div className="card-head">
        <div>
          <h2 id="titulo-proteccion" className="card-title">Protección de datos personales</h2>
          <p className="card-sub">
            Tu mapa de datos y tu registro de actividades alimentan tu evaluación, tus brechas y tus borradores.
          </p>
        </div>
      </div>

      <div className={c.tarjetas}>
        <Link href="/empresa/mapa-datos" className={c.tarjeta} prefetch={false}>
          <span className={c.etiqueta}><Icon name="mapa" />Mapa de datos</span>
          <strong>{mapa.iniciado ? `${mapa.elementos} elementos · ${mapa.flujos} envíos` : "Sin empezar"}</strong>
          <span className={c.pie}>
            {mapa.flujos_sin_actividad
              ? `${mapa.flujos_sin_actividad} envío${mapa.flujos_sin_actividad > 1 ? "s" : ""} sin actividad en el registro`
              : mapa.iniciado ? "Todos los envíos están en el registro" : "Registra qué datos tratas y dónde están"}
          </span>
        </Link>
        <Link href="/empresa/registro-actividades" className={c.tarjeta} prefetch={false} data-ok={registro.vigente_completo || undefined}>
          <span className={c.etiqueta}><Icon name="lista" />Registro de actividades</span>
          <strong>{textoEstadoRegistro(datos)}</strong>
          <span className={c.barra} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={registro.completitud} aria-label="Avance del registro">
            <span style={{ width: `${registro.completitud}%` }} />
          </span>
        </Link>
        <div className={c.tarjeta}>
          <span className={c.etiqueta}><Icon name="escudo" />Actividades de mayor riesgo</span>
          <strong>{riesgos.mayor_riesgo.length}</strong>
          <span className={c.pie}>
            {riesgos.pia_recomendadas
              ? `${riesgos.pia_recomendadas} con evaluación de impacto recomendada`
              : "Ninguna requiere evaluación de impacto"}
          </span>
        </div>
        <div className={c.tarjeta} data-ok={respaldados > 0 || undefined}>
          <span className={c.etiqueta}><Icon name="diagnostico" />Tu evaluación</span>
          <strong>
            {evidencia.evaluacion_id === null
              ? "Sin evaluación completada"
              : respaldados
                ? `${respaldados} control${respaldados > 1 ? "es" : ""} respaldado${respaldados > 1 ? "s" : ""} por el registro`
                : "El registro aún no respalda controles"}
          </strong>
          <span className={c.pie}>
            {evidencia.puntaje_general !== null ? `Puntaje actual: ${evidencia.puntaje_general.toFixed(1).replace(".", ",")}` : " "}
          </span>
        </div>
      </div>

      {aviso ? (
        <p className="callout" role="status"><Icon name={aviso.tono === "ok" ? "check" : "info"} /><span>{aviso.texto}</span></p>
      ) : null}

      {/* ------------------------------------------------ aporte a la evaluación */}
      {evidencia.evaluacion_id !== null ? (
        <div className={c.bloque}>
          <h3 className={c.titulo}>Tu registro como evidencia</h3>
          {evidencia.aplicable ? (
            <>
              <ul className={c.lista}>
                {evidencia.controles.map((x) => (
                  <li key={x.respuesta_id} className={c.item}>
                    <span>
                      <strong>{x.obligacion ?? "Control de protección de datos"}</strong>
                      <span className={c.pie}>
                        Hoy: {x.estado_actual_nombre ?? "sin respuesta"}
                        {x.estado_aportado_nombre ? ` · el registro demuestra: ${x.estado_aportado_nombre.toLocaleLowerCase("es")}` : " · el registro no lo respalda"}
                      </span>
                      {x.motivo ? <span className={c.pie}>{x.motivo}</span> : null}
                    </span>
                    {x.respaldado_por_registro ? <span className="badge tone-ok">Respaldado</span> : x.mejora ? <span className="badge tone-info">Puede mejorar</span> : null}
                  </li>
                ))}
              </ul>
              <div className={c.acciones}>
                <button type="button" className="btn btn-primary btn-sm" onClick={usarComoEvidencia} disabled={ocupado || !evidencia.por_mejorar}>
                  {ocupado ? "Actualizando…" : "Usar mi registro como evidencia"}
                </button>
                <span className={c.pie}>
                  {evidencia.por_mejorar
                    ? `Mejorará ${evidencia.por_mejorar} control${evidencia.por_mejorar > 1 ? "es" : ""} y recalculará tu puntaje. Nunca baja un control.`
                    : "Tu evaluación ya refleja lo que demuestra tu registro."}
                </span>
              </div>
            </>
          ) : (
            <>
              <p className={c.pie}>Cuando tu registro esté vigente y completo contará como evidencia en tu evaluación. Te falta:</p>
              <ul className={c.pasos}>{evidencia.faltantes.map((f) => <li key={f}>{f}</li>)}</ul>
            </>
          )}
        </div>
      ) : null}

      {/* ------------------------------------------------ matriz de mayor riesgo */}
      {riesgos.mayor_riesgo.length ? (
        <div className={c.bloque}>
          <h3 className={c.titulo}>Matriz de riesgos del registro <span className={c.pie}>({riesgos.referencia})</span></h3>
          <ul className={c.lista}>
            {riesgos.mayor_riesgo.slice(0, MAX_LISTA).map((r) => (
              <li key={r.actividad_id} className={c.item}>
                <span>
                  <Link href={`/empresa/registro-actividades?actividad=${r.actividad_id}`} prefetch={false}><strong>{r.nombre}</strong></Link>
                  <span className={c.pie}>{r.factores.join(" · ") || "Sin factores"}</span>
                  {r.requiere_pia ? <span className={c.pie}>Evaluación de impacto recomendada: {r.motivos_pia.join(" ")}</span> : null}
                </span>
                <span className={`badge ${TONO_RIESGO[r.nivel]}`}>{r.nivel} · {r.puntaje}/25</span>
              </li>
            ))}
          </ul>
          {riesgos.pia_recomendadas ? (
            <div className={c.acciones}>
              <Link href="/empresa/borradores?plantilla=pia" className="btn btn-ghost btn-sm" prefetch={false}>
                <Icon name="documento" />Generar la evaluación de impacto
              </Link>
              <span className={c.pie}>Se pre-llena con estas actividades: descripción, base de licitud, riesgos y medidas.</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ------------------------------------------------ brechas del registro */}
      <div className={c.bloque}>
        <h3 className={c.titulo}>Brechas de tu registro</h3>
        {brechas.length ? (
          <>
            <ul className={c.lista}>
              {brechasVisibles.map((b, i) => (
                <li key={`${b.codigo}-${b.actividad?.id ?? b.flujo_id ?? i}`} className={c.brecha}>
                  <div className={c.brechaCabeza}>
                    <span className={`badge ${TONO_SEVERIDAD[b.severidad] ?? "tone-info"}`}>{b.severidad}</span>
                    <strong>{b.titulo}</strong>
                  </div>
                  <p className={c.pie}>{b.texto}</p>
                  <ol className={c.ruta} aria-label="Ruta de remediación">
                    {rutaRemediacion(b).map((p) => (
                      <li key={p.clave} data-hecho={p.hecho || undefined}>
                        <Link href={p.href} prefetch={false}>{p.texto}</Link>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ul>
            {brechas.length > MAX_LISTA ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setTodas((x) => !x)}>
                {todas ? "Ver menos" : `Ver las ${brechas.length} brechas`}
              </button>
            ) : null}
          </>
        ) : (
          <p className={c.pie}>
            {registro.activas ? "Tu registro no tiene brechas de base de licitud, plazos ni transferencias." : "Aún no hay actividades que revisar."}
          </p>
        )}
      </div>
    </section>
  );
}
