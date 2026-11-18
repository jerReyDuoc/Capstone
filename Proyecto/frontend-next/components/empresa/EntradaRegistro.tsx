"use client";

/** Auditoría UX 16-11 · Fase 8.B: entrada única al flujo del registro; lleva al paso pendiente. */
import { useEffect, useState } from "react";
import { cargarCumplimiento } from "@/lib/registroActividades";
import { pasoPendiente, PASOS_REGISTRO } from "@/lib/flujoRegistro";

export function EntradaRegistro() {
  const [error, setError] = useState(false);

  useEffect(() => {
    cargarCumplimiento()
      .then((c) => {
        const n = pasoPendiente({ mapaIniciado: c.mapa.iniciado, elementos: c.mapa.elementos, actividades: c.registro.activas });
        // replace: "atrás" no vuelve a esta página de paso
        window.location.replace(PASOS_REGISTRO[n - 1].href);
      })
      .catch(() => setError(true));
  }, []);

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Privacidad y registro</span>
          <h1 className="page-title">Arma tu registro de actividades</h1>
          <p className="page-sub">Tres pasos: tu mapa de datos, completarlo con el asistente y revisar el registro.</p>
        </div>
      </header>
      {error ? (
        <section className="card pila-chica">
          <p>No pudimos ver en qué paso vas. Elige por dónde seguir:</p>
          <ol className="pila-chica">
            {PASOS_REGISTRO.map((p) => (
              <li key={p.numero}>
                <a href={p.href}>{p.titulo}</a>: {p.descripcion}
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <p role="status" className="card-sub">Te llevamos al paso que te falta…</p>
      )}
    </>
  );
}
