import { describe, expect, it } from "vitest";
import { construirBrechas, construirPanel } from "@/lib/adaptadores";
import { panelDemo } from "@/lib/demo";
import { brechasACsv, celdaCsv, nombreArchivo } from "@/lib/exportar";
import {
  describirFiltros,
  FILTROS_VACIOS,
  filtrarBrechas,
  filtrosAParams,
  filtrosDesdeParams,
} from "@/lib/filtrosBrechas";
import { calcularSeveridad, MATRIZ_SEVERIDAD } from "@/lib/severidad";
import type { Almacen } from "@/lib/vistasFijadas";
import { fijarVista, leerVistas, MAX_VISTAS, quitarVista } from "@/lib/vistasFijadas";
import type { BrechaCatalogoApi, ControlApi, RespuestaApi } from "@/lib/types";

const resp = (
  id: number,
  estado: RespuestaApi["estado_clasificacion"],
  brecha: number | null,
  control: number | null = id,
  final: RespuestaApi["estado_clasificacion_final"] = null,
): RespuestaApi => ({
  id_respuesta: id,
  estado_clasificacion: estado,
  estado_clasificacion_final: final,
  fuente_clasificacion: "usuario",
  confianza_clasificacion: null,
  fecha_validacion: null,
  matriz_controles_id_control: control,
  catalogo_brechas_id_brecha: brecha,
});

const cat = (id: number, codigo: string, categoria: string, criticidad: string | null): BrechaCatalogoApi => ({
  id_brecha: id,
  codigo_brecha: codigo,
  categoria,
  comportamiento_detectado: `Brecha ${codigo}`,
  criticidad,
  accion_sistema: "Acción",
  ruta_formativa: { id, nombre: `${categoria} - Inicial` },
});

const catalogo = [
  cat(1, "ERR-DAT-001", "Protección de Datos", "Alta"),
  cat(2, "ERR-GOB-006", "Gobernanza de IA", "Media"),
  cat(3, "ERR-RIE-011", "Gestión de Riesgos", "Baja"),
  cat(4, "ERR-SEG-099", "Uso Responsable", "Crítica"),
  cat(5, "ERR-SEG-100", "Uso Responsable", null),
];

describe("HU-11 · criterio 1: análisis automático", () => {
  it("solo genera brechas para no cumplidos y parcialmente cumplidos (estado final manda)", () => {
    const brechas = construirBrechas(
      [
        resp(1, "no_cumplido", 1),
        resp(2, "parcialmente_cumplido", 2),
        resp(3, "cumplido", 3),
        resp(4, "no_aplica", 3),
        resp(5, "requiere_revision", 3), // pendiente de la IA: aún no es brecha
        resp(6, "requiere_revision", 3, 6, "no_cumplido"), // la IA la dejó no cumplida
        resp(7, "no_cumplido", 1, 7, "cumplido"), // la revisión la dio por cumplida
      ],
      catalogo,
    );
    expect(brechas.map((b) => b.respuestaId).sort()).toEqual([1, 2, 6]);
  });

  it("usa el control como respaldo cuando la respuesta no trae brecha de catálogo", () => {
    const controles: ControlApi[] = [
      { id_control: 50, codigo_control: "GOB-007", obligacion: "Inventario de IA", criticidad: "Alta", recomendacion: "Levantar inventario", dominio: { id: 2, nombre_dominio: "Gobernanza de IA" } },
    ];
    const [b] = construirBrechas([resp(9, "no_cumplido", null, 50)], catalogo, controles);
    expect(b).toMatchObject({
      codigo: "GOB-007",
      controlCodigo: "GOB-007",
      dominio: "Gobernanza de IA",
      descripcion: "Inventario de IA",
      accion: "Levantar inventario",
      criticidad: "Alta",
      severidad: "Crítica",
    });
  });

  it("sin impacto conocido queda 'Sin clasificar' y al final, pero no se esconde", () => {
    const brechas = construirBrechas([resp(1, "no_cumplido", 5), resp(2, "parcialmente_cumplido", 3)], catalogo);
    expect(brechas.map((b) => [b.codigo, b.severidad])).toEqual([
      ["ERR-RIE-011", "Baja"],
      ["ERR-SEG-100", "Sin clasificar"],
    ]);
  });
});

