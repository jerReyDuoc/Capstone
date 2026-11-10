/**
 * HU-32 · Derechos ARCOP en la página web: listas blancas de los tres proxies, filtros del
 * admin y reglas de presentación (qué botones se muestran, plazos, código de seguimiento).
 */
import { describe, expect, it } from "vitest";
import {
  DERECHOS, ESTADOS, ESTADOS_ARCOP, FILTROS_ADMIN_INICIALES, TIPOS_ARCOP,
  accionesAdmin, accionesTitular, errorTexto, exportable, nombreDesdeDisposicion, normalizarCodigo,
  pasoActual, puedeProrrogar, queryAdmin, siguientePasoAdmin, textoEvento, textoPlazo, titularDe,
  type DetalleArcop, type EstadoArcop,
} from "@/lib/arcop";
import { autorizarRuta, filtrarQuery } from "@/lib/servidor/proxy";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

const AHORA = new Date("2026-11-10T15:00:00Z");

function detalle(parcial: Partial<DetalleArcop> = {}): DetalleArcop {
  return {
    id_solicitud: 1, codigo_seguimiento: "ARC-AB12-CD34", tipo: "acceso", estado: "recibida",
    usuario_temporal_id: null, evaluacion_id: 7, usuario_definitivo_id: null,
    fecha_creacion: "2026-11-01T12:00:00", fecha_actualizacion: null, fecha_cierre: null,
    fecha_limite_respuesta: "2026-12-01T12:00:00", fecha_limite_informacion: null, plazo_vencido: false,
    fecha_prorroga: null, descripcion: "Quiero ver mis datos.", respuesta: null,
    transiciones_posibles: ["en_revision", "rechazada", "cancelada"], historial: [], ...parcial,
  };
}

/* ------------------------------------------------------------------ proxies */
describe("HU-32 · proxy del usuario temporal (/bff/api)", () => {
  it("deja pasar sus solicitudes y la descarga de datos como binario JSON/CSV", () => {
    expect(autorizarRuta("GET", ["arcop", "solicitudes"], 7).ok).toBe(true);
    expect(autorizarRuta("POST", ["arcop", "solicitudes", "3", "informacion"], 7).ok).toBe(true);
    const exp = autorizarRuta("GET", ["arcop", "solicitudes", "3", "exportacion"], 7);
    expect(exp.ok && exp.binario).toBe(true);
    expect(exp.ok && exp.tipos).toEqual(["application/json", "text/csv"]);
    // el informe PDF sigue siendo solo PDF (sin lista de tipos)
    const pdf = autorizarRuta("GET", ["evaluaciones", "7", "informe", "pdf"], 7);
    expect(pdf.ok && pdf.binario && pdf.tipos).toBeUndefined();
  });

  it("no deja gestionar como admin ni exportar con POST", () => {
    expect(autorizarRuta("PATCH", ["arcop", "solicitudes", "3", "estado"], 7).ok).toBe(false);
    expect(autorizarRuta("POST", ["arcop", "solicitudes", "3", "resolucion"], 7).ok).toBe(false);
    expect(autorizarRuta("POST", ["arcop", "solicitudes", "3", "exportacion"], 7).ok).toBe(false);
  });

  it("el formato de la exportación pasa por el filtro de la query", () => {
    expect(filtrarQuery(new URLSearchParams("formato=csv&x=1"))).toBe("?formato=csv");
  });
});

