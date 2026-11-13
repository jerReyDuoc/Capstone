/**
 * Asistente de registro: lista blanca del proxy del cliente y lógica de presentación pura
 * (etiqueta de la IA, filas de la tarjeta, dependencias, edición y validaciones).
 */
import { describe, expect, it } from "vitest";
import {
  agruparPropuestas, cambios, cantidad, cuotaTexto, dependenciasPendientes, progresoEntrevista, tipoVisual, diccionario, etiquetaIa, explicacionesSueltas, filasPropuesta,
  nombreRef, ordenarPropuestas, tituloTipo, tonoSeveridad, validarDocumento, validarRespuesta, versionGuia,
  CODIGO_PREGUNTA_YA_RESPONDIDA, CODIGO_RESPUESTA_EN_PROCESO, textoEspera,
  type EstadoAsistente, type PropuestaApi,
} from "@/lib/asistente";
import type { CatalogoMapa } from "@/lib/mapaDatos";
import type { CatalogoRat } from "@/lib/registroActividades";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

const ok = (m: string, r: string) => autorizarRutaCliente(m, r.split("/")).ok;

function propuesta(p: Partial<PropuestaApi>): PropuestaApi {
  return {
    id: 1, tipo: "elemento", clave: "crm", estado: "sugerida", origen: "entrevista", area: "clientes", nombre: "CRM",
    payload: { tipo: "sistema", nombre: "CRM" }, payload_final: null, campos_editados: [], explicaciones: {},
    inconsistencias: [], riesgo_nivel: null, confianza: "media",
    ia: { modelo: "openai/gpt-oss-20b", prompt_version: "asistente_rat/1.0.0", traza_id: "t", etiqueta: null },
    entidad_destino: null, entidad_destino_id: null, motivo_descarte: null, documento_id: null,
    fecha_creacion: null, fecha_decision: null, ...p,
  };
}

const refs: EstadoAsistente["referencias"] = {
  elementos: { "id:3": "ERP", "nuevo:crm": "CRM" },
  flujos: { "id:9": "ERP → Banco", "nuevo:envio": "Newsletter" },
};

const catMapa = {
  tipos: [{ codigo: "sistema", nombre: "Sistema o aplicación" }],
  subtipos: { sistema: [{ codigo: "crm", nombre: "CRM o atención de clientes" }], base_datos: [], tercero: [] },
  categorias_datos: [{ codigo: "contacto", nombre: "Datos de contacto" }, { codigo: "salud", nombre: "Salud" }],
  categorias_titulares: [{ codigo: "clientes", nombre: "Clientes" }],
  roles_tercero: [], garantias: [{ codigo: "clausulas_contractuales", nombre: "Cláusulas contractuales tipo" }],
  frecuencias: [], medios: [], paises: [{ codigo: "CL", nombre: "Chile" }, { codigo: "US", nombre: "Estados Unidos" }],
} as unknown as CatalogoMapa;
const catRat = {
  bases_licitud: [{ codigo: "contrato", nombre: "Ejecución de un contrato" }],
  bases_sensibles: [], fuentes: [], unidades_plazo: [{ codigo: "anios", nombre: "años" }],
  inicios_plazo: [{ codigo: "termino_relacion", nombre: "desde que termina la relación o el contrato" }],
  medidas_seguridad: [], roles_empresa: [],
} as unknown as CatalogoRat;

describe("proxy del cliente · asistente", () => {
  it("deja pasar solo las rutas del asistente", () => {
    expect(ok("GET", "asistente")).toBe(true);
    expect(ok("POST", "asistente/sesiones")).toBe(true);
    expect(ok("POST", "asistente/sesiones/4/area")).toBe(true);
    expect(ok("POST", "asistente/sesiones/4/cerrar")).toBe(true);
    expect(ok("POST", "asistente/propuestas/12/aceptar")).toBe(true);
    expect(ok("POST", "asistente/propuestas/12/descartar")).toBe(true);
    expect(ok("DELETE", "asistente/propuestas/12")).toBe(false);
    expect(ok("GET", "asistente/propuestas/x/aceptar")).toBe(false);
  });
  it("da más tiempo a lo que llama al servicio de IA y sube documentos como formulario", () => {
    const r = autorizarRutaCliente("POST", ["asistente", "sesiones", "4", "respuestas"]);
    expect(r.ok && r.timeoutMs).toBe(90_000);
    const d = autorizarRutaCliente("POST", ["asistente", "documentos"]);
    expect(d.ok && d.archivo).toBe(true);
  });
});

