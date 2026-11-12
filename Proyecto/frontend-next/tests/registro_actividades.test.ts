/**
 * Registro de actividades de tratamiento: lógica pura (lib/registroActividades.ts), el aviso del
 * mapa cuando un cambio afecta actividades y la lista blanca del proxy del cliente.
 */
import { describe, expect, it } from "vitest";
import { textoCambioMapa, type CatalogoMapa, type ElementoMapa, type FlujoMapa } from "@/lib/mapaDatos";
import {
  alinearPlazos, aplicarPlazoATodas, cambiosContenido, contenidoVacio, ETIQUETA_ACCION_ESTADO, ETIQUETA_ESTADO,
  filtrarActividades, pendientesPorPaso, seleccionInicial, textoVersion, vistaPreviaDesdeMapa,
  type Actividad, type Completitud,
} from "@/lib/registroActividades";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

const CODIGO_INTERNO = /\b(?:HU|T)-\d{2}\b|\bRAT-\d/;

function elemento(id: number, tipo: ElementoMapa["tipo"], nombre: string, extra: Partial<ElementoMapa> = {}): ElementoMapa {
  const pais = extra.pais ?? (tipo === "tercero" ? null : "CL");
  return {
    id, tipo, nombre, subtipo: null, descripcion: null, proveedor: null, pais, responsable: null,
    categorias_datos: [], categorias_titulares: [], nna_declarado: false, incluye_nna: false, rol_tercero: null,
    contrato_firmado: null, origen: "manual", clave: null, pendiente_revision: false, fecha_creacion: null,
    fecha_actualizacion: null,
    derivados: { sensibles: [], incluye_nna: false, fuera_de_chile: Boolean(pais && pais !== "CL"), pais_efectivo: pais, flujos_entrantes: 0, flujos_salientes: 0 },
    ...extra,
  };
}

function flujo(id: number, o: number, d: number, extra: Partial<FlujoMapa> = {}, der: Partial<FlujoMapa["derivados"]> = {}): FlujoMapa {
  return {
    id, origen_id: o, destino_id: d, finalidad: null, categorias_datos: [], categorias_titulares: [], nna_declarado: false,
    incluye_nna: false, frecuencia: null, medio: null, cifrado: null, garantia: null, origen: "manual", clave: null,
    pendiente_revision: false, fecha_creacion: null, fecha_actualizacion: null,
    derivados: { internacional: false, pais_origen: "CL", pais_destino: "CL", hacia_tercero: false, desde_tercero: false, sensibles: [], incluye_nna: false, garantia_valida: false, ...der },
    ...extra,
  };
}

const CATALOGO = {
  categorias_datos: [
    { codigo: "salud", nombre: "Salud", grupo: "Datos sensibles", descripcion: "", ejemplos: [], sensible: true },
    { codigo: "identificacion", nombre: "Identificación", grupo: "", descripcion: "", ejemplos: [], sensible: false },
    { codigo: "financieros", nombre: "Financieros", grupo: "", descripcion: "", ejemplos: [], sensible: false },
    { codigo: "contacto", nombre: "Contacto", grupo: "", descripcion: "", ejemplos: [], sensible: false },
  ],
  categorias_titulares: [
    { codigo: "trabajadores", nombre: "Trabajadores", descripcion: "", nna: false, posible_nna: false },
    { codigo: "nna", nombre: "Niños, niñas y adolescentes", descripcion: "", nna: true, posible_nna: false },
  ],
} as unknown as CatalogoMapa;

const MAPA = {
  elementos: [
    elemento(1, "sistema", "Remuneraciones", { categorias_datos: ["identificacion", "financieros", "salud"], categorias_titulares: ["trabajadores"] }),
    elemento(2, "tercero", "Banco", { pais: "CL", categorias_datos: ["identificacion", "financieros"], categorias_titulares: ["trabajadores"] }),
    elemento(3, "tercero", "Nube", { pais: "US", categorias_datos: ["contacto"], categorias_titulares: ["trabajadores"] }),
  ],
  flujos: [
    flujo(10, 1, 2, { categorias_datos: ["identificacion", "financieros"], categorias_titulares: ["trabajadores"] }),
    flujo(11, 1, 3, { categorias_datos: ["contacto"], categorias_titulares: ["trabajadores"] }, { internacional: true, pais_destino: "US", garantia_valida: false }),
  ],
};

