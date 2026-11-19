/**
 * Mejoras 19-11 · Genera el favicon y los íconos de la app desde el logo de TherionLabs.
 *
 *   npm run iconos                          # usa public/marca/therionlabs-logo.(svg|png)
 *   npm run iconos -- ruta/a/otro-logo.png  # o un archivo cualquiera
 *
 * Si no encuentra el logo, usa la marca hexagonal provisional (app/icon.svg).
 *
 * Crea (convención de archivos de Next.js: los <link> del <head> se agregan solos):
 *   app/favicon.ico      16 × 16 y 32 × 32 (pestaña del navegador, navegadores antiguos)
 *   app/icon1.png        16 × 16
 *   app/icon2.png        32 × 32
 *   app/icon3.png        512 × 512 (Android, accesos directos)
 *   app/apple-icon.png   180 × 180 (iPhone/iPad, con fondo: iOS no admite transparencia)
 *   app/icon.svg         solo si el logo es SVG (escala a cualquier tamaño)
 *
 * Usa `sharp`, que ya viene instalado con Next.js (no agrega dependencias).
 */
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const app = join(raiz, "app");
const FONDO_APPLE = "#050807"; // --bg del tema oscuro

const candidatos = [
  process.argv[2] && resolve(process.cwd(), process.argv[2]),
  join(raiz, "public", "marca", "therionlabs-logo.svg"),
  join(raiz, "public", "marca", "therionlabs-logo.png"),
  join(app, "icon.svg"),
].filter(Boolean);
const origen = candidatos.find((r) => existsSync(r));
if (!origen) {
  console.error("No encontré el logo. Ponlo en public/marca/therionlabs-logo.svg o .png");
  process.exit(1);
}
const esSvg = extname(origen).toLowerCase() === ".svg";
const datos = readFileSync(origen);
console.log(`Logo: ${origen}${origen.endsWith(join("app", "icon.svg")) ? " (provisional)" : ""}`);

const png = (lado, fondo) =>
  sharp(datos, esSvg ? { density: Math.max(72, Math.ceil((72 * lado) / 40)) } : {})
    .resize(lado, lado, { fit: "contain", background: fondo ?? { r: 0, g: 0, b: 0, alpha: 0 } })
    .flatten(fondo ? { background: fondo } : false)
    .png({ compressionLevel: 9 })
    .toBuffer();

/** .ico con imágenes PNG adentro (válido desde Windows Vista y en todos los navegadores actuales). */
function ico(imagenes) {
  const cabecera = Buffer.alloc(6 + 16 * imagenes.length);
  cabecera.writeUInt16LE(0, 0);
  cabecera.writeUInt16LE(1, 2); // tipo: ícono
  cabecera.writeUInt16LE(imagenes.length, 4);
  let desplazamiento = cabecera.length;
  imagenes.forEach(({ lado, buffer }, i) => {
    const e = 6 + 16 * i;
    cabecera.writeUInt8(lado >= 256 ? 0 : lado, e);
    cabecera.writeUInt8(lado >= 256 ? 0 : lado, e + 1);
    cabecera.writeUInt8(0, e + 2); // sin paleta
    cabecera.writeUInt8(0, e + 3);
    cabecera.writeUInt16LE(1, e + 4); // planos
    cabecera.writeUInt16LE(32, e + 6); // bits por píxel
    cabecera.writeUInt32LE(buffer.length, e + 8);
    cabecera.writeUInt32LE(desplazamiento, e + 12);
    desplazamiento += buffer.length;
  });
  return Buffer.concat([cabecera, ...imagenes.map((x) => x.buffer)]);
}

const [p16, p32, p512, apple] = await Promise.all([png(16), png(32), png(512), png(180, FONDO_APPLE)]);
writeFileSync(join(app, "favicon.ico"), ico([{ lado: 16, buffer: p16 }, { lado: 32, buffer: p32 }]));
writeFileSync(join(app, "icon1.png"), p16);
writeFileSync(join(app, "icon2.png"), p32);
writeFileSync(join(app, "icon3.png"), p512);
writeFileSync(join(app, "apple-icon.png"), apple);

const svgApp = join(app, "icon.svg");
if (esSvg && origen !== svgApp) writeFileSync(svgApp, datos);
else if (!esSvg && existsSync(svgApp)) rmSync(svgApp); // el SVG provisional ya no corresponde al logo

console.log("Listo: app/favicon.ico, app/icon1.png (16), app/icon2.png (32), app/icon3.png (512), app/apple-icon.png (180)");