describe("etiqueta de la IA", () => {
  it("muestra modelo y versión de la guía en lenguaje simple", () => {
    expect(versionGuia("asistente_rat/1.0.0")).toBe("Guía v1.0.0");
    expect(etiquetaIa(propuesta({}))).toBe("Sugerido por IA · Modelo openai/gpt-oss-20b · Guía v1.0.0");
    expect(etiquetaIa(propuesta({ ia: { modelo: "m", prompt_version: "x/2", traza_id: null, etiqueta: "Del servidor" } })))
      .toBe("Del servidor");
  });
  it("no menciona códigos internos", () => {
    expect(etiquetaIa(propuesta({}))).not.toMatch(/HU-|T-\d|asistente_rat/);
  });
});

describe("tarjeta de la propuesta", () => {
  const dic = diccionario(catMapa, catRat);
  it("traduce códigos del catálogo y referencias a nombres", () => {
    const filas = filasPropuesta(propuesta({
      payload: { tipo: "sistema", subtipo: "crm", pais: "US", categorias_datos: ["contacto", "salud"] },
      explicaciones: { pais: "El proveedor está en Estados Unidos." },
    }), dic, refs);
    const por = Object.fromEntries(filas.map((f) => [f.campo, f]));
    expect(por.subtipo.valor).toBe("CRM o atención de clientes");
    expect(por.pais.valor).toBe("Estados Unidos");
    expect(por.pais.explicacion).toMatch(/Estados Unidos/);
    expect(por.categorias_datos.valor).toBe("Datos de contacto, Salud");
  });
  it("muestra flujos y actividades con sus referencias legibles", () => {
    const flujo = filasPropuesta(propuesta({ tipo: "flujo", payload: { origen: "id:3", destino: "nuevo:crm" } }), dic, refs);
    expect(flujo.map((f) => f.valor)).toEqual(["ERP", "CRM"]);
    const act = filasPropuesta(propuesta({ tipo: "actividad", payload: {
      nombre: "Ventas", base_licitud: "contrato", elementos: ["id:3", "nuevo:otro"],
      plazos: [{ categoria: "contacto", plazo: 5, unidad: "anios", desde: "termino_relacion", fundamento: null },
        { categoria: "salud", plazo: null, unidad: null, desde: null, fundamento: null }],
    } }), dic, refs);
    const por = Object.fromEntries(act.map((f) => [f.campo, f.valor]));
    expect(por.base_licitud).toBe("Ejecución de un contrato");
    expect(por.elementos).toBe("ERP, Propuesta por aceptar");
    expect(por.plazos).toBe("Datos de contacto: 5 años desde que termina la relación o el contrato · Salud: sin plazo");
  });
  it("las explicaciones sin campo visible se muestran aparte", () => {
    const p = propuesta({ explicaciones: { riesgo: "Sube por datos de salud.", pais: "x" }, payload: { tipo: "sistema", pais: "CL" } });
    expect(explicacionesSueltas(p, filasPropuesta(p, dic, refs)).map(([k]) => k)).toEqual(["riesgo"]);
  });
  it("títulos y tonos", () => {
    expect(tituloTipo(propuesta({ payload: { tipo: "tercero" } }))).toBe("Tercero");
    expect(tituloTipo(propuesta({ tipo: "actividad" }))).toBe("Actividad del registro");
    expect(tonoSeveridad("Crítica")).toBe("tone-alto");
    expect(tonoSeveridad("Medio")).toBe("tone-medio");
    expect(nombreRef("id:77", refs, "elementos")).toBe("Ya no está en el mapa");
  });
});

describe("revisión en orden", () => {
  it("los flujos y actividades esperan a los elementos que usan", () => {
    const crm = propuesta({ id: 1 });
    const flujo = propuesta({ id: 2, tipo: "flujo", clave: "envio", payload: { origen: "nuevo:crm", destino: "id:3" } });
    const act = propuesta({ id: 3, tipo: "actividad", clave: "ventas", payload: { flujos: ["nuevo:envio"] } });
    expect(dependenciasPendientes(flujo, [crm, flujo, act]).map((x) => x.id)).toEqual([1]);
    expect(dependenciasPendientes(flujo, [{ ...crm, estado: "aceptada" }, flujo]).length).toBe(0);
    expect(ordenarPropuestas([act, flujo, crm]).map((x) => x.id)).toEqual([1, 2, 3]);
  });
});

