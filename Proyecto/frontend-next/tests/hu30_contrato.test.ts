/**
 * HU-30 · Vigencia del contrato: lo que el frontend necesita para mostrar la situación cuando
 * el backend corta el servicio pagado (403 CONTRATO_NO_VIGENTE / PLAZO_GRACIA_VENCIDO).
 */
import { describe, expect, it } from "vitest";
import { SIN_SERVICIO } from "@/lib/empresa";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

describe("HU-30 · proxy del cliente", () => {
  it("deja leer la situación del contrato, solo con GET", () => {
    expect(autorizarRutaCliente("GET", ["cliente", "contrato"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["cliente", "contrato"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["cliente", "contrato", "x"]).ok).toBe(false);
  });

  it("reconoce los códigos con que se corta el servicio", () => {
    expect(SIN_SERVICIO.has("CONTRATO_NO_VIGENTE")).toBe(true);
    expect(SIN_SERVICIO.has("PLAZO_GRACIA_VENCIDO")).toBe(true);
    expect(SIN_SERVICIO.has("NO_AUTORIZADO")).toBe(false);
  });
});
