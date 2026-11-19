"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { VistasFijadas } from "@/components/brechas/VistasFijadas";
import { CtaContratar } from "@/components/contratacion/CtaContratar";
import { AccionesInforme } from "@/components/informe/AccionesInforme";
import { BarrasCriticidad } from "@/components/charts/BarrasCriticidad";
import { MadurezPorDominio } from "@/components/charts/MadurezPorDominio";
import { AvisoCohorte } from "@/components/sector/AvisoCohorte";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeNivel, EstadoPanel } from "@/components/ui/Basicos";
import { ComoSeCalcula } from "@/components/ui/ComoSeCalcula";
import { usePanel } from "@/hooks/usePanel";
import { formatoPuntaje, NIVELES } from "@/lib/madurez";
import { slug } from "@/lib/slug";
import { ResumenBrechas } from "./ResumenBrechas";

export function VistaDiagnostico() {
  const router = useRouter();
  const { href, evaluacionId, estado } = usePanel();
  const [aviso, setAviso] = useState("");

  return (
    <>
      <PageHeader
        eyebrow="Cumplimiento y protección de datos"
        titulo="Diagnóstico"
        subtitulo="Visión ejecutiva de la madurez en gobernanza de IA de tu empresa y de las brechas que requieren acción."
      >
        {evaluacionId && estado.tipo === "listo" ? (
          <AccionesInforme evaluacionId={evaluacionId} onAviso={setAviso} tamano="md" />
        ) : null}
      </PageHeader>
      <p className="aviso-accion" role="status" aria-live="polite" hidden={!aviso}>
        {aviso}
      </p>

      <EstadoPanel>
        {(p) => {
          const criticas = p.brechasPorSeveridad["Crítica"];
          const altas = p.brechasPorSeveridad.Alta;
          return (
            <>
              {/* Auditoría UX 16-11 · Fase 5.A: UN bloque de resultado (antes, tres tarjetas repetían
                  el puntaje, el nivel y las brechas). Lo que el usuario vino a ver va arriba. */}
              <section className="card resultado" aria-labelledby="resultado-titulo">
                <div className="resultado-cifra">
                  <h2 className="sr-only" id="resultado-titulo">Tu resultado</h2>
                  <p className="resultado-puntaje">
                    {formatoPuntaje(p.puntajeGeneral)}
                    <small>/ 100</small>
                  </p>
                  <div
                    className="meter"
                    role="meter"
                    aria-label={`Madurez general: ${formatoPuntaje(p.puntajeGeneral)} de 100`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(p.puntajeGeneral)}
                  >
                    <span style={{ width: `${Math.max(0, Math.min(100, p.puntajeGeneral))}%` }} />
                  </div>
                </div>
                <div className="resultado-texto">
                  <p className="resultado-linea">
                    <BadgeNivel nivel={p.nivelGeneral} />
                    <span>{NIVELES[p.nivelGeneral].descripcion}</span>
                  </p>
                  <p className="resultado-linea">
                    {p.brechas.length === 0 ? (
                      <span>Sin brechas abiertas.</span>
                    ) : (
                      <span>
                        <strong>{p.brechas.length}</strong> {p.brechas.length === 1 ? "brecha abierta" : "brechas abiertas"}
                        {criticas + altas > 0 ? (
                          <>
                            {": "}
                            <strong className="cifra-critica">{criticas}</strong> {criticas === 1 ? "crítica" : "críticas"} y{" "}
                            <strong className="cifra-alta">{altas}</strong> {altas === 1 ? "alta" : "altas"}
                          </>
                        ) : null}
                        .
                      </span>
                    )}
                    {p.brechas.length ? <Link href={href("/panel/brechas")}>Ver brechas</Link> : null}
                  </p>
                  <p className="card-sub">
                    {p.controlesEvaluados} preguntas evaluadas
                    {p.enRevision > 0 ? ` · ${p.enRevision} en revisión por la IA` : ""}
                  </p>
                </div>
              </section>

              <VistasFijadas panel={p} />

              <div className="grid">
                <div className="card col-7 md-col-12">
                  {/* Mejoras 19-11: radar de madurez (barras en celular o si el usuario las elige) */}
                  <MadurezPorDominio
                    dominios={p.dominios}
                    onSeleccionar={(d) => router.push(`${href("/panel/dominios")}#${slug(d.nombre)}`)}
                  />
                </div>
                <div className="card col-5 md-col-12">
                  <BarrasCriticidad
                    conteo={p.brechasPorSeveridad}
                    onSeleccionar={(s) => router.push(href("/panel/brechas", { severidad: s }))}
                  />
                </div>
              </div>

              {/* HU-10: la comparación con el rubro va DESPUÉS del gráfico que la muestra */}
              <AvisoCohorte panel={p} compacto hrefSector={href("/panel/sector")} />

              <ResumenBrechas brechas={p.brechas} />

              {/* HU-31: después de los resultados, el siguiente paso (solo para el encuestado) */}
              <CtaContratar brechas={p.brechas.length} />

              <ComoSeCalcula>
                <p>
                  Cada pregunta respondida suma según su estado (cumplido, parcial o no cumplido) y el puntaje de cada
                  dimensión va de 0 a 100. El puntaje general pondera las dimensiones por la cantidad de preguntas.
                </p>
                <ul>
                  {(Object.keys(NIVELES) as (keyof typeof NIVELES)[]).map((n) => (
                    <li key={n}>
                      <strong>{NIVELES[n].etiqueta}:</strong> {NIVELES[n].descripcion}
                    </li>
                  ))}
                </ul>
                <p>
                  Las brechas se ordenan por severidad: cruzan el impacto de cada práctica con qué tan incumplida está.
                  En <Link href={href("/panel/capacitacion")}>Capacitación</Link> está el plan de estudio para cerrarlas.
                </p>
              </ComoSeCalcula>
            </>
          );
        }}
      </EstadoPanel>
    </>
  );
}