function actividad(id: number, nombre: string, extra: Partial<Actividad> = {}): Actividad {
  return {
    id, nombre, estado: "borrador", estado_nombre: "Borrador", estado_previo: null, revision: 1, version_vigente: null,
    editable: true, acciones: ["enviar_revision", "archivar"],
    completitud: { porcentaje: 0, completos: 0, total: 13, faltantes: [], puede_quedar_vigente: false },
    motivos_revision: [], area: null, fecha_creacion: null, fecha_actualizacion: null, fecha_vigencia: null, fecha_archivo: null,
    resumen: { tipos_datos: 0, hay_sensibles: false, incluye_nna: false, sistemas: 0, terceros: 0, transferencias: 0, paises: [], base_licitud: null, rol: null, finalidades: 0 },
    ...extra,
  };
}

describe("vista previa de lo que la actividad toma del mapa", () => {
  it("suma datos, titulares, países y terceros con el subconjunto elegido", () => {
    const p = vistaPreviaDesdeMapa({
      elementos: [{ id: 1, categorias_datos: ["identificacion", "salud"], categorias_titulares: ["trabajadores"] }],
      flujos: [seleccionInicial(MAPA.flujos[0])],
    }, MAPA, CATALOGO);
    expect(p.tiposDatos[0]).toBe("salud");                  // los sensibles primero
    expect(new Set(p.tiposDatos)).toEqual(new Set(["salud", "identificacion", "financieros"]));
    expect(p.haySensibles).toBe(true);
    expect(p.terceros).toEqual(["Banco"]);
    expect(p.bases).toEqual(["Remuneraciones"]);
    expect(p.paises).toEqual(["CL"]);
    expect(p.transferencias).toEqual([]);
  });

  it("detecta transferencias internacionales y lo que ya no está en el mapa", () => {
    const p = vistaPreviaDesdeMapa({ elementos: [{ id: 99, categorias_datos: [], categorias_titulares: [] }], flujos: [seleccionInicial(MAPA.flujos[1])] }, MAPA, CATALOGO);
    expect(p.transferencias).toEqual([{ flujo: 11, nombre: "Remuneraciones → Nube", pais: "US", garantiaValida: false }]);
    expect(p.paises).toEqual(["CL", "US"]);
    expect(p.noEncontrados).toEqual([99]);
  });

  it("ignora categorías que el mapa ya no registra", () => {
    const p = vistaPreviaDesdeMapa({ elementos: [{ id: 2, categorias_datos: ["salud", "financieros"], categorias_titulares: ["nna"] }], flujos: [] }, MAPA, CATALOGO);
    expect(p.tiposDatos).toEqual(["financieros"]);
    expect(p.incluyeNna).toBe(false);
  });
});

