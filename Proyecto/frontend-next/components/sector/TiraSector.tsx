import { Icon } from "@/components/ui/Icon";
import { describirTira, enEscala } from "@/lib/sector";
import s from "./sector.module.css";

/**
 * HU-10 · Tira 0–100 con tu puntaje frente al sector.
 *
 * - punto menta: tu empresa
 * - trazo discontinuo lavanda: promedio del sector
 * - banda lavanda: mitad central del sector (percentiles 25–75, solo con cohortes grandes)
 * - trazo punteado amarillo: meta de cumplimiento (opcional)
 * Cohorte insuficiente (promedio null): la tira se raya y lleva un sello "Oculto"; tu punto
 * se sigue viendo. Las formas (punto, discontinuo, punteado, rayado) no dependen solo del
 * color (WCAG 1.4.1). Toda la información está en el aria-label (role="img").
 */
export function TiraSector({
  nombre,
  puntaje,
  promedio,
  p25,
  p75,
  meta,
  k,
  grande = false,
  conEscala = false,
}: {
  nombre: string;
  puntaje: number;
  promedio: number | null;
  p25: number | null;
  p75: number | null;
  meta?: number | null;
  k: number;
  grande?: boolean;
  conEscala?: boolean;
}) {
  const oculta = promedio == null;
  const clases = [s.tira, grande ? s.grande : "", oculta ? s.oculta : ""].filter(Boolean).join(" ");
  return (
    <div>
      <div className={clases} role="img" aria-label={describirTira({ nombre, puntaje, promedio, p25, p75, meta, k })}>
        <span className={s.pista} aria-hidden="true" />
        {oculta ? (
          // El sello va del lado opuesto a tu punto para no taparlo
          <span className={s.sello} aria-hidden="true" style={puntaje < 50 ? { left: "auto", right: 10 } : undefined}>
            <Icon name="candado" />
            Oculto: menos de {k} empresas
          </span>
        ) : null}
        {!oculta && p25 != null && p75 != null ? (
          <span
            className={s.banda}
            aria-hidden="true"
            style={{ left: `${enEscala(p25)}%`, width: `${Math.max(0.5, enEscala(p75) - enEscala(p25))}%` }}
          />
        ) : null}
        {meta != null ? (
          <span className={`${s.marca} ${s.marcaMeta}`} aria-hidden="true" style={{ left: `${enEscala(meta)}%` }} />
        ) : null}
        {!oculta ? (
          <span className={`${s.marca} ${s.marcaSector}`} aria-hidden="true" style={{ left: `${enEscala(promedio)}%` }} />
        ) : null}
        <span className={s.tu} aria-hidden="true" style={{ left: `${enEscala(puntaje)}%` }} />
      </div>
      {conEscala ? (
        <div className={s.escala} aria-hidden="true">
          {[0, 25, 50, 75, 100].map((n) => (
            <span key={n}>{n}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Leyenda de la tira (formas, no solo color). */
export function LeyendaSector({
  conSector = true,
  conBanda,
  conMeta,
  conOculta,
}: {
  conSector?: boolean;
  conBanda: boolean;
  conMeta: boolean;
  conOculta: boolean;
}) {
  return (
    <ul className={s.leyenda} aria-label="Leyenda">
      <li>
        <i className={`${s.muestra} ${s.muestraTu}`} aria-hidden="true" />
        Tu empresa
      </li>
      {conSector ? (
        <li>
          <i className={`${s.muestra} ${s.muestraSector}`} aria-hidden="true" />
          Promedio del sector
        </li>
      ) : null}
      {conBanda ? (
        <li>
          <i className={`${s.muestra} ${s.muestraBanda}`} aria-hidden="true" />
          Mitad central del sector
        </li>
      ) : null}
      {conMeta ? (
        <li>
          <i className={`${s.muestra} ${s.muestraMeta}`} aria-hidden="true" />
          Meta de cumplimiento
        </li>
      ) : null}
      {conOculta ? (
        <li>
          <i className={`${s.muestra} ${s.muestraOculta}`} aria-hidden="true" />
          Oculto para proteger a las empresas
        </li>
      ) : null}
    </ul>
  );
}
