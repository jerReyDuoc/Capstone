/**
 * Auditoría UX 16-11 · Fase 1: ninguna pantalla puede ser más ancha que el viewport a 390 × 844.
 *
 * Falla si document.documentElement.scrollWidth > window.innerWidth en cualquiera de las rutas de
 * las cuatro áreas (público, encuestado, cliente y admin). Además informa qué elementos son los
 * que se salen, para encontrar el culpable sin abrir el navegador.
 */
import { expect, test } from "@playwright/test";
import { iniciarSesion, simular, type Rol } from "./simulacion";

export const RUTAS: [Rol, string, string][] = [
  // [rol, ruta, nombre]
  ["anonimo", "/", "portada"],
  ["anonimo", "/retomar", "retomar"],
  ["anonimo", "/ingresar", "ingresar"],
  ["encuestado", "/encuesta", "cuestionario"],
  ["cliente", "/panel", "diagnostico"],
  ["cliente", "/panel/brechas", "brechas"],
  ["cliente", "/panel/capacitacion", "capacitacion"],
  ["cliente", "/panel/dominios", "dominios"],
  ["cliente", "/panel/sector", "sector"],
  ["cliente", "/panel/informe", "informe"],
  ["cliente", "/panel/remediacion", "cerrar-brechas"],
  ["cliente", "/empresa", "mi-empresa"],
  ["cliente", "/empresa/evaluaciones", "mis-evaluaciones"],
  ["cliente", "/empresa/documentos", "mis-documentos"],
  ["cliente", "/empresa/borradores", "borradores"],
  ["cliente", "/empresa/mapa-datos", "mapa-datos"],
  ["cliente", "/empresa/registro-actividades", "registro-actividades"],
  ["cliente", "/empresa/mis-derechos", "mis-derechos"],
  ["admin", "/admin/clientes", "admin-empresas"],
  ["admin", "/admin/matriz", "admin-matriz"],
  ["admin", "/admin/revision", "admin-revision"],
  ["admin", "/admin/arcop", "admin-arcop"],
  ["admin", "/admin/retencion", "admin-retencion"],
  ["admin", "/admin/privacidad", "admin-privacidad"],
];

for (const [rol, ruta, nombre] of RUTAS) {
  test(`sin desborde horizontal a 390 px · ${nombre}`, async ({ page, context, baseURL }) => {
    await iniciarSesion(context, rol, baseURL!);
    await simular(page, rol);
    await page.goto(ruta, { waitUntil: "networkidle" });
    // Espera a que termine la carga (sin esqueletos) antes de medir
    await page.waitForFunction(() => !document.querySelector(".skeleton, [aria-busy='true']"), null, { timeout: 15_000 }).catch(() => undefined);
    await page.waitForTimeout(600);

    const medida = await page.evaluate(() => {
      const ancho = window.innerWidth;
      const culpables = [...document.querySelectorAll<HTMLElement>("body *")]
        .filter((el) => {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.right <= ancho + 1) return false;
          // Ignora lo que está dentro de un contenedor con desplazamiento propio
          for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
            const ox = getComputedStyle(p).overflowX;
            if (ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") return false;
          }
          return true;
        })
        .slice(0, 5)
        .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")} (${Math.round(el.getBoundingClientRect().right)} px)`);
      return { scroll: document.documentElement.scrollWidth, ancho, culpables };
    });

    expect(medida.scroll, `Se sale del ancho: ${medida.culpables.join(" · ")}`).toBeLessThanOrEqual(medida.ancho);
  });
}
