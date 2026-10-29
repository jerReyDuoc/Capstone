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
 * Solo aparece cuando se agota algo (evidencias o validaciones con IA): el saldo diario es una
 * regla interna y no se muestra en la situación normal. `compacto` se mantiene por compatibilidad.
 */
export function BannerLimites({ limites }: { limites: Limites | null; compacto?: boolean }) {
  if (!limites) return null;
  const { evidencias, validacionesIa, servicioIaDisponible } = limites;
  const reinicio = horaDeReinicio(validacionesIa.reiniciaEn);
  const sinIa = !servicioIaDisponible || validacionesIa.restantes === 0;
  const sinEvidencias = evidencias.restantes === 0;

  // Correcciones 29-10: la cuota es una regla de negocio; solo se avisa cuando se agota.
  if (!sinIa && !sinEvidencias) return null;

  return (
    <div className="callout" role="status" style={sinIa || sinEvidencias ? { borderColor: "rgba(242,181,63,.45)", background: "var(--medio-soft)" } : undefined}>
      <Icon name={sinIa || sinEvidencias ? "alerta" : "info"} />
      <div>
        {sinEvidencias ? (
          <p><strong>Llegaste al máximo de evidencias.</strong> Puedes seguir respondiendo sin adjuntar más archivos.</p>
        ) : (
          <p>
            <strong>Validación con IA en pausa por hoy.</strong> Tus respuestas se guardan igual; podrás adjuntar evidencias
            {reinicio ? ` desde las ${reinicio} (hora de Chile)` : " mañana"}.
          </p>
        )}
      </div>
    </div>
  );
}