describe("HU-11 · criterio 2: orden por severidad", () => {
  it("la matriz impacto × estado produce las cuatro severidades", () => {
    expect(calcularSeveridad("Alta", "no_cumplido").severidad).toBe("Crítica");
    expect(calcularSeveridad("ALTA", "parcialmente_cumplido").severidad).toBe("Alta");
    expect(calcularSeveridad(" media ", "no_cumplido").severidad).toBe("Alta");
    expect(calcularSeveridad("Media", "parcialmente_cumplido").severidad).toBe("Media");
    expect(calcularSeveridad("Baja", "no_cumplido").severidad).toBe("Media");
    expect(calcularSeveridad("Baja", "parcialmente_cumplido").severidad).toBe("Baja");
    expect(Object.keys(MATRIZ_SEVERIDAD)).toEqual(["Alta", "Media", "Baja"]);
  });

  it("respeta 'Crítica' explícita del catálogo y prefiere el catálogo sobre el control", () => {
    expect(calcularSeveridad("Crítica", "parcialmente_cumplido").severidad).toBe("Crítica");
    expect(calcularSeveridad("Baja", "no_cumplido", "Alta").severidad).toBe("Media");
    expect(calcularSeveridad(null, "no_cumplido", "Alta").severidad).toBe("Crítica");
    expect(calcularSeveridad("", "no_cumplido", null).severidad).toBe("Sin clasificar");
  });

  it("ordena Crítica → Alta → Media → Baja y numera la prioridad", () => {
    const brechas = construirBrechas(
      [
        resp(1, "parcialmente_cumplido", 3), // Baja
        resp(2, "parcialmente_cumplido", 2), // Media
        resp(3, "no_cumplido", 2), // Alta
        resp(4, "no_cumplido", 1), // Crítica
      ],
      catalogo,
    );
    expect(brechas.map((b) => b.severidad)).toEqual(["Crítica", "Alta", "Media", "Baja"]);
    expect(brechas.map((b) => b.prioridad)).toEqual([1, 2, 3, 4]);
  });

  it("dentro de la misma severidad: no cumplida antes que parcial, luego mayor impacto, luego dominio menos maduro", () => {
    const puntajes = new Map([
      ["Protección de Datos", 30],
      ["Gobernanza de IA", 70],
    ]);
    const extra = [cat(6, "ERR-GOB-001", "Gobernanza de IA", "Alta")];
    const brechas = construirBrechas(
      [
        resp(1, "parcialmente_cumplido", 1), // Alta (impacto alto, parcial)
        resp(2, "no_cumplido", 2), // Alta (impacto medio, no cumplido)
        resp(3, "no_cumplido", 6), // Crítica en dominio maduro
        resp(4, "no_cumplido", 1), // Crítica en dominio poco maduro
      ],
      [...catalogo, ...extra],
      [],
      puntajes,
    );
    expect(brechas.map((b) => b.respuestaId)).toEqual([4, 3, 2, 1]);
  });

  it("el panel cuenta por severidad, no cumplidos y parciales", () => {
    const p = construirPanel({
      resumen: { evaluacion_id: 1, puntaje_general: 50, nivel_madurez_general: "en_desarrollo", total_controles_evaluados: 4, dominios: [] },
      comparativa: null,
      respuestas: [resp(1, "no_cumplido", 1), resp(2, "parcialmente_cumplido", 1), resp(3, "parcialmente_cumplido", 3)],
      catalogo,
    });
    expect(p.brechasPorSeveridad).toEqual({ Crítica: 1, Alta: 1, Media: 0, Baja: 1, "Sin clasificar": 0 });
    expect([p.noCumplidos, p.parciales]).toEqual([1, 2]);
  });
});

