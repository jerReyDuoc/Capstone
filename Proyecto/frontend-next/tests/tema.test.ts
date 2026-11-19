/**
 * Corrección 18-11 · Selector de tema (claro · oscuro · azul): qué se guarda, qué se lee y el script que lo pone
 * antes de pintar (su hash va en la CSP de las páginas con nonce).
 */
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  claveTemaUsuario, CLAVE_TEMA, esTema, guardarTema, HASH_SCRIPT_TEMA, leerTema, SCRIPT_TEMA, TEMA_POR_DEFECTO, TEMAS, temaSiguiente,
} from "@/lib/tema";

const almacen = (inicial: Record<string, string> = {}) => {
  const datos = new Map(Object.entries(inicial));
  return {
    datos,
    getItem: (k: string) => datos.get(k) ?? null,
    setItem: (k: string, v: string) => void datos.set(k, v),
  };
};

describe("tema", () => {
  it("ofrece los tres temas y el oscuro es el de siempre", () => {
    expect(TEMAS.map((t) => t.id)).toEqual(["light", "dark", "blue"]);
    expect(TEMA_POR_DEFECTO).toBe("dark");
    expect(esTema("blue")).toBe(true);
    expect(esTema("rosado")).toBe(false);
  });

  it("lee el de la cuenta, si no el del navegador, si no el oscuro (y nunca un valor inválido)", () => {
    expect(leerTema(almacen())).toBe("dark");
    expect(leerTema(almacen({ [CLAVE_TEMA]: "light" }), 5)).toBe("light");
    expect(leerTema(almacen({ [CLAVE_TEMA]: "light", [claveTemaUsuario(5)]: "blue" }), 5)).toBe("blue");
    expect(leerTema(almacen({ [CLAVE_TEMA]: "light", [claveTemaUsuario(5)]: "blue" }), 6)).toBe("light");
    expect(leerTema(almacen({ [CLAVE_TEMA]: "<script>" }))).toBe("dark");
    expect(leerTema(null)).toBe("dark");
  });

  it("guarda por cuenta y como último del navegador", () => {
    const a = almacen();
    guardarTema(a, "blue", 5);
    expect(Object.fromEntries(a.datos)).toEqual({ tema: "blue", "tema:5": "blue" });
    guardarTema(a, "light");
    expect(a.datos.get("tema")).toBe("light");
    expect(a.datos.get("tema:5")).toBe("blue");
  });

  it("el script del <head> pone solo temas válidos y no falla sin almacenamiento", () => {
    const correr = (valor: string | null, falla = false) => {
      const html = { dataset: {} as Record<string, string> };
      const localStorage = { getItem: () => { if (falla) throw new Error("bloqueado"); return valor; } };
      new Function("localStorage", "document", SCRIPT_TEMA)(localStorage, { documentElement: html });
      return html.dataset.theme;
    };
    expect(correr("blue")).toBe("blue");
    expect(correr("x")).toBeUndefined();
    expect(correr(null, true)).toBeUndefined();
  });

  it("el botón único de pantallas angostas recorre los tres temas en orden", () => {
    expect(temaSiguiente("light")).toBe("dark");
    expect(temaSiguiente("dark")).toBe("blue");
    expect(temaSiguiente("blue")).toBe("light");
  });

  it("el hash de la CSP corresponde al script (si cambias el script, actualiza HASH_SCRIPT_TEMA)", () => {
    const h = `sha256-${createHash("sha256").update(SCRIPT_TEMA, "utf8").digest("base64")}`;
    expect(HASH_SCRIPT_TEMA).toBe(h);
  });
});
