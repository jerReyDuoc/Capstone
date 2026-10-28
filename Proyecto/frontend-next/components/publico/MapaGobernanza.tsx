/**
 * Portada · "Mapa de gobernanza": ilustración topográfica del resultado del autodiagnóstico.
 *
 * Cada cima es un dominio y su número de curvas de nivel es su madurez (datos de ejemplo).
 * Server Component sin estado: las curvas se calculan una vez al compilar la página
 * (force-static) con una fórmula determinista, así el SVG es siempre el mismo y no pesa
 * JavaScript en el navegador. La única animación es el trazado de las curvas al cargar
 * (se desactiva con prefers-reduced-motion).
 */
import type { CSSProperties } from "react";
import m from "./mapa.module.css";

/** Orden de trazado de cada curva (escalona la animación en CSS). */
const orden = (n: number) => ({ "--i": n }) as CSSProperties;

const ANCHO = 1200;
const ALTO = 560;

interface Cima {
  nombre: string;
  puntaje: number;
  x: number;
  y: number;
  radio: number;
  fase: number;
  /** Desplazamiento de la etiqueta respecto de la cima. */
  etiqueta: { dx: number; dy: number; ancla: "start" | "end" | "middle" };
  brecha?: boolean;
}

// Valores de ejemplo, coherentes con el radar que mostraba antes la portada.
const CIMAS: Cima[] = [
  { nombre: "Protección de Datos", puntaje: 72, x: 270, y: 300, radio: 190, fase: 0.4, etiqueta: { dx: 0, dy: -44, ancla: "middle" } },
  { nombre: "Gobernanza de IA", puntaje: 58, x: 590, y: 215, radio: 165, fase: 1.9, etiqueta: { dx: 0, dy: -40, ancla: "middle" } },
  { nombre: "Gestión de Riesgos", puntaje: 41, x: 820, y: 385, radio: 130, fase: 3.1, etiqueta: { dx: 0, dy: 62, ancla: "middle" }, brecha: true },
  { nombre: "Uso Responsable", puntaje: 64, x: 1010, y: 210, radio: 150, fase: 4.6, etiqueta: { dx: 0, dy: -42, ancla: "middle" } },
];

type Punto = [number, number];

const f = (n: number) => n.toFixed(1);

/** Curva cerrada suave por los puntos (Catmull-Rom convertida a Bézier cúbica). */
function curvaCerrada(p: Punto[]): string {
  const n = p.length;
  let d = `M${f(p[0][0])},${f(p[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = p[(i - 1 + n) % n], p1 = p[i], p2 = p[(i + 1) % n], p3 = p[(i + 2) % n];
    const c1: Punto = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Punto = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${f(c1[0])},${f(c1[1])} ${f(c2[0])},${f(c2[1])} ${f(p2[0])},${f(p2[1])}`;
  }
  return `${d}Z`;
}

/** Curvas de nivel de una cima: más madurez, más curvas (una cada 10 puntos). */
function curvasDe(c: Cima): string[] {
  const niveles = Math.max(3, Math.round(c.puntaje / 10));
  const curvas: string[] = [];
  for (let k = 0; k < niveles; k++) {
    const r = c.radio * (1 - k / (niveles + 0.7));
    // La cima se inclina un poco hacia el noreste a medida que sube (relieve asimétrico)
    const cx = c.x + k * 6;
    const cy = c.y - k * 4;
    const puntos: Punto[] = [];
    for (let i = 0; i < 48; i++) {
      const t = (i / 48) * Math.PI * 2;
      const deformacion =
        1 + 0.13 * Math.sin(2 * t + c.fase + k * 0.25) + 0.07 * Math.sin(3 * t + 2 * c.fase) + 0.035 * Math.sin(5 * t + 3 * c.fase - k * 0.4);
      puntos.push([cx + Math.cos(t) * r * deformacion, cy + Math.sin(t) * r * deformacion * 0.62]);
    }
    curvas.push(curvaCerrada(puntos));
  }
  return curvas;
}

/** Líneas de terreno de fondo (abiertas), que se apagan bajo las cimas. */
function lineasDeFondo(): string[] {
  const lineas: string[] = [];
  for (let i = 0; i < 11; i++) {
    const base = 30 + i * 50;
    let d = "";
    for (let x = -20; x <= ANCHO + 20; x += 30) {
      const y = base + 14 * Math.sin(x / 150 + i * 0.9) + 7 * Math.sin(x / 61 + i * 1.7);
      d += `${d ? "L" : "M"}${f(x)},${f(y)}`;
    }
    lineas.push(d);
  }
  return lineas;
}

const CURVAS = CIMAS.map(curvasDe);
const FONDO = lineasDeFondo();

