"use client";

/**
 * HU-29 criterio 2 · Reevaluación desde la cuenta de la empresa.
 *
 * La evaluación ya pertenece a la empresa (sin usuario temporal ni clave de acceso): se
 * responde con el cuestionario de siempre, pero por el BFF del cliente. Al completarla, el
 * backend archiva su informe PDF en "Mis documentos" y el cuestionario lleva a los resultados.
 */
import Link from "next/link";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { Cuestionario } from "@/components/cuestionario/Cuestionario";
import { BrandMark } from "@/components/ui/Icon";
import s from "@/components/admin/admin.module.css";

export function ReevaluacionEmpresa({ evaluacionId }: { evaluacionId: number }) {
  return (
    <div className={s.pagina}>
      <a href="#contenido" className="skip-link">Saltar al contenido</a>
      <header className={s.barra}>
        <div className={s.marca}>
          <BrandMark aria-hidden="true" />
          <span>
            ComplianceAI
            <span className={s.marcaSub}>Reevaluación de tu empresa</span>
          </span>
        </div>
        <BotonCerrarSesion tipo="cliente" />
      </header>

      <main id="contenido" className={s.contenido} tabIndex={-1}>
        <div>
          <p className="card-sub" style={{ margin: 0 }}>
            <Link href="/empresa" prefetch={false}>← Volver al espacio de tu empresa</Link>
          </p>
          <h1 className="page-title">Reevaluación N.º {evaluacionId}</h1>
          <p className="page-sub">
            Responde de nuevo los controles para medir cuánto avanzó tu organización. Tu avance se guarda solo y puedes
            retomarla desde Mis evaluaciones. Al completarla se calcula el nuevo nivel de madurez y su informe queda en
            Mis documentos.
          </p>
        </div>
        <Cuestionario evaluacionId={evaluacionId} base="/bff/cliente/api" onLimites={() => undefined} />
      </main>
    </div>
  );
}
