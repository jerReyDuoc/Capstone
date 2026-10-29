/**
 * Portada (/) · Héroe centrado (correcciones 29-10; reemplaza el mapa topográfico).
 *
 * Server Component sin estado ni JavaScript propio: la portada sigue siendo force-static.
 *  - Texto centrado: insignia, titular, bajada, botones y garantías.
 *  - Debajo, una vista previa del resultado con tres tarjetas de ejemplo (nivel global al
 *    centro; madurez por dominio y brechas priorizadas a los lados). Muestra lo que el
 *    visitante obtiene, en vez de una metáfora. Los datos son ficticios y se dice.
 *  - Detrás, ondas finas en el verde de marca, solo decorativas (aria-hidden).
 *  - Al deslizar, el texto y la vista previa se desvanecen con una animación ligada al
 *    scroll (animation-timeline, solo CSS). Sin soporte o con "reducir movimiento", quedan fijos.
 */
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import s from "./heroe.module.css";

const DOMINIOS_EJEMPLO = [
  { nombre: "Protección de Datos", valor: 72 },
  { nombre: "Uso Responsable", valor: 64 },
  { nombre: "Gobernanza de IA", valor: 58 },
  { nombre: "Gestión de Riesgos", valor: 41 },
];

const BRECHAS_EJEMPLO = [
  { severidad: "Crítica", tono: "critico", texto: "Sin inventario de los sistemas de IA en uso" },
  { severidad: "Alta", tono: "alta", texto: "Clientes sin aviso de que interactúan con IA" },
  { severidad: "Media", tono: "media", texto: "Riesgos de cada modelo sin registro formal" },
] as const;

const PUNTAJE_EJEMPLO = 59;

/** Ondas del fondo: senos superpuestos, calculados al compilar (no hay JS en el cliente). */
function ondas(): string[] {
  const lineas: string[] = [];
  for (let k = 0; k < 7; k++) {
    const puntos: string[] = [];
    for (let x = 0; x <= 1440; x += 24) {
      const y =
        170 +
        k * 14 +
        Math.sin(x / 210 + k * 0.55) * (34 - k * 2.5) +
        Math.sin(x / 95 + k * 1.3) * 7;
      puntos.push(`${x === 0 ? "M" : "L"}${x},${y.toFixed(1)}`);
    }
    lineas.push(puntos.join(" "));
  }
  return lineas;
}

export function HeroePortada() {
  const circunferencia = 2 * Math.PI * 54;
  const arco = (PUNTAJE_EJEMPLO / 100) * circunferencia;

  return (
    <section className={s.heroe} aria-labelledby="titulo-heroe">
      <div className={s.resplandor} aria-hidden="true" />
      <svg className={s.ondas} viewBox="0 0 1440 320" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="onda-trazo" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0" />
            <stop offset="0.5" stopColor="var(--accent)" stopOpacity="1" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ondas().map((d, i) => (
          <path key={i} d={d} fill="none" stroke="url(#onda-trazo)" strokeWidth={1} opacity={0.32 - i * 0.035} />
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
            <Link href="/comenzar" prefetch={false} className={`btn btn-primary ${s.boton}`}>
              Comenzar autodiagnóstico
              <Icon name="flecha" />
            </Link>
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

        <figure className={s.vistaPrevia}>
          <figcaption className={s.vistaLeyenda}>Ejemplo de resultado · organización ficticia</figcaption>
          <div className={s.tarjetas}>
            <div className={`${s.tarjeta} ${s.lateral} ${s.izquierda}`}>
              <p className={s.tarjetaTitulo}>Madurez por dominio</p>
              <ul className={s.barras}>
                {DOMINIOS_EJEMPLO.map((d) => (
                  <li key={d.nombre}>
                    <span className={s.barraNombre}>{d.nombre}</span>
                    <span className={s.barraPista} aria-hidden="true">
                      <span className={s.barraValor} style={{ width: `${d.valor}%` }} data-bajo={d.valor < 50 || undefined} />
                      <span className={s.barraMeta} />
                    </span>
                    <span className={s.barraCifra}>{d.valor}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className={`${s.tarjeta} ${s.central}`}>
              <p className={s.tarjetaTitulo}>Nivel de madurez</p>
              <div className={s.medidor}>
                <svg viewBox="0 0 128 128" aria-hidden="true" focusable="false">
                  <circle cx="64" cy="64" r="54" className={s.medidorPista} />
                  <circle
                    cx="64" cy="64" r="54"
                    className={s.medidorValor}
                    strokeDasharray={`${arco} ${circunferencia}`}
                    transform="rotate(-90 64 64)"
                  />
                </svg>
                <span className={s.medidorCifra}>
                  {PUNTAJE_EJEMPLO}
                  <small>de 100</small>
                </span>
              </div>
              <p className={s.nivel}>En desarrollo</p>
              <p className={s.nivelSub}>4 dominios evaluados · 8 brechas</p>
            </div>

            <div className={`${s.tarjeta} ${s.lateral} ${s.derecha}`}>
              <p className={s.tarjetaTitulo}>Brechas priorizadas</p>
              <ol className={s.brechas}>
                {BRECHAS_EJEMPLO.map((b) => (
                  <li key={b.texto}>
                    <span className={s.sev} data-tono={b.tono}>{b.severidad}</span>
                    <span className={s.brechaTexto}>{b.texto}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </figure>
      </div>
    </section>
  );
}
