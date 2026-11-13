/**
 * Informe RoPA (lib/informeRopa.ts) y la lista blanca del proxy para sus rutas.
 */
import { describe, expect, it } from "vitest";
import {
  cambiosDatos, correoValido, erroresFormato, faltantes, limpio, telefonoValido, textoFaltantes, textoPartes,
  type DatosRopa,
} from "@/lib/informeRopa";
import { autorizarRutaCliente, TIPO_XLSX } from "@/lib/servidor/proxyCliente";

const VACIO: DatosRopa = {
  direccion: null, correo: null, telefono: null, tiene_dpo: null, dpo_cargo: null, dpo_correo: null,
  mandantes: [{ clave: "grupo sur s.a.", nombre: "Grupo Sur S.A.", direccion: null, correo: null, dpo: null }],
};

const COMPLETO: DatosRopa = {
  direccion: "Av. Apoquindo 4500, Las Condes", correo: "privacidad@andes.cl", telefono: null, tiene_dpo: true,
  dpo_cargo: "Oficial de Protección de Datos", dpo_correo: "dpo@andes.cl",
  mandantes: [{ clave: "grupo sur s.a.", nombre: "Grupo Sur S.A.", direccion: "Av. Libertador 1000", correo: "contacto@gruposur.cl", dpo: null }],
};

describe("lo que falta para generar", () => {
  it("pide los datos de la empresa y, como encargado, los de cada organización", () => {
    const f = faltantes(VACIO, ["responsable", "encargado"]);
    expect(f.filter((x) => x.grupo === "empresa").map((x) => x.campo)).toEqual(["direccion", "correo", "tiene_dpo"]);
    expect(f.filter((x) => x.grupo === "grupo sur s.a.").map((x) => x.campo)).toEqual(["direccion", "correo"]);
    expect(textoFaltantes(f, VACIO)).toBe("Completa los datos de la empresa y Grupo Sur S.A.");
  });

  it("solo como responsable no pide las organizaciones", () => {
    const d = { ...COMPLETO, mandantes: VACIO.mandantes };
    expect(faltantes(d, ["responsable"])).toEqual([]);
    expect(textoFaltantes(faltantes(d, ["encargado"]), d)).toBe("Completa Grupo Sur S.A.");
  });

  it("con delegado pide su cargo y su correo; sin delegado no", () => {
    expect(faltantes({ ...COMPLETO, dpo_correo: " " }, ["responsable"]).map((x) => x.campo)).toEqual(["dpo_correo"]);
    expect(faltantes({ ...COMPLETO, tiene_dpo: false, dpo_cargo: null, dpo_correo: null }, ["responsable"])).toEqual([]);
    expect(faltantes(COMPLETO, ["responsable", "encargado"])).toEqual([]);
  });

  it("revisa el formato de correos y teléfono como el servidor", () => {
    expect(correoValido("privacidad@andes.cl") && correoValido("") && correoValido(null)).toBe(true);
    expect(correoValido("no-es-correo")).toBe(false);
    expect(telefonoValido("+56 2 2345 6789") && telefonoValido(null)).toBe(true);
    expect(telefonoValido("llamar")).toBe(false);
    const malos = erroresFormato({ ...COMPLETO, correo: "x", dpo_cargo: "juan@andes.cl" }, ["responsable"]);
    expect(malos.map((x) => x.campo)).toEqual(["correo", "dpo_cargo"]);
  });
});

describe("guardar solo lo que cambió", () => {
  it("sin cambios no envía nada y normaliza espacios", () => {
    expect(cambiosDatos(COMPLETO, { ...COMPLETO, direccion: "  Av.  Apoquindo 4500,   Las Condes " })).toBeNull();
    expect(limpio("  a   b ")).toBe("a b");
    expect(limpio("   ")).toBeNull();
  });

  it("envía los campos cambiados y las organizaciones modificadas", () => {
    const ahora = {
      ...COMPLETO,
      correo: "otro@andes.cl",
      mandantes: [{ ...COMPLETO.mandantes[0], dpo: "dpo@gruposur.cl" }],
    };
    expect(cambiosDatos(COMPLETO, ahora)).toEqual({
      correo: "otro@andes.cl",
      mandantes: [{ clave: "grupo sur s.a.", direccion: "Av. Libertador 1000", correo: "contacto@gruposur.cl", dpo: "dpo@gruposur.cl" }],
    });
    expect(cambiosDatos(COMPLETO, { ...COMPLETO, tiene_dpo: false })).toEqual({ tiene_dpo: false });
  });

  it("nombra las partes de una emisión", () => {
    expect(textoPartes(["responsable", "encargado"])).toBe("Responsable y encargado");
    expect(textoPartes(["encargado"])).toBe("Encargado");
    expect(textoPartes(["responsable"])).toBe("Responsable");
  });
});

describe("proxy del cliente: informe RoPA", () => {
  const ok = (metodo: string, ruta: string) => autorizarRutaCliente(metodo, ruta.split("/")).ok;

  it("deja pasar solo las rutas del informe RoPA", () => {
    expect(ok("GET", "registro-actividades/ropa")).toBe(true);
    expect(ok("POST", "registro-actividades/ropa")).toBe(true);
    expect(ok("PATCH", "registro-actividades/ropa/datos")).toBe(true);
    expect(ok("GET", "registro-actividades/ropa/datos")).toBe(false);
    expect(ok("DELETE", "registro-actividades/ropa/12")).toBe(false);
    expect(ok("POST", "registro-actividades/ropa/12/descarga")).toBe(false);
  });

  it("la descarga es binaria y admite PDF o Excel", () => {
    const a = autorizarRutaCliente("GET", ["registro-actividades", "ropa", "12", "descarga"]);
    expect(a.ok && a.binario).toBe(true);
    expect(a.ok && a.tipos).toEqual(["application/pdf", TIPO_XLSX]);
  });
});
