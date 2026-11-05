/**
 * HU-22 · Lógica pura de la bandeja de revisión y lista blanca del proxy del panel interno.
 */
import { describe, expect, it } from "vitest";
import {
  cadenaDecision,
  decisionDe,
  errorComentario,
  FILTROS_INICIALES,
  largoComentario,
  queryBandeja,
  siguientePendiente,
  sugerida,
  textoBotonDecision,
  type ItemRespuesta,
} from "@/lib/admin/revision";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";

const item = (extra: Partial<ItemRespuesta> = {}): ItemRespuesta => ({
  tipo_item: "respuesta",
  id: 7,
  evaluacion: { id: 1, origen: "publica", estado_progreso: "completada", cerrada: true, es_prueba: false, empresa: null },
  control: { id: 3, codigo: "DAT-001", pregunta: "¿Existe una política?", criticidad: "Alta", dominio_id: 1, dominio: "Datos" },
  declarado: "cumplido",
  estado_final: "no_cumplido",
  fuente: "llm",
  llm: { clasificacion: "no_cumplido", confianza: 0.92, fecha: "2026-11-02", evidencia_id: 4, bajo_umbral: false },
  motivos: ["divergencia"],
  eventos_seguridad: 0,
  pendiente: true,
  revision: null,
  fecha_referencia: "2026-11-02",
  ...extra,
});

describe("HU-22 · decisión del oficial", () => {
  it("confirmar es dejar la clasificación vigente; corregir es cambiarla", () => {
    const r = item();
    expect(decisionDe(r, "no_cumplido")).toBe("confirmada");
    expect(decisionDe(r, "parcialmente_cumplido")).toBe("corregida");
    expect(decisionDe(r, null)).toBeNull();
  });

  it("el botón dice exactamente qué pasa", () => {
    const r = item();
    expect(textoBotonDecision(r, "no_cumplido")).toBe("Confirmar «No cumplido»");
    expect(textoBotonDecision(r, "cumplido")).toBe("Corregir a «Cumplido»");
    expect(textoBotonDecision(r, null)).toBe("Elige una clasificación");
  });

  it("sugiere la vigente; si está en requiere_revision, la de la IA", () => {
    expect(sugerida(item())).toBe("no_cumplido");
    expect(sugerida(item({ estado_final: "requiere_revision", llm: null }))).toBeNull();
    expect(sugerida(item({ estado_final: "requiere_revision" }))).toBe("no_cumplido");
  });

  it("la cadena marca el quiebre solo cuando la IA no coincide con lo declarado", () => {
    expect(cadenaDecision(item()).quiebre).toBe(true);
    expect(cadenaDecision(item({ declarado: "no_cumplido" })).quiebre).toBe(false);
    expect(cadenaDecision(item({ declarado: "requiere_revision" })).quiebre).toBe(false);
    expect(cadenaDecision(item({ llm: null })).quiebre).toBe(false);
  });

  it("el comentario es obligatorio, como en el backend (10 a 1000 caracteres sin contar espacios repetidos)", () => {
    expect(errorComentario("")).toMatch(/al menos 10/);
    expect(errorComentario("   corto    ")).toMatch(/al menos 10/);
    expect(errorComentario("La evidencia es un borrador.")).toBeNull();
    expect(errorComentario("x".repeat(1001))).toMatch(/hasta 1000/);
    expect(largoComentario("  a   b  ")).toBe(3);
  });

  it("tras resolver, abre el siguiente pendiente (y da la vuelta)", () => {
    const xs = [{ id: 1, pendiente: true }, { id: 2, pendiente: false }, { id: 3, pendiente: true }];
    expect(siguientePendiente(xs, 1)?.id).toBe(3);
    expect(siguientePendiente(xs, 3)?.id).toBe(1);
    expect(siguientePendiente([{ id: 1, pendiente: true }], 1)).toBeNull();
  });
});

describe("HU-22 · filtros y proxy", () => {
  it("la query solo lleva lo elegido y los filtros de clasificaciones no viajan en eventos", () => {
    expect(queryBandeja(FILTROS_INICIALES)).toBe("vista=clasificaciones&estado=pendiente&size=25");
    const q = queryBandeja({ ...FILTROS_INICIALES, motivo: "divergencia", dominio_id: 2, criticidad: "Alta", page: 2 });
    expect(q).toContain("motivo=divergencia");
    expect(q).toContain("dominio_id=2");
    expect(q).toContain("page=2");
    const ev = queryBandeja({ ...FILTROS_INICIALES, vista: "eventos", motivo: "divergencia", evaluacion_id: 9 });
    expect(ev).not.toContain("motivo");
    expect(ev).toContain("evaluacion_id=9");
  });

  it("el proxy deja pasar solo las rutas de la bandeja y sus decisiones", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "revision", "bandeja"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "revision", "resumen"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "revision", "respuestas", "12"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["respuestas", "12", "revision"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["seguridad", "eventos", "5", "revision"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["dominios"]).ok).toBe(true);
    // lo demás sigue cerrado
    expect(autorizarRutaAdmin("PATCH", ["respuestas", "12"]).ok).toBe(false);
    expect(autorizarRutaAdmin("PATCH", ["admin", "revision", "bandeja"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["seguridad", "eventos"]).ok).toBe(false);
  });

  it("el proxy limpia la query: valores válidos pasan y lo inventado se descarta", () => {
    const q = filtrarQueryAdmin(new URLSearchParams(
      "vista=eventos&estado=pendiente&motivo=divergencia&origen=tutor&criticidad=Crítica&orden=reciente&motivo2=x&evaluacion_id=abc"));
    expect(q).toContain("vista=eventos");
    expect(q).toContain("estado=pendiente");
    expect(q).toContain("origen=tutor");
    expect(q).toContain("orden=reciente");
    expect(q).not.toContain("motivo2");
    expect(q).not.toContain("evaluacion_id");
  });
});
