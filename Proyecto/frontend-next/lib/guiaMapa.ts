/**
 * Guía para armar el mapa de datos (lógica pura, probada en tests/informe_rat.test.ts): los pasos
 * recomendados, cuáles ya están listos según el mapa actual y qué acción ofrece cada uno.
 */
import { plural, type VistaMapa } from "@/lib/mapaDatos";

export type AccionGuia = "agregar_sistema" | "agregar_tercero" | "agregar_flujo" | "ver_riesgos" | "ir_registro";

export interface PasoGuia {
  id: "internos" | "terceros" | "flujos" | "completar" | "confirmar" | "riesgos" | "rat";
  titulo: string;
  texto: string;
  listo: boolean;
  accion?: { texto: string; tipo: AccionGuia };
}

export function pasosGuia(vista: VistaMapa): PasoGuia[] {
  const r = vista.resumen;
  const hay = vista.elementos.length > 0;
  const internos = r.sistemas + r.bases_datos;
  const aislados = vista.hallazgos.some((h) => h.codigo === "elemento_aislado");
  const faltan = vista.completitud.pendientes.filter((p) => p.faltan.length).length;
  const graves = vista.conteo_hallazgos["Crítica"] + vista.conteo_hallazgos["Alta"];
  return [
    {
      id: "internos", listo: internos > 0,
      titulo: "Registra tus sistemas y bases de datos",
      texto: internos ? `${plural(internos, "registrado", "registrados")}. Agrega los que falten: ERP, CRM, planillas, respaldos…`
        : "Parte por los sistemas donde se capturan datos (ventas, RR. HH., sitio web) y dónde se guardan.",
      accion: { texto: "Agregar sistema", tipo: "agregar_sistema" },
    },
    {
      id: "terceros", listo: r.terceros > 0,
      titulo: "Agrega los terceros que reciben datos",
      texto: r.terceros ? `${plural(r.terceros, "tercero registrado", "terceros registrados")}. Indica su rol y si hay contrato.`
        : "Proveedores, bancos, courier, nube o proveedores de IA que reciben datos de tu empresa.",
      accion: { texto: "Agregar tercero", tipo: "agregar_tercero" },
    },
    {
      id: "flujos", listo: r.flujos > 0 && !aislados,
      titulo: "Conecta todo con flujos",
      texto: r.flujos
        ? aislados ? "Hay elementos sin flujos: conéctalos o confirma que no comparten datos." : `${plural(r.flujos, "flujo", "flujos")} entre tus elementos.`
        : "Un flujo indica qué datos viajan de un elemento a otro y para qué.",
      accion: vista.elementos.length >= 2 ? { texto: "Agregar flujo", tipo: "agregar_flujo" } : undefined,
    },
    {
      id: "completar", listo: hay && faltan === 0,
      titulo: "Completa país, responsables y categorías",
      texto: faltan ? `${plural(faltan, "registro tiene", "registros tienen")} información pendiente. Mejora la precisión de los riesgos.`
        : "Toda la información clave está completa.",
      accion: faltan ? { texto: "Ver qué falta", tipo: "ver_riesgos" } : undefined,
    },
    {
      id: "confirmar", listo: hay && r.pendientes_revision === 0,
      titulo: "Confirma lo que vino de plantillas",
      texto: r.pendientes_revision ? `${plural(r.pendientes_revision, "registro por confirmar", "registros por confirmar")} (borde punteado en el mapa).`
        : "No hay nada por confirmar.",
      accion: r.pendientes_revision ? { texto: "Revisar", tipo: "ver_riesgos" } : undefined,
    },
    {
      id: "riesgos", listo: hay && graves === 0,
      titulo: "Atiende los riesgos críticos y altos",
      texto: graves ? `${plural(graves, "riesgo crítico o alto", "riesgos críticos o altos")} con lo que conviene hacer.`
        : "Sin riesgos críticos ni altos con la información registrada.",
      accion: graves ? { texto: "Ver riesgos", tipo: "ver_riesgos" } : undefined,
    },
    {
      id: "rat", listo: false,
      titulo: "Úsalo en tu registro de actividades",
      texto: "Cada actividad de tratamiento elige del mapa sus sistemas y flujos: no escribes dos veces lo mismo.",
      accion: { texto: "Ir al registro", tipo: "ir_registro" },
    },
  ];
}

/** El primer paso pendiente (sin contar el del registro, que siempre se ofrece). */
export function siguientePaso(pasos: PasoGuia[]): PasoGuia {
  return pasos.find((p) => p.id !== "rat" && !p.listo) ?? pasos[pasos.length - 1];
}
