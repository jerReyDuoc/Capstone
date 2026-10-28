"use client";

/**
 * HU-19 · Cuota diaria de validaciones con IA y evidencias restantes.
 * Informativo: si falla la consulta, no se muestra nada y el flujo sigue.
 * El cuestionario debe llamar a `refrescar()` (useLimitesEncuesta) tras subir evidencias
 * y mostrar <AvisoError> cuando reciba CUOTA_LLM_AGOTADA / LIMITE_EVIDENCIAS.
 */
import type { Limites } from "@/lib/encuesta/contratos";
import { horaDeReinicio } from "@/lib/encuesta/errores";
import { Icon } from "@/components/ui/Icon";

/**
 * `compacto`: en la situación normal (quedan validaciones y evidencias) se muestra como una
 * línea de texto pequeña en vez de un aviso, para no robar altura al cuestionario. Cuando se
 * agota algo, siempre se muestra el aviso completo.
 */
export function BannerLimites({ limites, compacto = false }: { limites: Limites | null; compacto?: boolean }) {
  if (!limites) return null;
  const { evidencias, validacionesIa, servicioIaDisponible } = limites;
  const reinicio = horaDeReinicio(validacionesIa.reiniciaEn);
  const sinIa = !servicioIaDisponible || validacionesIa.restantes === 0;
  const sinEvidencias = evidencias.restantes === 0;

  if (compacto && !sinIa && !sinEvidencias) {
    return (
      <p className="card-sub" role="status" style={{ margin: 0, display: "inline-flex", alignItems: "center", gap: 6 }}>
        <Icon name="info" style={{ width: 16, height: 16, flex: "none" }} />
        <span>
          Hoy te quedan <strong>{validacionesIa.restantes ?? "∞"}</strong> validaciones con IA y{" "}
          <strong>{evidencias.restantes}</strong> evidencias.
        </span>
      </p>
    );
  }

  return (
    <div className="callout" role="status" style={sinIa || sinEvidencias ? { borderColor: "rgba(242,181,63,.45)", background: "var(--medio-soft)" } : undefined}>
      <Icon name={sinIa || sinEvidencias ? "alerta" : "info"} />
      <div>
        {sinEvidencias ? (
          <p><strong>Llegaste al máximo de evidencias.</strong> Puedes seguir respondiendo sin adjuntar más archivos.</p>
        ) : sinIa ? (
          <p>
            <strong>Validación con IA en pausa por hoy.</strong> Tus respuestas se guardan igual; podrás adjuntar evidencias
            {reinicio ? ` desde las ${reinicio} (hora de Chile)` : " mañana"}.
          </p>
        ) : (
          <p>
            Hoy te quedan <strong>{validacionesIa.restantes ?? "∞"}</strong> validaciones con IA y{" "}
            <strong>{evidencias.restantes}</strong> evidencias para esta evaluación.
          </p>
        )}
      </div>
    </div>
  );
}