describe("cambios del formulario", () => {
  it("solo envía lo que cambió y trata los textos vacíos como sin valor", () => {
    const guardado = { ...contenidoVacio("Pagos"), descripcion: null, finalidades: ["Pagar sueldos"] };
    expect(cambiosContenido(guardado, { ...guardado, descripcion: "  " })).toEqual({});
    expect(cambiosContenido(guardado, { ...guardado, nombre: " Pagos " })).toEqual({});
    const c = cambiosContenido(guardado, { ...guardado, finalidades: ["Pagar sueldos", "Emitir certificados"], rol: "responsable" });
    expect(Object.keys(c).sort()).toEqual(["finalidades", "rol"]);
  });

  it("alinea los plazos con las categorías y copia un plazo a todas", () => {
    const plazos = alinearPlazos([{ categoria: "salud", plazo: 5, unidad: "anios", desde: null, fundamento: null },
      { categoria: "vieja", plazo: 1, unidad: "dias", desde: null, fundamento: null }], ["salud", "contacto"]);
    expect(plazos.map((p) => p.categoria)).toEqual(["salud", "contacto"]);
    expect(plazos[1].plazo).toBeNull();
    expect(aplicarPlazoATodas(plazos, plazos[0]).every((p) => p.plazo === 5 && p.unidad === "anios")).toBe(true);
  });

  it("agrupa lo pendiente por paso", () => {
    const c: Completitud = {
      porcentaje: 50, completos: 6, total: 13, puede_quedar_vigente: false,
      faltantes: [{ codigo: "fuentes", titulo: "Fuentes", paso: 3, mensaje: "x" }, { codigo: "base_licitud", titulo: "Base", paso: 3, mensaje: "y" },
        { codigo: "medidas", titulo: "Medidas", paso: 6, mensaje: "z" }],
    };
    expect(pendientesPorPaso(c)).toEqual({ 3: 2, 6: 1 });
  });
});

describe("lista del registro", () => {
  const lista = [
    actividad(1, "Ventas en línea", { area: "Comercial" }),
    actividad(2, "Pago de remuneraciones", { estado: "en_revision", motivos_revision: [{ fecha: "", texto: "Cambió el banco", version_mapa: 4 }] }),
    actividad(3, "Selección de personal", { estado: "archivada" }),
    actividad(4, "Atención de reclamos", { estado: "vigente", version_vigente: 2 }),
  ];
  it("filtra por estado (sin archivadas por defecto), busca y pone primero lo que hay que revisar", () => {
    expect(filtrarActividades(lista, "activas", "").map((a) => a.id)).toEqual([2, 4, 1]);
    expect(filtrarActividades(lista, "archivada", "").map((a) => a.id)).toEqual([3]);
    expect(filtrarActividades(lista, "activas", "comer").map((a) => a.id)).toEqual([1]);
  });
  it("describe la versión en lenguaje simple", () => {
    expect(textoVersion({ estado: "vigente", version_vigente: 2 })).toBe("Versión 2 vigente");
    expect(textoVersion({ estado: "borrador", version_vigente: null })).toBe("Aún sin versión vigente");
    expect(textoVersion({ estado: "en_revision", version_vigente: 3 })).toContain("Sigue valiendo la versión 3");
  });
  it("los textos visibles no muestran códigos internos", () => {
    const textos = [...Object.values(ETIQUETA_ESTADO), ...Object.values(ETIQUETA_ACCION_ESTADO), textoVersion(lista[1])];
    for (const t of textos) expect(CODIGO_INTERNO.test(t)).toBe(false);
  });
});

describe("aviso del mapa", () => {
  it("suma las actividades afectadas solo cuando las hay", () => {
    expect(textoCambioMapa("Se editó el tercero «Banco».", 0)).toBe("Se editó el tercero «Banco».");
    expect(textoCambioMapa("Se editó el tercero «Banco».", 1)).toContain("1 actividad usa lo que cambiaste");
    expect(textoCambioMapa("Cambios.", 3)).toContain("3 actividades usan lo que cambiaste");
  });
});

describe("proxy del cliente", () => {
  it("permite solo las rutas del registro de actividades que existen", () => {
    expect(autorizarRutaCliente("GET", ["registro-actividades"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["registro-actividades", "catalogo"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["registro-actividades", "actividades"]).ok).toBe(true);
    expect(autorizarRutaCliente("PATCH", ["registro-actividades", "actividades", "12"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["registro-actividades", "actividades", "12", "estado"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["registro-actividades", "actividades", "12", "versiones", "3"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["registro-actividades", "actividades", "12"]).ok).toBe(false);
    expect(autorizarRutaCliente("PATCH", ["registro-actividades", "actividades", "abc"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["registro-actividades", "actividades", "12", "versiones", "3"]).ok).toBe(false);
  });
});
