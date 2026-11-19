"use client";

/**
 * Corrección 18-11 · /empresa/asistente: el asistente de registro como sección propia del menú
 * («Privacidad y registro → Asistente»), con TODO lo que hace en el panel flotante:
 *
 *   ┌ Asistente de registro ─────────────── Pregunto sobre: ( Mapa de datos | Registro ) ┐
 *   │ [ Preguntar ]  [ Revisar mi registro · 3 ]                                          │
 *   ├─────────────────────────────────────────────────────────────────────────────────────┤
 *   │ Preguntar: conversación (la misma del panel flotante, solo de esta cuenta)          │
 *   │ Revisar:   el paso que conviene ahora y una tarjeta por tipo de problema            │
 *   └─────────────────────────────────────────────────────────────────────────────────────┘
 *
 * El botón flotante del mapa de datos y del registro de actividades sigue funcionando igual. Desde aquí,
 * «Resolver» lleva a la vista donde se corrige (la actividad se abre directo con ?actividad=).
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { useConversacionGuia } from "@/hooks/useConversacionGuia";
import type { AlertaRegistro, VistaGuia } from "@/lib/guiaRegistro";
import { ContenidoAsistente, RUTA } from "./GuiaRegistro";
import g from "./guia.module.css";

const VISTAS: { id: VistaGuia; texto: string }[] = [
  { id: "mapa", texto: "Mapa de datos" },
  { id: "registro", texto: "Registro de actividades" },
];

export function SeccionAsistente({ vistaInicial }: { vistaInicial: VistaGuia }) {
  const router = useRouter();
  const [vista, setVista] = useState<VistaGuia>(vistaInicial);
  const conv = useConversacionGuia(vista);

  const irA = (a: AlertaRegistro | null, destino: VistaGuia) => {
    const id = a?.referencia?.id;
    if (a?.referencia?.tipo === "actividad" && id) router.push(`${RUTA.registro}?actividad=${id}`);
    else router.push(RUTA[destino]);
  };

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Privacidad y registro</span>
          <h1 className="page-title">Asistente de registro</h1>
          <p className="page-sub">
            Te oriento paso a paso con tu mapa de datos y tu registro de actividades. Tú completas y decides qué se
            guarda. La conversación es solo de tu cuenta.
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={conv.nuevaConversacion}
            disabled={conv.enviando || !conv.mensajes.length}>
            <Icon name="mas" /> Nueva conversación
          </button>
        </div>
      </header>

      <section className={g.seccion} aria-labelledby="titulo-asistente">
        <div className={g.seccionCabeza}>
          <h2 id="titulo-asistente" className={g.seccionTitulo}>
            <Icon name="chispa" /> Asistente
          </h2>
          <div className={g.contexto} role="radiogroup" aria-label="Sobre qué preguntas">
            {VISTAS.map((v) => (
              <button key={v.id} type="button" role="radio" aria-checked={vista === v.id} onClick={() => setVista(v.id)}>
                {v.texto}
              </button>
            ))}
          </div>
        </div>
        <ContenidoAsistente vista={vista} conv={conv} onIr={irA} />
      </section>
    </>
  );
}
