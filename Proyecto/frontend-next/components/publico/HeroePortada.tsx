/**
 * Portada (/) · Héroe centrado (correcciones 29-10; reemplaza el mapa topográfico).
 *
 * Server Component sin estado ni JavaScript propio: la portada sigue siendo force-static.
 *  - Texto centrado: insignia, titular, bajada, botones y garantías.
 *  - Correcciones 05-11: se quitó la vista previa con el resultado de ejemplo; el héroe queda
 *    solo con el texto y, detrás, las ondas en el verde de marca, que ahora se mueven como
 *    oleaje (solo CSS: cada línea se desplaza en bucle a su propia velocidad y sube y baja
 *    levemente). Son decorativas (aria-hidden) y quedan fijas con "reducir movimiento".
 *  - Al deslizar, el texto se desvanece con una animación ligada al scroll
 *    (animation-timeline, solo CSS). Sin soporte o con "reducir movimiento", queda fijo.
 */
import Link from "next/link";
import type { CSSProperties } from "react";
import { Icon } from "@/components/ui/Icon";
import s from "./heroe.module.css";

const ANCHO = 1440;
const LINEAS = 7;

/**
 * Ondas del fondo, calculadas al compilar (no hay JS en el cliente). Cada línea es la suma de
 * senos con un número ENTERO de ciclos en ANCHO y se dibuja dos veces seguidas (0 → 2·ANCHO):
 * así, al desplazarla exactamente ANCHO hacia la izquierda, el bucle no tiene salto.
 */
function ondas(): string[] {
  const lineas: string[] = [];
  const w = (2 * Math.PI) / ANCHO;
  for (let k = 0; k < LINEAS; k++) {
    const puntos: string[] = [];
    for (let x = 0; x <= ANCHO * 2; x += 12) {
      const y =
        150 +
        k * 16 +
        Math.sin(x * w * 3 + k * 0.6) * (32 - k * 2.5) +
        Math.sin(x * w * 7 + k * 1.3) * 7;
      puntos.push(`${x === 0 ? "M" : "L"}${x},${y.toFixed(1)}`);
    }
    lineas.push(puntos.join(" "));
  }
  return lineas;
}

export function HeroePortada() {
  return (
    <section className={s.heroe} aria-labelledby="titulo-heroe">
      <div className={s.resplandor} aria-hidden="true" />
      <svg className={s.ondas} viewBox={`0 0 ${ANCHO} 320`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
        {ondas().map((d, i) => (
          // La <g> lleva el desplazamiento horizontal y el <path> el vaivén vertical
          <g key={i} className={s.ola} style={{ "--i": i } as CSSProperties}>
            <path d={d} fill="none" stroke="var(--accent)" strokeWidth={1.2} opacity={0.5 - i * 0.055} className={s.olaLinea} />
          </g>
        ))}
      </svg>

      <div className={s.contenido}>
        <div className={s.texto}>
          <p className={s.insignia}>
            <span className={s.insigniaPunto} aria-hidden="true" />
            Gratis y sin registro · Ley 21.719
          </p>
          <h1 id="titulo-heroe" className={s.titulo}>
            <span className={s.linea}>Mide la <span className={s.acento}>gobernanza de IA</span></span>{" "}
            <span className={s.linea}>de tu organización</span>
          </h1>
          <p className={s.bajada}>
            Un autodiagnóstico que se adapta a cómo usas la inteligencia artificial. Al terminar ves tu madurez en cada
            dominio, las brechas que conviene cerrar primero y la formación para cerrarlas.
          </p>
          <div className={s.acciones}>
            {/* Correcciones 05-11: carga completa (no <Link>) para que /comenzar llegue con su propia
                CSP y un script de verificación nuevo, igual que al recargar */}
            <a href="/comenzar" className={`btn btn-primary ${s.boton}`}>
              Comenzar autodiagnóstico
              <Icon name="flecha" />
            </a>
            <Link href="/retomar" prefetch={false} className={`btn btn-ghost ${s.boton}`}>
              Ya empecé: retomar
            </Link>
          </div>
          <ul className={s.garantias}>
            <li><Icon name="usuario" /> Sin registro ni invitación</li>
            <li><Icon name="reloj" /> Guarda y retoma cuando quieras</li>
            <li><Icon name="candado" /> Datos anonimizados antes de la IA</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
