"use client";

/**
 * HU-29 criterio 3 · "Mis documentos": informes PDF, borradores (HU-16), evidencias y
 * constancias (HU-26) de la empresa, con descarga y eliminación.
 *
 * Eliminar pide una confirmación en la misma fila (sin diálogo modal) y es definitivo; el
 * backend deja cada eliminación en la bitácora de auditoría. Qué se borra en cada caso:
 *   informe / borrador  el archivo
 *   evidencia           el archivo (en el disco solo quedaba su texto anonimizado); la
 *                       clasificación y los puntajes que produjo se conservan
 *   constancia          su código queda anulado; el módulo sigue completado
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarDocumentos, descargarDocumento, eliminarDocumento, fechaCorta, tamanoLegible,
  type DocumentosApi, type TipoEliminable,
} from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import s from "@/components/admin/admin.module.css";

type Pestana = "informes" | "borradores" | "evidencias" | "constancias";
type Estado = { tipo: "cargando" } | { tipo: "listo"; datos: DocumentosApi } | { tipo: "error"; mensaje: string };

const PESTANAS: { id: Pestana; titulo: string }[] = [
  { id: "informes", titulo: "Informes PDF" },
  { id: "borradores", titulo: "Borradores" },
  { id: "evidencias", titulo: "Evidencias" },
  { id: "constancias", titulo: "Constancias" },
];

const AVISO_ELIMINAR: Record<TipoEliminable, string> = {
  documento: "Se borra el archivo de forma definitiva.",
  evidencia: "Se borra el archivo; el puntaje y la clasificación que produjo se conservan.",
  constancia: "Su código queda anulado. El módulo sigue completado.",
};

interface Fila {
  clave: string;
  tipo: TipoEliminable;
  id: number;
  titulo: string;
  detalle: string;
  fecha: string | null;
  descargable: boolean;
  eliminable: boolean;
  nota?: string;
}

/**
 * Correcciones 29-10: vive en su propia página (/empresa/documentos). Con `encabezado={false}`
 * la página pone el título y la tarjeta empieza directo en las pestañas.
 */