describe("edición y validaciones", () => {
  it("envía solo lo que cambió", () => {
    expect(cambios({ nombre: "CRM", pais: null, categorias_datos: ["contacto"] },
      { nombre: "CRM", pais: "CL", categorias_datos: ["contacto"] })).toEqual({ pais: "CL" });
  });
  it("valida la respuesta y el documento", () => {
    expect(validarRespuesta("   ", 100)).toMatch(/Saltar pregunta/);
    expect(validarRespuesta("x".repeat(101), 100)).toMatch(/100/);
    expect(validarRespuesta("Usamos un CRM", 100)).toBeNull();
    expect(validarDocumento({ name: "lista.xlsx", size: 10 }, 5)).toMatch(/PDF/);
    expect(validarDocumento({ name: "politica.pdf", size: 6 * 1024 * 1024 }, 5)).toMatch(/5 MB/);
    expect(validarDocumento({ name: "politica.pdf", size: 1000 }, 5)).toBeNull();
  });
  it("explica la cuota y el modo sin ayuda automática", () => {
    const base = { ia: { habilitada: true, cuota: { reinicia_en: "", respuestas: { usados: 2, limite: 60, restantes: 58 },
      documentos: { usados: 0, limite: 10, restantes: 10 } } } } as EstadoAsistente;
    expect(cuotaTexto(base)).toBe("Te quedan 58 de 60 respuestas con ayuda automática hoy.");
    expect(cuotaTexto({ ia: { ...base.ia, habilitada: false } })).toMatch(/a mano/);
    expect(cuotaTexto({ ia: { ...base.ia, cuota: { ...base.ia.cuota, respuestas: { usados: 60, limite: 60, restantes: 0 } } } }))
      .toMatch(/Puedes seguir a mano/);
  });
});

describe("diseño de la pantalla", () => {
  it("identidad visual por tipo", () => {
    expect(tipoVisual(propuesta({ payload: { tipo: "tercero" } }))).toBe("tercero");
    expect(tipoVisual(propuesta({ payload: {} }))).toBe("sistema");
    expect(tipoVisual(propuesta({ tipo: "flujo" }))).toBe("flujo");
  });
  it("progreso de la entrevista", () => {
    const areas = [
      { codigo: "personas", nombre: "", descripcion: "", preguntas: 3, completada: true },
      { codigo: "clientes", nombre: "", descripcion: "", preguntas: 3, completada: false },
      { codigo: "ti", nombre: "", descripcion: "", preguntas: 2, completada: false },
    ] as EstadoAsistente["areas"];
    expect(progresoEntrevista({ areas, area_actual: "clientes", paso: 1, terminada: false })).toEqual({ hechas: 4, total: 8 });
    expect(progresoEntrevista({ areas, area_actual: "ti", paso: 0, terminada: true })).toEqual({ hechas: 8, total: 8 });
  });
  it("agrupa en orden de revisión y sin grupos vacíos", () => {
    const g = agruparPropuestas([propuesta({ id: 2, tipo: "actividad" }), propuesta({ id: 1 })]);
    expect(g.map((x) => x.tipo)).toEqual(["elemento", "actividad"]);
    expect(cantidad(1, "flujo", "flujos")).toBe("1 flujo");
    expect(cantidad(3, "flujo", "flujos")).toBe("3 flujos");
  });
});

describe("espera mientras la ayuda automática analiza", () => {
  it("explica la espera según los segundos y nunca promete más de un minuto", () => {
    expect(textoEspera(0)).toBe("Analizando tu respuesta…");
    expect(textoEspera(12)).toMatch(/Sigo analizando/);
    expect(textoEspera(30)).toMatch(/hasta un minuto/);
    expect(textoEspera(65)).toMatch(/reintentar o guardar tu respuesta sin ayuda/);
  });
  it("los códigos de respuesta en curso son los del servidor", () => {
    expect(CODIGO_RESPUESTA_EN_PROCESO).toBe("RESPUESTA_EN_PROCESO");
    expect(CODIGO_PREGUNTA_YA_RESPONDIDA).toBe("PREGUNTA_YA_RESPONDIDA");
  });
});
