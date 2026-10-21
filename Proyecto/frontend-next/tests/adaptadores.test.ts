import { describe, expect, it } from "vitest";
import { construirBrechas, construirPanel, contarPorCriticidad } from "@/lib/adaptadores";
import { panelDemo } from "@/lib/demo";
import { nivelDesdePuntaje, normalizarCriticidad } from "@/lib/madurez";
import type { BrechaCatalogoApi, RespuestaApi, ResumenApi } from "@/lib/types";

const resp = (id: number, estado: RespuestaApi["estado_clasificacion"], brecha: number | null, final: RespuestaApi["estado_clasificacion_final"] = null): RespuestaApi => ({
  id_respuesta: id,
  estado_clasificacion: estado,
  estado_clasificacion_final: final,
  fuente_clasificacion: "usuario",
  confianza_clasificacion: null,
  fecha_validacion: null,
  matriz_controles_id_control: id,
  catalogo_brechas_id_brecha: brecha,
});

const catalogo: BrechaCatalogoApi[] = [
  { id_brecha: 1, codigo_brecha: "ERR-DAT-001", categoria: "Protección de Datos", comportamiento_detectado: "x", criticidad: "Alta", accion_sistema: "a", ruta_formativa: { id: 1, nombre: "Protección de Datos - Inicial" } },
  { id_brecha: 2, codigo_brecha: "ERR-GOB-006", categoria: "Gobernanza de IA", comportamiento_detectado: "y", criticidad: "media", accion_sistema: null, ruta_formativa: null },
];

describe("madurez", () => {
  it("usa los mismos cortes que el backend", () => {
    expect(nivelDesdePuntaje(25)).toBe("inicial");
    expect(nivelDesdePuntaje(25.01)).toBe("en_desarrollo");
    expect(nivelDesdePuntaje(50)).toBe("en_desarrollo");
    expect(nivelDesdePuntaje(75)).toBe("gestionado");
    expect(nivelDesdePuntaje(75.5)).toBe("optimizado");
  });

  it("normaliza la criticidad del catálogo", () => {
    expect(normalizarCriticidad("ALTA")).toBe("Alta");
    expect(normalizarCriticidad("Crítica")).toBe("Alta");
    expect(normalizarCriticidad(" media ")).toBe("Media");
    expect(normalizarCriticidad("Baja")).toBe("Baja");
    expect(normalizarCriticidad(null)).toBe("Sin clasificar");
  });
});

describe("construirBrechas", () => {
  it("solo toma no cumplidas y parciales, y el estado final manda sobre el original", () => {
    const brechas = construirBrechas(
      [
        resp(1, "no_cumplido", 1),
        resp(2, "cumplido", 2),
        resp(3, "requiere_revision", 2, "parcialmente_cumplido"), // el LLM la dejó parcial
        resp(4, "no_cumplido", null, "cumplido"),                  // la revisión la dio por cumplida
        resp(5, "no_aplica", null),
      ],
      catalogo,
    );
    expect(brechas.map((b) => b.respuestaId)).toEqual([1, 3]);
    expect(brechas[1]).toMatchObject({ codigo: "ERR-GOB-006", criticidad: "Media", estado: "parcialmente_cumplido" });
  });

  it("no esconde respuestas incumplidas sin brecha de catálogo", () => {
    const [b] = construirBrechas([resp(9, "no_cumplido", null)], catalogo);
    expect(b).toMatchObject({ codigo: "RESP-9", criticidad: "Sin clasificar", dominio: "Sin dominio" });
  });

  it("ordena por criticidad y luego no cumplidas antes que parciales", () => {
    const brechas = construirBrechas(
      [resp(1, "parcialmente_cumplido", 2), resp(2, "parcialmente_cumplido", 1), resp(3, "no_cumplido", 1)],
      catalogo,
    );
    expect(brechas.map((b) => b.respuestaId)).toEqual([3, 2, 1]);
    expect(contarPorCriticidad(brechas)).toEqual({ Alta: 2, Media: 1, Baja: 0, "Sin clasificar": 0 });
  });
});

describe("construirPanel", () => {
  const resumen: ResumenApi = {
    evaluacion_id: 7,
    puntaje_general: 40,
    nivel_madurez_general: "en_desarrollo",
    total_controles_evaluados: 10,
    dominios: [
      { dominio_id: 1, dominio: "Uso Responsable", puntaje: 80, nivel_madurez: "optimizado", total_controles_evaluados: 5 },
      { dominio_id: 2, dominio: "Gestión de Riesgos", puntaje: null, nivel_madurez: null, total_controles_evaluados: 5 },
    ],
  };

  it("funciona sin benchmark (comparativa nula)", () => {
    const p = construirPanel({ resumen, comparativa: null, respuestas: [resp(1, "requiere_revision", null)], catalogo });
    expect(p.tieneBenchmark).toBe(false);
    expect(p.enRevision).toBe(1);
    expect(p.dominios.map((d) => d.nombre)).toEqual(["Gestión de Riesgos", "Uso Responsable"]);
    expect(p.dominios[0]).toMatchObject({ puntaje: 0, nivel: "inicial", promedioIndustria: null, diferencia: null });
  });

  it("calcula la diferencia contra la industria cuando el backend no la trae", () => {
    const p = construirPanel({
      resumen,
      comparativa: {
        evaluacion_id: 7,
        rubro_id: 1,
        comparativas: [{ dominio: "Uso Responsable", tu_puntaje: 80, tu_nivel: null, promedio_industria: 62.5, mediana_industria: null, maximo_industria: null, minimo_industria: null, muestras: 3, diferencia_vs_promedio: null }],
      },
      respuestas: [],
      catalogo,
    });
    expect(p.tieneBenchmark).toBe(true);
    expect(p.dominios.find((d) => d.nombre === "Uso Responsable")?.diferencia).toBe(17.5);
  });

  it("el modo demo produce un panel coherente", () => {
    const p = panelDemo(9101);
    expect(p.dominios).toHaveLength(4);
    expect(p.brechas.length).toBe(Object.values(p.brechasPorCriticidad).reduce((a, b) => a + b, 0));
    expect(p.nivelGeneral).toBe(nivelDesdePuntaje(p.puntajeGeneral));
  });
});
