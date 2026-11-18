"use client";

/**
 * Auditoría UX 16-11 · Fase 8.B: indicador de pasos común al mapa de datos, al asistente y al
 * registro de actividades, con el "siguiente paso" a la vista.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import { cargarCumplimiento } from "@/lib/registroActividades";
import { estadoPasos, pasoDeRuta, pasoPendiente, PASOS_REGISTRO, type NumeroPaso, type PasoRegistro } from "@/lib/flujoRegistro";
import p from "./pasosRegistro.module.css";

function EnlacePaso({ paso, className, children, actual }: { paso: PasoRegistro; className: string; children: ReactNode; actual?: boolean }) {
  return paso.recargaCompleta ? (
    <a href={paso.href} className={className} aria-current={actual ? "step" : undefined}>{children}</a>
  ) : (
    <Link href={paso.href} className={className} aria-current={actual ? "step" : undefined} prefetch={false}>{children}</Link>
  );
}

export function PasosRegistro() {
  const pathname = usePathname();
  const [asistente, setAsistente] = useState(false);
  const [pendiente, setPendiente] = useState<NumeroPaso | null>(null);

  useEffect(() => {
    setAsistente(new URLSearchParams(window.location.search).get("asistente") === "1");
    cargarCumplimiento()
      .then((c) => setPendiente(pasoPendiente({ mapaIniciado: c.mapa.iniciado, elementos: c.mapa.elementos, actividades: c.registro.activas })))
      .catch(() => setPendiente(null));
  }, [pathname]);

  const actual = pasoDeRuta(pathname, asistente);
  if (!actual) return null;
  const estados = estadoPasos(actual, pendiente ?? actual);
  const siguiente = pendiente && pendiente !== actual ? PASOS_REGISTRO[pendiente - 1] : actual < 3 ? PASOS_REGISTRO[actual] : null;

  return (
    <nav className={p.flujo} aria-label="Arma tu registro de actividades: pasos">
      <ol className={p.pasos}>
        {PASOS_REGISTRO.map((x) => (
          <li key={x.numero} className={p.paso} data-estado={estados[x.numero]}>
            <EnlacePaso paso={x} className={p.enlace} actual={x.numero === actual}>
              <span className={p.marca} aria-hidden="true">
                {estados[x.numero] === "hecho" ? <Icon name="check" /> : x.numero}
              </span>
              <span className={p.texto}>
                <span className="sr-only">
                  Paso {x.numero} de 3{estados[x.numero] === "hecho" ? ", hecho" : x.numero === actual ? ", estás aquí" : ""}:{" "}
                </span>
                {x.titulo}
              </span>
            </EnlacePaso>
          </li>
        ))}
      </ol>
      {siguiente ? (
        <p className={p.siguiente}>
          <span>Siguiente paso:</span>
          <EnlacePaso paso={siguiente} className="link-btn">
            {siguiente.titulo}
            <Icon name="flecha" aria-hidden="true" />
          </EnlacePaso>
        </p>
      ) : null}
    </nav>
  );
}
