"use client";

/**
 * HU-29 criterios 1 y 2 · "Mis evaluaciones" del usuario definitivo.
 *
 * Todas las evaluaciones de la empresa (las migradas del autodiagnóstico y las reevaluaciones
 * iniciadas desde la cuenta) con fecha, estado, puntaje global y nivel; el gráfico de
 * evolución global y por dimensión; y el botón para iniciar (o continuar) una reevaluación.
 * Lee GET /api/cliente/evaluaciones, que responde también sin contrato vigente (los
 * resultados son gratuitos); iniciar una reevaluación exige el servicio activo.
 *
 * Correcciones 29-10: es su propia página (/empresa/evaluaciones); el subtítulo largo pasó a un
 * botón (i) y el cliente ya no ve los números internos de cada evaluación.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EvolucionMadurez } from "@/components/charts/EvolucionMadurez";
import { InfoTip } from "@/components/ui/InfoTip";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  archivarInforme, cargarHistorial, fechaCorta, iniciarReevaluacion, textoVariacion,
  type EvaluacionHistorial, type HistorialApi,
} from "@/lib/empresa";
import { formatoPuntaje, NIVELES } from "@/lib/madurez";
import s from "@/components/admin/admin.module.css";

type Estado = { tipo: "cargando" } | { tipo: "listo"; datos: HistorialApi } | { tipo: "error" };

const TONO_NIVEL: Record<string, string> = { inicial: "alto", en_desarrollo: "medio", gestionado: "bajo", optimizado: "ok" };

export function MisEvaluaciones() {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [aviso, setAviso] = useState<{ texto: string; enlace?: boolean } | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const cargar = useCallback(() => {
    cargarHistorial()
      .then((datos) => setEstado({ tipo: "listo", datos }))
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) router.replace("/ingresar?motivo=sesion");
        else setEstado({ tipo: "error" });
      });
  }, [router]);

  useEffect(cargar, [cargar]);

  async function nueva() {
    setOcupado("nueva");
    try {
      const r = await iniciarReevaluacion();
      router.push(`/empresa/evaluacion/${r.evaluacion_id}`);
    } catch (e) {
      if (e instanceof ErrorBff && e.info.codigo === "EVALUACION_EN_CURSO" && e.info.evaluacionId) {
        router.push(`/empresa/evaluacion/${e.info.evaluacionId}`);
        return;
      }
      setAviso({
        texto:
          e instanceof ErrorBff && e.info.codigo === "CONTRATO_NO_VIGENTE"
            ? "El servicio de tu empresa no está activo: no puedes iniciar una reevaluación."
            : "No pudimos iniciar la reevaluación. Inténtalo de nuevo.",
      });
      setOcupado(null);
    }
  }

  async function guardarInforme(ev: EvaluacionHistorial) {
    setOcupado(`inf${ev.id}`);
    try {
      const doc = await archivarInforme(ev.id);
      setAviso({ texto: `Guardamos el informe del ${fechaCorta(ev.fecha)} (${doc.nombre}).`, enlace: true });
    } catch (e) {
      setAviso({
        texto: e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : "No pudimos guardar el informe. Inténtalo de nuevo.",
      });
    } finally {
      setOcupado(null);
    }
  }

  if (estado.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 240 }} role="status" aria-label="Cargando tus evaluaciones" />;
  }
  if (estado.tipo === "error") {
    return (
      <div className={s.alerta} role="alert">
        <strong>No pudimos cargar tus evaluaciones.</strong>
        <button type="button" className="btn btn-sm" onClick={() => { setEstado({ tipo: "cargando" }); cargar(); }}>
          Reintentar
        </button>
      </div>
    );
  }

  const { datos } = estado;
  const r = datos.resumen;
  const enCurso = r.evaluacion_en_curso_id;

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Mi empresa</span>
          <h1 className="page-title">
            Mis evaluaciones
            <InfoTip etiqueta="Qué evaluaciones aparecen aquí">
              Todas las evaluaciones de tu empresa, incluida la del autodiagnóstico. Para la comparación con tu rubro
              solo cuenta la más reciente completada.
            </InfoTip>
          </h1>
        </div>
        <div className={s.acciones}>
          {enCurso ? (
            <Link className="btn btn-primary" href={`/empresa/evaluacion/${enCurso}`} prefetch={false}>
              Continuar evaluación
            </Link>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={nueva}
              disabled={!datos.puede_reevaluar || ocupado !== null}
              aria-busy={ocupado === "nueva"}
              title={!datos.servicio_habilitado ? "Requiere el servicio activo de tu empresa" : undefined}
            >
              Nueva evaluación
            </button>
          )}
        </div>
      </header>

      {r.completadas ? (
        <div className={s.rejilla}>
          <div className="card kpi">
            <span className="kpi-label">Nivel actual</span>
            <span className="kpi-value">{r.nivel_actual ? NIVELES[r.nivel_actual.codigo].etiqueta : "—"}</span>
          </div>
          <div className="card kpi">
            <span className="kpi-label">Puntaje global</span>
            <span className="kpi-value">{formatoPuntaje(r.puntaje_actual)}<small>/ 100</small></span>
          </div>
          <div className="card kpi">
            <span className="kpi-label">Evolución desde la primera</span>
            <span className="kpi-value">{textoVariacion(r.variacion_total)}</span>
          </div>
          <div className="card kpi">
            <span className="kpi-label">Evaluaciones completadas</span>
            <span className="kpi-value">{r.completadas}</span>
          </div>
        </div>
      ) : null}

      {r.completadas ? (
        <section className="card" aria-label="Evolución de la madurez">
          <EvolucionMadurez evolucion={datos.evolucion} />
        </section>
      ) : null}

      {!datos.evaluaciones.length ? (
        <p className={`card ${s.vacio}`}>
          Tu empresa aún no tiene evaluaciones. {datos.puede_reevaluar ? "Inicia la primera con Nueva evaluación." : ""}
        </p>
      ) : (
        <section className="card" aria-labelledby="titulo-historial">
          <div className="card-head">
            <h2 id="titulo-historial" className="card-title">Historial</h2>
          </div>
          <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Historial de evaluaciones de la empresa</caption>
            <thead>
              <tr>
                <th scope="col">Evaluación</th>
                <th scope="col">Fecha</th>
                <th scope="col">Estado</th>
                <th scope="col" className="num">Puntaje global</th>
                <th scope="col">Nivel</th>
                <th scope="col" className="num">Variación</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {datos.evaluaciones.map((ev) => (
                <tr key={ev.id}>
                  <th scope="row">
                    {ev.tipo === "migrada" ? "Autodiagnóstico" : "Reevaluación"}
                    {ev.vigente ? <span className={s.sub}>Vigente para la comparación</span> : null}
                  </th>
                  <td>{fechaCorta(ev.fecha)}</td>
                  <td>
                    <span className={`badge tone-${ev.completada ? "ok" : "medio"}`}>{ev.completada ? "Completada" : "En curso"}</span>
                  </td>
                  <td className="num">{ev.puntaje_global != null ? formatoPuntaje(ev.puntaje_global) : "—"}</td>
                  <td>
                    {ev.nivel ? <span className={`badge tone-${TONO_NIVEL[ev.nivel.codigo] ?? "info"}`}>{ev.nivel.etiqueta}</span> : "—"}
                  </td>
                  <td className="num">{textoVariacion(ev.variacion)}</td>
                  <td>
                    <div className={s.acciones}>
                      {ev.completada ? (
                        <>
                          <Link className="btn btn-sm" href={`/panel?evaluacion=${ev.id}`} prefetch={false}>Ver resultados</Link>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => guardarInforme(ev)}
                            disabled={ocupado !== null}
                            aria-busy={ocupado === `inf${ev.id}`}
                          >
                            Guardar informe
                          </button>
                        </>
                      ) : (
                        <Link className="btn btn-primary btn-sm" href={`/empresa/evaluacion/${ev.id}`} prefetch={false}>Continuar</Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}
      <p className="sr-only" role="status" aria-live="polite">{aviso?.texto ?? ""}</p>
      {aviso ? (
        <p className="callout" aria-hidden="true">
          {aviso.texto}
          {aviso.enlace ? <> <Link href="/empresa/documentos" prefetch={false}>Ver en Mis documentos</Link></> : null}
        </p>
      ) : null}
    </>
  );
}
