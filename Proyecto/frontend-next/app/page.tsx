/**
 * HU-19 · Landing pública (antes redirigía a /panel).
 *
 * 100 % estática (force-static) y sin componentes cliente: no hidrata nada propio y no
 * carga el CAPTCHA. El flujo interactivo vive en /comenzar, que se carga solo al hacer
 * clic (prefetch desactivado para no bajar su JavaScript en segundo plano).
 */
import type { Metadata } from "next";
import Link from "next/link";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/publico.module.css";
import { Icon, type IconName } from "@/components/ui/Icon";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: { absolute: "Autodiagnóstico de gobernanza de IA · ComplianceAI" },
  description:
    "Evalúa gratis y sin registro la madurez de tu organización en gobernanza de inteligencia artificial y protección de datos (Ley 21.719).",
};

const DOMINIOS: { nombre: string; icono: IconName; texto: string }[] = [
  { nombre: "Protección de Datos", icono: "candado", texto: "Licitud del tratamiento, datos sensibles, transferencias internacionales y transparencia (Ley 21.719)." },
  { nombre: "Gobernanza de IA", icono: "escudo", texto: "Políticas, responsables y el inventario de los sistemas de IA que usa tu organización." },
  { nombre: "Gestión de Riesgos", icono: "radar", texto: "Cómo identificas, registras y das seguimiento a los riesgos de cada sistema de IA." },
  { nombre: "Uso Responsable", icono: "chispa", texto: "Seguridad de modelos de lenguaje, anonimización y supervisión humana en decisiones de impacto." },
];

function CTAs() {
  return (
    <div className={s.acciones}>
      <Link href="/comenzar" prefetch={false} className={`btn btn-primary ${s.btnGrande}`}>
        Comenzar autodiagnóstico
        <Icon name="flecha" />
      </Link>
      <Link href="/retomar" prefetch={false} className={`btn btn-ghost ${s.btnGrande}`}>
        Ya empecé: retomar
      </Link>
    </div>
  );
}

/** Radar decorativo (SVG estático, valores de ejemplo). */
function RadarEjemplo() {
  const c = { x: 160, y: 150 };
  const r = 110;
  const anillos = [0.25, 0.5, 0.75, 1].map((k) =>
    [`${c.x},${c.y - r * k}`, `${c.x + r * k},${c.y}`, `${c.x},${c.y + r * k}`, `${c.x - r * k},${c.y}`].join(" "),
  );
  const v = [0.72, 0.58, 0.45, 0.64];
  const area = [`${c.x},${c.y - r * v[0]}`, `${c.x + r * v[1]},${c.y}`, `${c.x},${c.y + r * v[2]}`, `${c.x - r * v[3]},${c.y}`].join(" ");
  return (
    <svg viewBox="0 0 320 300" aria-hidden="true" focusable="false">
      {anillos.map((p, i) => (
        <polygon key={i} points={p} fill="none" stroke="var(--grid)" strokeWidth="1" />
      ))}
      <line x1={c.x} y1={c.y - r} x2={c.x} y2={c.y + r} stroke="var(--grid)" />
      <line x1={c.x - r} y1={c.y} x2={c.x + r} y2={c.y} stroke="var(--grid)" />
      <polygon points={area} fill="rgba(20,216,158,0.18)" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      {area.split(" ").map((p) => {
        const [x, y] = p.split(",");
        return <circle key={p} cx={x} cy={y} r="4" fill="var(--accent)" />;
      })}
      <g fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-body)" textAnchor="middle">
        <text x={c.x} y={c.y - r - 12}>Datos</text>
        <text x={c.x + r + 4} y={c.y - 10} textAnchor="end">Gobernanza</text>
        <text x={c.x} y={c.y + r + 22}>Riesgos</text>
        <text x={c.x - r - 4} y={c.y - 10} textAnchor="start">Uso resp.</text>
      </g>
    </svg>
  );
}

