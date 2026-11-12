"use client";

/**
 * Historial de versiones de una actividad: cada vez que queda vigente se guarda una versión que ya
 * no se puede modificar, con su huella para demostrar que no se alteró.
 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { fechaHoraChile } from "@/lib/fechas";
import { mensajeError, type CatalogoMapa } from "@/lib/mapaDatos";
import {
  cargarVersionActividad, cargarVersionesActividad, type CatalogoRat, type InstantaneaVersion, type VersionResumen,
} from "@/lib/registroActividades";
import { FichaActividad } from "./Ficha";

export function HistorialActividad({
  id,
  revision,
  catalogo,
  catalogoMapa,
}: {
  id: number;
  revision: number;
  catalogo: CatalogoRat;
  catalogoMapa: CatalogoMapa | null;
}) {
  const [lista, setLista] = useState<{ version_vigente: number | null; versiones: VersionResumen[] } | null>(null);
  const [elegida, setElegida] = useState<InstantaneaVersion | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let vivo = true;
    cargarVersionesActividad(id)
      .then((r) => {
        if (!vivo) return;
        setLista(r);
        if (r.versiones.length) {
          return cargarVersionActividad(id, r.versiones[0].numero).then((v) => vivo && setElegida(v));
        }
      })
      .catch((e) => vivo && setError(mensajeError(e, "No pudimos cargar el historial. Inténtalo de nuevo.")));
    return () => {
      vivo = false;
    };
  }, [id, revision]);

  const abrir = async (numero: number) => {
    try {
      setElegida(await cargarVersionActividad(id, numero));
    } catch (e) {
      setError(mensajeError(e, "No pudimos abrir esa versión."));
    }
  };

  if (error) return <div className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></div>;
  if (!lista) return <div className="skeleton" style={{ height: 240 }} role="status" aria-label="Cargando el historial" />;
  if (!lista.versiones.length) {
    return (
      <p className="callout">
        <Icon name="info" />
        <span>Todavía no hay versiones. La primera se guarda cuando dejes la actividad vigente.</span>
      </p>
    );
  }

  return (
    <div className={ms.zonaHistorial}>
      <section className="card" aria-labelledby="titulo-versiones-rat" style={{ display: "grid", gap: 12 }}>
        <div>
          <h2 id="titulo-versiones-rat" className="card-title">Versiones vigentes</h2>
          <p className="card-sub">Cada vez que la actividad queda vigente se guarda una versión que ya no se puede modificar.</p>
        </div>
        <ol className={ms.lineaTiempo}>
          {lista.versiones.map((v) => (
            <li key={v.numero}>
              <button type="button" className={ms.version} aria-current={elegida?.numero === v.numero || undefined} onClick={() => abrir(v.numero)}>
                <span className={ms.versionNum}>{v.numero}</span>
                <strong>
                  {v.numero === lista.version_vigente ? "Versión vigente" : "Versión anterior"}
                </strong>
                <small>{fechaHoraChile(v.fecha)} · {v.resumen}</small>
              </button>
            </li>
          ))}
        </ol>
      </section>

      {elegida ? (
        <section className="card" aria-labelledby="titulo-version-rat" style={{ display: "grid", gap: 16 }}>
          <div>
            <h2 id="titulo-version-rat" className="card-title">
              Versión {elegida.numero}{elegida.es_la_vigente ? " · vigente" : ""}
            </h2>
            <p className="card-sub">
              Quedó vigente el {fechaHoraChile(elegida.fecha)}. Tomó del mapa de datos su versión {elegida.version_mapa}.
            </p>
          </div>
          <p className={ms.alertaInfo} style={elegida.verificada ? { borderColor: "rgba(20, 216, 158, 0.45)", background: "var(--ok-soft)" } : undefined}>
            <Icon name={elegida.verificada ? "escudo" : "alerta"} />
            <span>
              {elegida.verificada
                ? "Integridad verificada: el contenido coincide con su huella digital."
                : "El contenido no coincide con su huella digital. Contacta a Therion Labs."}
              <span className={ms.huella} style={{ display: "block", marginTop: 4 }}>{elegida.huella}</span>
            </span>
          </p>
          <FichaActividad contenido={elegida.contenido.actividad} mapa={elegida.contenido.mapa} catalogo={catalogo} catalogoMapa={catalogoMapa} />
        </section>
      ) : null}
    </div>
  );
}