export function MisDocumentos({ recarga = 0, encabezado = true }: { recarga?: number; encabezado?: boolean }) {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [pestana, setPestana] = useState<Pestana>("informes");
  const [confirmar, setConfirmar] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [aviso, setAviso] = useState("");

  const cargar = useCallback(() => {
    cargarDocumentos()
      .then((datos) => setEstado({ tipo: "listo", datos }))
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
        }
        setEstado({
          tipo: "error",
          mensaje:
            e instanceof ErrorBff && e.info.codigo === "PLAZO_GRACIA_VENCIDO"
              ? "Terminó el plazo para descargar los documentos de tu empresa."
              : "No pudimos cargar tus documentos. Inténtalo de nuevo.",
        });
      });
  }, [router]);

  useEffect(cargar, [cargar, recarga]);

  async function descargar(f: Fila) {
    setOcupado(f.clave);
    try {
      const { blob, nombre } = await descargarDocumento(f.tipo, f.id);
      descargarBlob(blob, nombre);
      setAviso(`Descargamos ${nombre}.`);
    } catch (e) {
      setAviso(e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : "No pudimos descargar el documento.");
    } finally {
      setOcupado(null);
    }
  }

  async function eliminar(f: Fila) {
    setOcupado(f.clave);
    try {
      await eliminarDocumento(f.tipo, f.id);
      setAviso(`Eliminamos ${f.titulo}.`);
      setConfirmar(null);
      cargar();
    } catch (e) {
      setAviso(e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : "No pudimos eliminar el documento.");
    } finally {
      setOcupado(null);
    }
  }

  if (estado.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 200 }} role="status" aria-label="Cargando tus documentos" />;
  }
  if (estado.tipo === "error") {
    return <div className={s.alerta} role="alert"><strong>{estado.mensaje}</strong></div>;
  }

  const d = estado.datos;
  const filas: Record<Pestana, Fila[]> = {
    informes: d.informes.map((x) => ({
      clave: `d${x.id}`, tipo: "documento", id: x.id, titulo: x.nombre,
      detalle: tamanoLegible(x.tamano_bytes),
      fecha: x.fecha_creacion, descargable: true, eliminable: true,
    })),
    borradores: d.borradores.map((x) => ({
      clave: `d${x.id}`, tipo: "documento", id: x.id, titulo: x.nombre, detalle: tamanoLegible(x.tamano_bytes),
      fecha: x.fecha_creacion, descargable: true, eliminable: true,
    })),
    evidencias: d.evidencias.map((x) => ({
      clave: `e${x.id}`, tipo: "evidencia", id: x.id, titulo: x.nombre,
      detalle: x.origen === "remediacion" ? "Evidencia para cerrar una brecha" : "Evidencia de la evaluación",
      fecha: x.fecha_subida, descargable: !x.en_proceso, eliminable: !x.en_proceso,
      nota: x.en_proceso ? "En validación" : undefined,
    })),
    constancias: d.constancias.map((x) => ({
      clave: `c${x.ruta_id}`, tipo: "constancia", id: x.ruta_id, titulo: `Constancia: ${x.modulo}`,
      detalle: `Código de verificación ${x.codigo}`, fecha: x.fecha_completado, descargable: true, eliminable: true,
    })),
  };
  const vacios: Record<Pestana, ReactNode> = {
    informes: "Aún no hay informes guardados. Se guardan al completar una reevaluación o con Guardar informe en Mis evaluaciones.",
    borradores: "Aún no hay borradores de documentos de cumplimiento.",
    evidencias: "Tu empresa no tiene evidencias subidas.",
    constancias: "Aún no hay constancias: se obtienen al completar un módulo formativo.",
  };
  const lista = filas[pestana];

  return (
    <section className="card" aria-labelledby="titulo-mis-documentos" style={{ display: "grid", gap: 16 }}>
      {encabezado ? (
        <div className="card-head">
          <div>
            <h2 id="titulo-mis-documentos" className="card-title">Mis documentos</h2>
            <p className="card-sub">
              Informes, borradores, evidencias y constancias de tu empresa.
              {d.documentos_disponibles_hasta ? ` Puedes descargarlos hasta el ${fechaCorta(d.documentos_disponibles_hasta)}.` : ""}
              {" "}Eliminar un documento es definitivo.
            </p>
          </div>
        </div>
      ) : (
        <h2 id="titulo-mis-documentos" className="sr-only">Documentos de tu empresa</h2>
      )}
      {!encabezado && d.documentos_disponibles_hasta ? (
        <p className="callout" role="status">
          Puedes descargar tus documentos hasta el {fechaCorta(d.documentos_disponibles_hasta)}.
        </p>
      ) : null}

      <div className={s.pestanas} role="tablist" aria-label="Tipo de documento">
        {PESTANAS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            id={`tab-doc-${p.id}`}
            aria-controls="panel-documentos"
            aria-selected={pestana === p.id}
            className={s.pestana}
            onClick={() => {
              setPestana(p.id);
              setConfirmar(null);
            }}
          >
            {p.titulo} ({filas[p.id].length})
          </button>
        ))}
      </div>

      <div id="panel-documentos" role="tabpanel" aria-labelledby={`tab-doc-${pestana}`}>
        {!lista.length ? (
          <p className={s.vacio}>{vacios[pestana]}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">{PESTANAS.find((p) => p.id === pestana)?.titulo}</caption>
              <thead>
                <tr>
                  <th scope="col">Documento</th>
                  <th scope="col">Fecha</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {lista.map((f) => (
                  <tr key={f.clave}>
                    <th scope="row" style={{ wordBreak: "break-word" }}>
                      {f.titulo}
                      <span className={s.sub}>{f.detalle}</span>
                    </th>
                    <td>{fechaCorta(f.fecha)}</td>
                    <td>
                      {confirmar === f.clave ? (
                        <div className={s.acciones} role="group" aria-label={`Confirmar la eliminación de ${f.titulo}`}>
                          <span className={s.sub}>¿Eliminar? {AVISO_ELIMINAR[f.tipo]}</span>
                          <button
                            type="button"
                            className="btn btn-sm"
                            style={{ borderColor: "var(--alto)", color: "var(--alto)" }}
                            onClick={() => eliminar(f)}
                            disabled={ocupado !== null}
                            aria-busy={ocupado === f.clave}
                          >
                            Sí, eliminar
                          </button>
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(null)}>
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <div className={s.acciones}>
                          {f.nota ? <span className="badge tone-medio">{f.nota}</span> : null}
                          <button
                            type="button"
                            className="btn btn-sm"
                            onClick={() => descargar(f)}
                            disabled={!f.descargable || ocupado !== null}
                            aria-busy={ocupado === f.clave}
                            aria-label={`Descargar ${f.titulo}`}
                          >
                            Descargar
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => setConfirmar(f.clave)}
                            disabled={!f.eliminable || ocupado !== null}
                            aria-label={`Eliminar ${f.titulo}`}
                          >
                            Eliminar
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
    </section>
  );
}
