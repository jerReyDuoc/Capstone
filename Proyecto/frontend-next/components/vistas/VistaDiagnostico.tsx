"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { VistasFijadas } from "@/components/brechas/VistasFijadas";
import { CtaContratar } from "@/components/contratacion/CtaContratar";
import { AccionesInforme } from "@/components/informe/AccionesInforme";
import { BarrasCriticidad } from "@/components/charts/BarrasCriticidad";
import { BarrasDominio } from "@/components/charts/BarrasDominio";
import { RadarMadurez } from "@/components/charts/RadarMadurez";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeNivel, EstadoPanel, Kpi } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { formatoPuntaje, NIVELES } from "@/lib/madurez";
import { notaIndustria } from "@/lib/adaptadores";
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
              <div className="grid">
                <Kpi
                  className="col-3 md-col-3 card-glow"
                  icono="escudo"
                  etiqueta="Madurez general"
                  valor={formatoPuntaje(p.puntajeGeneral)}
                  sufijo="/ 100"
                  medidor={p.puntajeGeneral}
                  pista={<BadgeNivel nivel={p.nivelGeneral} />}
                />
                <Kpi
                  className="col-3 md-col-3"
                  icono="chispa"
                  etiqueta="Nivel de madurez"
                  valor={NIVELES[p.nivelGeneral].etiqueta}
                  pista={NIVELES[p.nivelGeneral].descripcion}
                />
                <Kpi
                  className="col-3 md-col-3"
                  icono="brechas"
                  etiqueta="Brechas abiertas"
                  valor={p.brechas.length}
                  pista={
                    criticas + altas > 0 ? (
                      <span>
                        <strong style={{ color: "var(--critico)" }}>{criticas}</strong> {criticas === 1 ? "crítica" : "críticas"} ·{" "}
                        <strong style={{ color: "var(--naranja)" }}>{altas}</strong> {altas === 1 ? "alta" : "altas"}
                      </span>
                    ) : (
                      "Ninguna crítica ni alta"
                    )
                  }
                />
                <Kpi
                  className="col-3 md-col-3"
                  icono="lista"
                  etiqueta="Preguntas evaluadas"
                  valor={p.controlesEvaluados}
                  pista={p.enRevision > 0 ? `${p.enRevision} en revisión por la IA` : "Sin respuestas pendientes de revisión"}
                />
              </div>

              <VistasFijadas panel={p} />

              <div className="grid">
                <div className="card col-7 md-col-7">
                  <RadarMadurez
                    dominios={p.dominios}
                    onSeleccionar={(d) => router.push(`${href("/panel/dominios")}#${slug(d.nombre)}`)}
                  />
                </div>
                <div className="card col-5 md-col-5">
                  <BarrasCriticidad
                    conteo={p.brechasPorSeveridad}
                    onSeleccionar={(s) => router.push(href("/panel/brechas", { severidad: s }))}
                  />
                </div>
              </div>

              <div className="grid">
                <div className="card col-6 md-col-12">
                  <BarrasDominio
                    dominios={p.dominios}
                    notaIndustria={notaIndustria(p) ?? undefined}
                    onSeleccionar={(d) => router.push(`${href("/panel/dominios")}#${slug(d.nombre)}`)}
                  />
                </div>
                <div className="col-6 md-col-12" style={{ display: "grid" }}>
                  <ResumenBrechas brechas={p.brechas} />
                </div>
              </div>

              {/* HU-31: después de los resultados, el siguiente paso (solo para el encuestado) */}
              <CtaContratar brechas={p.brechas.length} />

              <p className="callout">
                <Icon name="info" />
                <span>
                  <strong>De la señal a la decisión.</strong> Empieza por las brechas críticas: cada una trae la acción
                  sugerida y la ruta formativa para cerrarla. En{" "}
                  <Link href={href("/panel/capacitacion")}>Capacitación</Link> verás el plan de estudio por dimensión, y
                  con «Enviar por correo» guardas una copia del informe en tu bandeja.
                </span>
              </p>
            </>
          );
        }}
      </EstadoPanel>
    </>
  );
}