describe("HU-32 · proxy del usuario definitivo (/bff/cliente/api)", () => {
  it("deja ejercer los derechos y descargar los datos", () => {
    for (const [m, ruta] of [
      ["GET", ["arcop", "catalogo"]],
      ["GET", ["arcop", "solicitudes"]],
      ["GET", ["arcop", "solicitudes", "9"]],
      ["POST", ["arcop", "solicitudes"]],
      ["POST", ["arcop", "solicitudes", "9", "cancelacion"]],
      ["POST", ["arcop", "solicitudes", "9", "informacion"]],
    ] as const) {
      expect(autorizarRutaCliente(m, [...ruta]).ok, ruta.join("/")).toBe(true);
    }
    const exp = autorizarRutaCliente("GET", ["arcop", "solicitudes", "9", "exportacion"]);
    expect(exp.ok && exp.binario).toBe(true);
    expect(exp.ok && exp.tipos).toEqual(["application/json", "text/csv"]);
  });

  it("no deja hacer lo del admin", () => {
    expect(autorizarRutaCliente("PATCH", ["arcop", "solicitudes", "9", "estado"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["arcop", "solicitudes", "9", "prorroga"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["arcop", "solicitudes", "9", "resolucion"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["arcop", "solicitudes", "..", "x"]).ok).toBe(false);
  });
});

describe("HU-32 · proxy del admin (/bff/admin/api)", () => {
  it("deja gestionar las solicitudes", () => {
    expect(autorizarRutaAdmin("GET", ["arcop", "solicitudes"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["arcop", "solicitudes", "4"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["arcop", "solicitudes", "4", "estado"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["arcop", "solicitudes", "4", "prorroga"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["arcop", "solicitudes", "4", "resolucion"]).ok).toBe(true);
  });

  it("no actúa por el titular (crear, cancelar, aportar o descargar sus datos)", () => {
    expect(autorizarRutaAdmin("POST", ["arcop", "solicitudes"]).ok).toBe(false);
    expect(autorizarRutaAdmin("POST", ["arcop", "solicitudes", "4", "cancelacion"]).ok).toBe(false);
    expect(autorizarRutaAdmin("POST", ["arcop", "solicitudes", "4", "informacion"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["arcop", "solicitudes", "4", "exportacion"]).ok).toBe(false);
  });

  it("filtra estado, tipo, vencidas y evaluación; descarta valores desconocidos", () => {
    const q = new URLSearchParams("estado=pendiente_informacion&tipo=supresion&vencidas=true&evaluacion_id=12&page=2&size=20");
    expect(filtrarQueryAdmin(q)).toBe("?estado=pendiente_informacion&tipo=supresion&vencidas=true&evaluacion_id=12&page=2&size=20");
    expect(filtrarQueryAdmin(new URLSearchParams("tipo=borrar&vencidas=si"))).toBe("");
    // los estados de las otras bandejas siguen pasando
    expect(filtrarQueryAdmin(new URLSearchParams("estado=nueva"))).toBe("?estado=nueva");
  });

  it("la query que arma la bandeja pasa entera por el filtro", () => {
    const f = { ...FILTROS_ADMIN_INICIALES, estado: "en_proceso" as const, tipo: "acceso" as const, vencidas: true, evaluacion_id: 5 };
    const q = queryAdmin(f);
    expect(filtrarQueryAdmin(new URLSearchParams(q))).toBe(`?${q}`);
    expect(queryAdmin(FILTROS_ADMIN_INICIALES)).toBe("page=1&size=20");
  });
});

/* ------------------------------------------------------------------ textos y reglas */
describe("HU-32 · los seis derechos y los siete estados", () => {
  it("tienen texto en lenguaje claro", () => {
    expect(TIPOS_ARCOP).toHaveLength(6);
    for (const t of TIPOS_ARCOP) {
      expect(DERECHOS[t].accion.length).toBeGreaterThan(5);
      expect(DERECHOS[t].ejemplo.length).toBeGreaterThanOrEqual(10); // el mínimo del backend
    }
    for (const e of ESTADOS_ARCOP) expect(ESTADOS[e].etiqueta).toBeTruthy();
  });

  it("solo acceso y portabilidad se descargan", () => {
    expect(TIPOS_ARCOP.filter(exportable)).toEqual(["acceso", "portabilidad"]);
  });

  it("el progreso tiene 4 hitos", () => {
    const pasos = (["recibida", "en_revision", "pendiente_informacion", "en_proceso", "resuelta", "cancelada"] as EstadoArcop[]).map(pasoActual);
    expect(pasos).toEqual([0, 1, 1, 2, 3, 3]);
  });

  it("valida el texto como el backend", () => {
    expect(errorTexto("   ", 10, 50)).toMatch(/obligatorio/);
    expect(errorTexto("corto", 10, 50)).toMatch(/faltan 5/);
    expect(errorTexto("x".repeat(51), 10, 50)).toMatch(/superar/);
    expect(errorTexto("suficientemente largo", 10, 50)).toBeNull();
  });
});

describe("HU-32 · acciones que se ofrecen", () => {
  it("titular: cancelar mientras se puede, responder si le piden información, descargar si está resuelta", () => {
    expect(accionesTitular(detalle())).toEqual({ cancelar: true, aportar: false, descargar: false });
    expect(accionesTitular(detalle({ estado: "pendiente_informacion", transiciones_posibles: ["en_revision", "rechazada", "cancelada"] })).aportar).toBe(true);
    expect(accionesTitular(detalle({ estado: "resuelta", transiciones_posibles: [] }))).toEqual({ cancelar: false, aportar: false, descargar: true });
    expect(accionesTitular(detalle({ tipo: "rectificacion", estado: "resuelta", transiciones_posibles: [] })).descargar).toBe(false);
  });

  it("admin: solo lo que permite el backend, con el siguiente paso sugerido", () => {
    const d = detalle({ estado: "en_proceso", transiciones_posibles: ["resuelta", "rechazada"] });
    expect(accionesAdmin(d, AHORA)).toEqual(["resolver", "rechazar", "prorrogar"]);
    expect(siguientePasoAdmin(d)).toBe("resolver");
    expect(accionesAdmin(detalle({ estado: "resuelta", transiciones_posibles: [] }), AHORA)).toEqual([]);
  });

  it("la prórroga es única, antes del vencimiento y nunca para el bloqueo", () => {
    expect(puedeProrrogar(detalle(), AHORA)).toBe(true);
    expect(puedeProrrogar(detalle({ fecha_prorroga: "2026-11-05T10:00:00" }), AHORA)).toBe(false);
    expect(puedeProrrogar(detalle({ tipo: "bloqueo" }), AHORA)).toBe(false);
    expect(puedeProrrogar(detalle({ fecha_limite_respuesta: "2026-11-01T00:00:00" }), AHORA)).toBe(false);
  });
});

describe("HU-32 · plazos, titular e historial", () => {
  it("describe el plazo según cuánto falta", () => {
    expect(textoPlazo(detalle(), AHORA)?.tono).toBe("info");
    expect(textoPlazo(detalle({ fecha_limite_respuesta: "2026-11-13T12:00:00" }), AHORA)?.tono).toBe("medio");
    const vencido = textoPlazo(detalle({ fecha_limite_respuesta: "2026-11-08T12:00:00", plazo_vencido: true }), AHORA);
    expect(vencido?.tono).toBe("alto");
    expect(vencido?.texto).toMatch(/vencido hace 2 días/);
    expect(textoPlazo(detalle({ estado: "resuelta", fecha_cierre: "2026-11-09T12:00:00" }), AHORA)?.texto).toMatch(/^Cerrada/);
  });

  it("nombra al titular para el admin", () => {
    expect(titularDe(detalle())).toMatch(/evaluación N\.º 7/);
    expect(titularDe(detalle({ evaluacion_id: null, usuario_definitivo_id: 3 }))).toMatch(/empresa cliente/);
  });

  it("habla en segunda persona al titular", () => {
    const e = { id_evento: 1, fecha: "", tipo_evento: "creada", estado_anterior: null, estado_nuevo: "recibida", actor_rol: "encuestado", actor_id: null, comentario: null };
    expect(textoEvento(e, true)).toBe("Enviaste la solicitud");
    expect(textoEvento(e, false)).toBe("El titular envió la solicitud");
    expect(textoEvento({ ...e, tipo_evento: "cambio_estado", estado_nuevo: "pendiente_informacion", actor_rol: "admin_therion" }, true))
      .toBe("Te pidieron más información");
  });
});

describe("HU-32 · código de seguimiento y descarga", () => {
  it("normaliza igual que el backend", () => {
    expect(normalizarCodigo("arc ab12 cd34")).toBe("ARC-AB12-CD34");
    expect(normalizarCodigo("AB12CD34")).toBe("ARC-AB12-CD34");
    expect(normalizarCodigo("ARC-AB1O-CDl4")).toBe("ARC-AB10-CD14"); // O→0, l→1
    expect(normalizarCodigo("ARC-ABCD")).toBe("");
    expect(normalizarCodigo("ARC-UUUU-UUUU")).toBe(""); // U no está en el alfabeto
  });

  it("toma el nombre del archivo solo si es seguro", () => {
    expect(nombreDesdeDisposicion('attachment; filename="mis-datos-ARC-AB12-CD34.json"', "x")).toBe("mis-datos-ARC-AB12-CD34.json");
    expect(nombreDesdeDisposicion('attachment; filename="../../etc"', "x")).toBe("x");
    expect(nombreDesdeDisposicion(null, "mis-datos.csv")).toBe("mis-datos.csv");
  });
});