// Ruta del autodiagnóstico: del inicio a cada cima y al diagnóstico final
const RUTA =
  "M40,520 C140,500 180,420 270,300 S470,250 590,215 S760,330 820,385 S930,260 1010,210 S1150,170 1170,120";

// La franja superior del lienzo es solo terreno de fondo: se recorta para que la lámina no
// tenga un espacio vacío arriba.
const RECORTE_Y = 70;

export function MapaGobernanza() {
  let i = 0; // orden de trazado, para escalonar la animación
  return (
    <figure className={m.lamina} aria-labelledby="lamina-titulo">
      <div className={m.franja}>
        {/* figcaption debe ser hijo directo de figure: el título va como párrafo y se enlaza con aria-labelledby */}
        <p id="lamina-titulo" className={m.titulo}>Ejemplo de resultado: una organización ficticia del rubro servicios</p>
        <ul className={m.simbolos} aria-label="Cómo leer el mapa">
          <li><svg viewBox="0 0 14 14" aria-hidden="true"><path d="M1 12 7 2l6 10Z" className={m.hito} /></svg>Cada cima es un dominio</li>
          <li><svg viewBox="0 0 20 14" aria-hidden="true"><path d="M1 4q9-4 18 0M1 9q9-4 18 0" className={m.simboloCurva} /></svg>Cada curva suma 10 puntos de madurez</li>
          <li><svg viewBox="0 0 14 14" aria-hidden="true"><path d="M1 12 7 2l6 10Z" className={m.hitoBrecha} /></svg>Brecha prioritaria</li>
        </ul>
      </div>

      <svg className={m.mapa} viewBox={`0 ${RECORTE_Y} ${ANCHO} ${ALTO - RECORTE_Y}`} aria-hidden="true" focusable="false">
        <defs>
          <mask id="mapa-sin-cimas">
            <rect width={ANCHO} height={ALTO} fill="white" />
            {CIMAS.map((c) => (
              <ellipse key={c.nombre} cx={c.x} cy={c.y} rx={c.radio * 1.12} ry={c.radio * 0.72} fill="black" />
            ))}
          </mask>
        </defs>

        <g className={m.fondo} mask="url(#mapa-sin-cimas)">
          {FONDO.map((d, k) => (
            <path key={k} d={d} pathLength={1} className={m.curva} style={orden(k)} />
          ))}
        </g>

        {CIMAS.map((c, ci) => (
          <g key={c.nombre} className={c.brecha ? m.cimaBrecha : m.cima}>
            {CURVAS[ci].map((d, k) => (
              <path
                key={k}
                d={d}
                pathLength={1}
                className={`${m.curva} ${k === CURVAS[ci].length - 1 ? m.curvaAlta : ""}`}
                style={orden(6 + i++)}
              />
            ))}
          </g>
        ))}

        <path d={RUTA} className={m.ruta} />

        <g className={m.etiquetas}>
          {CIMAS.map((c, ci) => {
            const tope = CURVAS[ci].length - 1;
            const tx = c.x + tope * 6;
            const ty = c.y - tope * 4;
            return (
              <g key={c.nombre}>
                <path d={`M${tx - 7},${ty + 5} L${tx},${ty - 7} L${tx + 7},${ty + 5} Z`} className={c.brecha ? m.hitoBrecha : m.hito} />
                <text x={tx + c.etiqueta.dx} y={ty + c.etiqueta.dy} textAnchor={c.etiqueta.ancla} className={m.nombre}>
                  {c.nombre}
                </text>
                <text x={tx + c.etiqueta.dx} y={ty + c.etiqueta.dy + 22} textAnchor={c.etiqueta.ancla} className={m.cota}>
                  {c.brecha ? `${c.puntaje} de 100, brecha prioritaria` : `${c.puntaje} de 100`}
                </text>
              </g>
            );
          })}
          <circle cx={40} cy={520} r={6} className={m.hito} />
          <text x={58} y={526} className={m.cota}>Tu punto de partida</text>
          <circle cx={1170} cy={120} r={6} className={m.hito} />
          <text x={1160} y={104} textAnchor="end" className={m.cota}>Tu diagnóstico</text>
        </g>
      </svg>

      {/* En pantallas angostas las etiquetas del mapa serían ilegibles: se listan aquí */}
      <ul className={m.leyendaMovil}>
        {CIMAS.map((c) => (
          <li key={c.nombre} data-brecha={c.brecha ? "si" : undefined}>
            <span>{c.nombre}</span>
            <span>{c.puntaje} de 100</span>
          </li>
        ))}
      </ul>

      <div className={m.escala} aria-hidden="true">
        <span>Madurez</span>
        <span className={m.regla}>
          {[0, 25, 50, 75, 100].map((v) => <span key={v}>{v}</span>)}
        </span>
      </div>
    </figure>
  );
}