export default function Landing() {
  return (
    <PaginaPublica>
      <section className={s.heroe} aria-labelledby="titulo-heroe">
        <div className={`${s.contenedor} ${s.heroeGrid}`}>
          <div>
            <span className={s.eyebrow}>Autodiagnóstico gratuito · Ley 21.719</span>
            <h1 id="titulo-heroe" className={s.titulo}>
              ¿Qué tan preparada está tu organización para <em>gobernar la IA</em>?
            </h1>
            <p className={s.bajada}>
              Responde un cuestionario que se adapta a cómo usas la inteligencia artificial y obtén tu nivel de madurez
              por dominio, tus brechas priorizadas y rutas formativas para cerrarlas.
            </p>
            <CTAs />
            <ul className={s.garantias}>
              <li><Icon name="usuario" /> Sin registro ni invitación</li>
              <li><Icon name="reloj" /> Guarda y retoma cuando quieras</li>
              <li><Icon name="candado" /> Datos anonimizados antes de la IA</li>
            </ul>
          </div>
          <div className={s.visual} aria-hidden="true">
            <div className={s.visualCabecera}>
              <span className={s.visualEtiqueta}>Madurez por dominio</span>
              <span className={s.visualValor}>
                60<small>/100</small>
              </span>
            </div>
            <RadarEjemplo />
            <p className={s.visualPie}>Ejemplo ilustrativo del resultado</p>
          </div>
        </div>
      </section>

      <section id="como-funciona" className={s.seccion} aria-labelledby="titulo-como">
        <div className={s.contenedor}>
          <h2 id="titulo-como" className={s.seccionTitulo}>Cómo funciona</h2>
          <p className={s.seccionBajada}>Tres pasos. Puedes pausar en cualquier momento y continuar desde otro dispositivo con tu clave.</p>
          <ol className={s.pasos}>
            <li className={s.paso}>
              <h3>Acepta el aviso y elige tu rubro</h3>
              <p>Así comparamos tu resultado con organizaciones similares. No pedimos tu nombre ni el de tu empresa.</p>
            </li>
            <li className={s.paso}>
              <h3>Responde y adjunta evidencias</h3>
              <p>Unas preguntas iniciales filtran los controles que aplican a tu caso. La IA ayuda a validar las evidencias.</p>
            </li>
            <li className={s.paso}>
              <h3>Recibe tu diagnóstico</h3>
              <p>Nivel de madurez por dominio, brechas ordenadas por criticidad y rutas formativas recomendadas.</p>
            </li>
          </ol>
        </div>
      </section>

      <section className={s.seccion} aria-labelledby="titulo-dominios">
        <div className={s.contenedor}>
          <h2 id="titulo-dominios" className={s.seccionTitulo}>Qué evalúa</h2>
          <p className={s.seccionBajada}>Controles basados en la Ley N.º 21.719, NIST AI RMF y OWASP para aplicaciones con modelos de lenguaje.</p>
          <ul className={s.dominios}>
            {DOMINIOS.map((d) => (
              <li key={d.nombre} className={s.dominio}>
                <Icon name={d.icono} />
                <h3>{d.nombre}</h3>
                <p>{d.texto}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section id="privacidad" className={s.seccion} aria-labelledby="titulo-privacidad">
        <div className={`${s.contenedor} ${s.privacidad}`}>
          <div>
            <h2 id="titulo-privacidad" className={s.seccionTitulo}>Tu información, protegida</h2>
            <p className={s.seccionBajada}>
              Diseñamos el autodiagnóstico para que puedas usarlo sin entregar datos personales.{" "}
              <Link href="/aviso-legal" prefetch={false}>Lee el aviso legal</Link>.
            </p>
          </div>
          <ul className={s.listaCheck}>
            <li><Icon name="check" /> Anonimizamos RUT, nombres, correos, teléfonos y direcciones antes de guardar o enviar al modelo de IA.</li>
            <li><Icon name="check" /> El correo es opcional y solo sirve para retomar o recibir tu informe.</li>
            <li><Icon name="check" /> En la comparación con tu rubro solo entran evaluaciones completas y de forma agregada.</li>
            <li><Icon name="check" /> Puedes ejercer tus derechos de acceso, rectificación y supresión con tu clave.</li>
          </ul>
        </div>
      </section>

      <div className={s.contenedor}>
        <section className={s.cierre} aria-labelledby="titulo-cierre">
          <h2 id="titulo-cierre" className={s.seccionTitulo}>Empieza ahora, termina cuando puedas</h2>
          <p className={s.seccionBajada} style={{ margin: "8px auto 0" }}>Al comenzar recibirás una clave para continuar más tarde.</p>
          <CTAs />
        </section>
      </div>
    </PaginaPublica>
  );
}
