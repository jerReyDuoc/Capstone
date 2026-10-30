import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { advertenciaDe, textoAviso } from "@/lib/sector";
import type { PanelVista } from "@/lib/types";

/**
 * HU-10 (criterio 3) · Advertencia cuando la cohorte del sector tiene menos de k empresas.
 *
 * Se muestra en la página del sector y, en versión compacta, junto a los gráficos que
 * comparan con el rubro (Diagnóstico y Dominios), para que nadie lea la ausencia del promedio
 * como un error. No revela cuántas empresas hay: solo el umbral. Es contenido estático de la
 * página (no un aviso emergente), por eso no usa role="alert".
 */
export function AvisoCohorte({
  panel,
  compacto = false,
  hrefSector,
}: {
  panel: PanelVista;
  compacto?: boolean;
  /** En la versión compacta, enlace a la comparativa sectorial. */
  hrefSector?: string;
}) {
  const codigo = advertenciaDe(panel.sector, panel.sinRubro);
  if (!codigo) return null;
  // La falta de rubro ya se explica en el gráfico; en compacto solo se avisa la supresión
  if (compacto && codigo === "SIN_RUBRO") return null;

  const k = panel.sector?.kMinimo ?? panel.muestrasMinimas;
  const t = textoAviso(codigo, k, panel.sector);
  return (
    <aside
      className={`callout${t.tono === "aviso" ? " callout-aviso" : ""}`}
      aria-label={t.titulo}
      data-codigo={codigo}
    >
      <Icon name={t.tono === "aviso" ? "candado" : "info"} />
      <span>
        <strong>{t.titulo}.</strong> {t.cuerpo}
        {compacto && hrefSector ? (
          <>
            {" "}
            <Link href={hrefSector}>Ver cómo te comparas con tu sector</Link>
          </>
        ) : null}
      </span>
    </aside>
  );
}
