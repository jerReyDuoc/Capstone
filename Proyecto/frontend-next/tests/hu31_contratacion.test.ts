/**
 * HU-31 · "Contratar la plataforma": lógica pura del formulario, contratos con el backend,
 * lista blanca del BFF y estados de la bandeja del admin.
 */
import { describe, expect, it } from "vitest";
import {
  ACCIONES_SOLICITUD,
  ETIQUETA_ESTADO_SOLICITUD,
  seleccionable,
  type EstadoSolicitud,
  type Solicitud,
} from "@/lib/admin/api";
import {
  campoDelError,
  cuerpoSolicitud,
  FORMULARIO_VACIO,
  parseConsentimientos,
  parseSolicitud,
  primerError,
  validarFormulario,
  type Consentimientos,
  type FormularioContratacion,
} from "@/lib/contratacion";
import { parseErrorBackend } from "@/lib/encuesta/contratos";
import { mensajeDeError } from "@/lib/encuesta/errores";
import { autorizarRuta, cuerpoRespuestaEsDeLaSesion } from "@/lib/servidor/proxy";
import { filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";

const TEXTOS: Consentimientos = {
  contacto: { clave: "contacto", titulo: "Contacto comercial", texto: "Autorizo el contacto…", version: "2026-10-v1" },
  migracion: { clave: "migracion", titulo: "Asociar mi evaluación", texto: "Autorizo asociar…", version: "2026-10-v2" },
};

const LLENO: FormularioContratacion = {
  nombre: "  Ana   Pérez ",
  cargo: "Gerenta de Cumplimiento",
  empresa: "ACME SpA",
  email: " Ana.Perez@ACME.cl ",
  telefono: "",
  aceptaContacto: true,
  aceptaMigracion: true,
};

describe("HU-31 C1 · formulario: nombre, cargo, empresa, correo y teléfono opcional", () => {
  it("un formulario completo sin teléfono es válido", () => {
    expect(validarFormulario(LLENO)).toEqual({});
  });

  it("vacío: marca todo lo obligatorio, pero no el teléfono, en el orden visual", () => {
    const errores = validarFormulario(FORMULARIO_VACIO);
    expect(Object.keys(errores)).toEqual(["nombre", "cargo", "empresa", "email", "aceptaContacto", "aceptaMigracion"]);
    expect(errores.telefono).toBeUndefined();
    expect(primerError(errores)).toBe("nombre");
  });

  it("formatos: correo, teléfono y largos (iguales al backend)", () => {
    expect(validarFormulario({ ...LLENO, email: "ana@" }).email).toContain("nombre@empresa.cl");
    expect(validarFormulario({ ...LLENO, telefono: "llámame" }).telefono).toContain("+56 9 1234 5678");
    expect(validarFormulario({ ...LLENO, telefono: "+56 9 1234 5678" })).toEqual({});
    expect(validarFormulario({ ...LLENO, cargo: "x".repeat(81) }).cargo).toContain("80");
    expect(validarFormulario({ ...LLENO, empresa: "A" }).empresa).toBeTruthy();
  });

  it("el cuerpo limpia espacios, normaliza el correo y manda null si no hay teléfono", () => {
    const cuerpo = cuerpoSolicitud(12, LLENO, TEXTOS, "tok");
    expect(cuerpo).toMatchObject({
      evaluacion_id: 12,
      nombre: "Ana Pérez",
      email: "ana.perez@acme.cl",
      telefono: null,
      captcha_token: "tok",
    });
  });
});

describe("HU-31 C2 · dos consentimientos separados, cada uno con su versión", () => {
  it("sin cualquiera de los dos no se puede enviar", () => {
    expect(validarFormulario({ ...LLENO, aceptaContacto: false })).toMatchObject({ aceptaContacto: expect.any(String) });
    expect(validarFormulario({ ...LLENO, aceptaMigracion: false })).toMatchObject({ aceptaMigracion: expect.any(String) });
  });

  it("cada uno viaja con la versión del texto que se mostró", () => {
    const cuerpo = cuerpoSolicitud(12, LLENO, TEXTOS, "tok");
    expect(cuerpo.consentimiento_contacto).toEqual({ version: "2026-10-v1", aceptado: true });
    expect(cuerpo.consentimiento_migracion).toEqual({ version: "2026-10-v2", aceptado: true });
  });

  it("parsea los textos del backend y rechaza respuestas incompletas", () => {
    const datos = {
      contacto: { clave: "contacto", titulo: "Contacto comercial", texto: "a", version: "v1" },
      migracion: { clave: "migracion", titulo: "Asociar", texto: "b", version: "v2" },
    };
    expect(parseConsentimientos(datos)?.migracion.version).toBe("v2");
    expect(parseConsentimientos({ contacto: datos.contacto })).toBeNull();
    expect(parseConsentimientos({ version: "v1", texto: "formato viejo de HU-27" })).toBeNull();
  });

  it("los errores del backend apuntan al consentimiento o campo correcto", () => {
    const e = parseErrorBackend(409, {
      detail: { codigo: "CONSENTIMIENTO_DESACTUALIZADO", mensaje: "x", consentimiento: "migracion", version_vigente: "v3" },
    });
    expect(e).toMatchObject({ consentimiento: "migracion", versionVigente: "v3" });
    expect(campoDelError(e.codigo, e.campo, e.consentimiento)).toBe("aceptaMigracion");
    const t = parseErrorBackend(422, { detail: { codigo: "DATOS_INVALIDOS", mensaje: "x", campo: "telefono" } });
    expect(campoDelError(t.codigo, t.campo)).toBe("telefono");
    expect(campoDelError("EMAIL_INVALIDO")).toBe("email");
    // un campo inventado no se marca
    const raro = parseErrorBackend(422, { detail: { codigo: "DATOS_INVALIDOS", mensaje: "x", campo: "<script>" } });
    expect(raro.campo).toBeUndefined();
  });

  it("los códigos nuevos tienen un mensaje propio para la persona", () => {
    for (const codigo of ["SOLICITUD_EXISTENTE", "CONSENTIMIENTO_DESACTUALIZADO", "LIMITE_SOLICITUDES"]) {
      expect(mensajeDeError({ codigo, mensaje: "" }).titulo).not.toBe("Algo salió mal");
    }
    // límites y CAPTCHA reutilizan los de la encuesta pública (HU-19)
    expect(mensajeDeError({ codigo: "DEMASIADOS_INTENTOS", mensaje: "", reintentarEnS: 90 })).toMatchObject({
      accion: "esperar",
      esperaS: 90,
    });
  });
});

describe("HU-31 · estado de la solicitud del encuestado", () => {
  it("parsea la respuesta pública y rechaza estados desconocidos", () => {
    expect(parseSolicitud({ id: 3, evaluacion_id: 12, estado: "nueva", fecha_creacion: "2026-10-27" })).toEqual({
      id: 3,
      evaluacionId: 12,
      estado: "nueva",
      fechaCreacion: "2026-10-27",
    });
    expect(parseSolicitud({ id: 3, evaluacion_id: 12, estado: "migrada" })).toBeNull(); // el backend la muestra como contratada
    expect(parseSolicitud({ id: "3", evaluacion_id: 12, estado: "nueva" })).toBeNull();
  });
});

describe("HU-31 · BFF del encuestado", () => {
  it("permite solo lo que usa el formulario y solo para su evaluación", () => {
    expect(autorizarRuta("GET", ["contratacion", "consentimiento"], 12).ok).toBe(true);
    expect(autorizarRuta("GET", ["contratacion", "evaluaciones", "12", "solicitud"], 12).ok).toBe(true);
    expect(autorizarRuta("GET", ["contratacion", "evaluaciones", "13", "solicitud"], 12).ok).toBe(false);
    expect(autorizarRuta("POST", ["contratacion", "solicitudes"], 12)).toMatchObject({
      ok: true,
      conIp: true,
      cuerpoConEvaluacion: true,
    });
    expect(autorizarRuta("GET", ["contratacion", "solicitudes"], 12).ok).toBe(false);
    expect(autorizarRuta("PATCH", ["contratacion", "solicitudes", "1"], 12).ok).toBe(false);
    expect(autorizarRuta("GET", ["admin", "contrataciones"], 12).ok).toBe(false);
  });

  it("el cuerpo de la solicitud debe ser de la evaluación de la sesión", () => {
    expect(cuerpoRespuestaEsDeLaSesion(cuerpoSolicitud(12, LLENO, TEXTOS, "t"), 12)).toBe(true);
    expect(cuerpoRespuestaEsDeLaSesion(cuerpoSolicitud(13, LLENO, TEXTOS, "t"), 12)).toBe(false);
    // POST /respuestas sigue con su control
    expect(autorizarRuta("POST", ["respuestas"], 12)).toMatchObject({ ok: true, cuerpoConEvaluacion: true });
  });
});

describe("HU-31 C3 · bandeja del admin: nueva, contactada, contratada o descartada", () => {
  it("cada estado tiene etiqueta y sus acciones espejan las transiciones del backend", () => {
    const estados: EstadoSolicitud[] = ["nueva", "contactada", "contratada", "migrada", "descartada"];
    for (const e of estados) expect(ETIQUETA_ESTADO_SOLICITUD[e].texto).toBeTruthy();
    const destinos = (e: EstadoSolicitud) => ACCIONES_SOLICITUD[e].map((a) => a.estado);
    expect(destinos("nueva")).toEqual(["contactada", "contratada", "descartada"]);
    expect(destinos("contactada")).toEqual(["contratada", "descartada"]);
    expect(destinos("contratada")).toEqual(["contactada", "descartada"]);
    expect(destinos("migrada")).toEqual([]);
    expect(destinos("descartada")).toEqual([]);
  });

  it("el filtro por estado acepta los nuevos y ya no 'pendiente'", () => {
    expect(filtrarQueryAdmin(new URLSearchParams("estado=contactada"))).toBe("?estado=contactada");
    expect(filtrarQueryAdmin(new URLSearchParams("estado=nueva"))).toBe("?estado=nueva");
    expect(filtrarQueryAdmin(new URLSearchParams("estado=pendiente"))).toBe("");
  });

  it("solo una contratada (no contactada) se puede elegir para el alta de HU-27", () => {
    const base = {
      id: 1, estado: "contratada", autoriza_migracion: true, empresa_id: null, fecha_creacion: "2026-10-27",
      contacto: { nombre: "Ana", cargo: "Gerenta", email: "a@b.cl", telefono: null }, razon_social_declarada: "ACME",
      evaluacion: { id: 9, completada: true },
    } as Solicitud;
    expect(seleccionable(base)).toBe(true);
    expect(seleccionable({ ...base, estado: "contactada" })).toBe(false);
    expect(seleccionable({ ...base, estado: "nueva" })).toBe(false);
  });
});