describe("HU-11 · criterio 3: filtros y exportación", () => {
  const panel = panelDemo(9101);

  it("filtra por severidad (varias), dominio, estado y texto sin tildes", () => {
    const criticas = filtrarBrechas(panel.brechas, { ...FILTROS_VACIOS, severidades: ["Crítica"] });
    expect(criticas.length).toBeGreaterThan(0);
    expect(criticas.every((b) => b.severidad === "Crítica")).toBe(true);

    const combo = filtrarBrechas(panel.brechas, {
      severidades: ["Crítica", "Alta"],
      dominio: "Protección de Datos",
      estado: "no_cumplido",
      texto: "",
    });
    expect(combo.every((b) => b.dominio === "Protección de Datos" && b.estado === "no_cumplido")).toBe(true);

    const texto = filtrarBrechas(panel.brechas, { ...FILTROS_VACIOS, texto: "PROTECCION" });
    expect(texto.length).toBeGreaterThan(0);
  });

  it("los filtros van y vuelven de la URL sin perder nada", () => {
    const f = { severidades: ["Alta", "Crítica"] as const, dominio: "Gobernanza de IA", estado: "parcialmente_cumplido" as const, texto: "shadow" };
    const params = filtrosAParams({ ...f, severidades: [...f.severidades] });
    expect(params.severidad).toBe("Alta,Crítica");
    const vuelta = filtrosDesdeParams(new URLSearchParams(params));
    expect(vuelta).toEqual({ severidades: ["Crítica", "Alta"], dominio: "Gobernanza de IA", estado: "parcialmente_cumplido", texto: "shadow" });
    expect(filtrosDesdeParams(new URLSearchParams("severidad=Urgente&estado=x"))).toEqual(FILTROS_VACIOS);
    expect(describirFiltros(vuelta)).toBe("Crítica + Alta · Gobernanza de IA · Parciales · búsqueda “shadow”");
  });

  it("el CSV trae BOM, encabezados, una fila por brecha y neutraliza fórmulas", () => {
    const csv = brechasACsv(panel.brechas.slice(0, 2));
    expect(csv.startsWith("﻿")).toBe(true);
    const lineas = csv.trim().split("\r\n");
    expect(lineas).toHaveLength(3);
    expect(lineas[0]).toContain('"Prioridad";"Severidad"');
    expect(lineas[1].startsWith('"1";"Crítica"')).toBe(true);
    expect(celdaCsv('=HYPERLINK("x")')).toBe('"\'=HYPERLINK(""x"")"');
    expect(celdaCsv(-3)).toBe('"-3"');
  });

  it("nombre de archivo con evaluación y fecha", () => {
    expect(nombreArchivo(9101, new Date(2026, 9, 21))).toBe("brechas_evaluacion-9101_2026-10-21");
  });

  it("fijar en el panel guarda filtros, no duplica, limita y se puede quitar", () => {
    const mem = new Map<string, string>();
    const almacen: Almacen = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => void mem.set(k, v) };
    const criticas = { ...FILTROS_VACIOS, severidades: ["Crítica" as const] };

    expect(fijarVista(9101, criticas, almacen)).toBe(true);
    expect(fijarVista(9101, criticas, almacen)).toBe(true); // misma vista: no duplica
    expect(leerVistas(almacen)).toHaveLength(1);

    for (const d of ["A", "B", "C", "D", "E"]) fijarVista(9101, { ...FILTROS_VACIOS, dominio: d }, almacen);
    const vistas = leerVistas(almacen);
    expect(vistas).toHaveLength(MAX_VISTAS);
    expect(vistas.at(-1)?.filtros.dominio).toBe("E");

    expect(quitarVista(vistas[0].id, almacen)).toBe(true);
    expect(leerVistas(almacen)).toHaveLength(MAX_VISTAS - 1);

    mem.set("complianceai.hu11.vistas-fijadas.v1", "{no es json");
    expect(leerVistas(almacen)).toEqual([]);
    expect(leerVistas(null)).toEqual([]);
  });
});
