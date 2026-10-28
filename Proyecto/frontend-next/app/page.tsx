/**
 * HU-19 · Landing pública (antes redirigía a /panel). Rediseño: "mapa de gobernanza".
 *
 * 100 % estática (force-static) y sin componentes cliente: no hidrata nada propio y no
 * carga el CAPTCHA. El flujo interactivo vive en /comenzar, que se carga solo al hacer
 * clic (prefetch desactivado para no bajar su JavaScript en segundo plano).
 *
 * La pieza central es un mapa topográfico (components/publico/MapaGobernanza.tsx): cada
 * cima es un dominio y su altura, la madurez. Es SVG generado al compilar, sin imágenes.
 */
import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import Link from "next/link";
import { MapaGobernanza } from "@/components/publico/MapaGobernanza";
import { PaginaPublica } from "@/components/publico/Marco";
import s from "@/components/publico/portada.module.css";
import { Icon, type IconName } from "@/components/ui/Icon";

export const dynamic = "force-static";

// Fuente de titulares solo para la portada (eje de ancho variable). El resto del sitio
// sigue con Space Grotesk e Inter (app/layout.tsx).
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });

export const metadata: Metadata = {
  title: { absolute: "Autodiagnóstico de gobernanza de IA · ComplianceAI" },
  description:
    "Evalúa gratis y sin registro la madurez de tu organización en gobernanza de inteligencia artificial y protección de datos (Ley 21.719).",
};

const DOMINIOS: { nombre: string; icono: IconName; texto: string }[] = [
  { nombre: "Protección de Datos", icono: "candado", texto: "Licitud del tratamiento, datos sensibles, transferencias internacionales y transparencia según la Ley 21.719." },
  { nombre: "Gobernanza de IA", icono: "escudo", texto: "Políticas, responsables y el inventario de los sistemas de IA que usa tu organización." },
  { nombre: "Gestión de Riesgos", icono: "radar", texto: "Cómo identificas, registras y das seguimiento a los riesgos de cada sistema de IA." },
  { nombre: "Uso Responsable", icono: "chispa", texto: "Seguridad de los modelos de lenguaje, anonimización y supervisión humana en las decisiones de impacto." },
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

export default function Landing() {
  return (
    <PaginaPublica>
      <div className={`${archivo.variable} ${s.portada}`}>
        <section className={s.heroe} aria-labelledby="titulo-heroe">
          <div className={s.contenedor}>
            <div className={s.heroeTexto}>
              <h1 id="titulo-heroe" className={s.titulo}>
                Levanta el mapa de gobernanza de IA de tu organización
              </h1>
              <div className={s.heroeLado}>
                <p className={s.bajada}>
                  Un autodiagnóstico gratuito que se adapta a cómo usas la inteligencia artificial. Al terminar ves tu
                  madurez en cada dominio, las brechas que conviene cerrar primero y la formación para cerrarlas.
                </p>
                <CTAs />
              </div>
            </div>
            <div className={s.mapa}>
              <MapaGobernanza />
            </div>
            <ul className={s.garantias}>
              <li><Icon name="usuario" /> Sin registro ni invitación</li>
              <li><Icon name="reloj" /> Guarda y retoma cuando quieras</li>
              <li><Icon name="candado" /> Datos anonimizados antes de la IA</li>
            </ul>
          </div>
        </section>

        <section id="como-funciona" className={s.seccion} aria-labelledby="titulo-como">
          <div className={s.contenedor}>
            <h2 id="titulo-como" className={s.seccionTitulo}>Cómo funciona</h2>
            <p className={s.seccionBajada}>
              Puedes pausar en cualquier momento y seguir desde otro dispositivo con la clave que recibes al comenzar.
            </p>
            <ol className={s.ruta}>
              <li className={s.parada}>
                <h3>Acepta el aviso y elige tu rubro</h3>
                <p>Así comparamos tu resultado con organizaciones similares. No pedimos tu nombre ni el de tu empresa.</p>
              </li>
              <li className={s.parada}>
                <h3>Responde y adjunta evidencias</h3>
                <p>Unas preguntas iniciales filtran los controles que aplican a tu caso. La IA ayuda a validar las evidencias.</p>
              </li>
              <li className={s.parada}>
                <h3>Recibe tu diagnóstico</h3>
                <p>Tu nivel de madurez por dominio, las brechas ordenadas por criticidad y la formación recomendada.</p>
              </li>
            </ol>
          </div>
        </section>

        <section className={s.seccion} aria-labelledby="titulo-dominios">
          <div className={`${s.contenedor} ${s.evalua}`}>
            <div>
              <h2 id="titulo-dominios" className={s.seccionTitulo}>Qué evalúa</h2>
              <p className={s.seccionBajada}>
                Cuatro dominios, con controles basados en la Ley 21.719, el NIST AI RMF y OWASP para aplicaciones con
                modelos de lenguaje.
              </p>
            </div>
            <ul className={s.leyenda}>
              {DOMINIOS.map((d) => (
                <li key={d.nombre}>
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
                Puedes hacer el autodiagnóstico sin entregar datos personales.{" "}
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
            <div>
              <h2 id="titulo-cierre" className={s.seccionTitulo}>Empieza ahora, termina cuando puedas</h2>
              <p className={s.seccionBajada}>Al comenzar recibes una clave para continuar más tarde.</p>
            </div>
            <CTAs />
          </section>
        </div>
      </div>
    </PaginaPublica>
  );
}
