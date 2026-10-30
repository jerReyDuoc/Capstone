import type { SVGProps } from "react";

/** Íconos de trazo 24×24 (estilo lineal como en el sitio). Decorativos por defecto. */
const PATHS = {
  diagnostico: "M9 3h6M9 3a2 2 0 0 0-2 2v0H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-1v0a2 2 0 0 0-2-2M8 13l2.5 2.5L16 10",
  dominios: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-9 9h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9M12 3C9.5 5.6 8.2 8.6 8.2 12s1.3 6.4 3.8 9",
  brechas: "M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0ZM12 9v4M12 17h.01",
  escudo: "M12 3 4.5 6v5.5c0 4.6 3.1 8.3 7.5 9.5 4.4-1.2 7.5-4.9 7.5-9.5V6L12 3Zm-3 9 2 2 4-4",
  chispa: "M12 3l1.6 4.6L18 9.2l-4.4 1.6L12 15.4l-1.6-4.6L6 9.2l4.4-1.6L12 3ZM18.5 14l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM5 16.5l.6 1.4 1.4.6-1.4.6L5 20.5l-.6-1.4L3 18.5l1.4-.6.6-1.4Z",
  radar: "M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l6-6M12 12h.01",
  lista: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  refrescar: "M20 11a8 8 0 0 0-14.6-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5L20 16m0 4v-4h-4",
  flecha: "M5 12h14m-6-6 6 6-6 6",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13h.01M11 12h1v5h1",
  libro: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15ZM4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5",
  flechaArriba: "M12 19V5m-6 6 6-6 6 6",
  flechaAbajo: "M12 5v14m6-6-6 6-6-6",
  ordenar: "M8 4v16m0 0-3-3m3 3 3-3M16 20V4m0 0-3 3m3-3 3 3",
  // HU-19
  check: "M20 6 9 17l-5-5",
  candado: "M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Zm2 0V7a4 4 0 1 1 8 0v4",
  reloj: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v4l3 2",
  copiar: "M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1ZM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  descargar: "M12 4v11m0 0-4-4m4 4 4-4M5 19h14",
  usuario: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  alerta: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5m0 3h.01",
  // HU-11
  buscar: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm9 3-4.35-4.35",
  pdf: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5M9 13h6M9 17h4",
  tabla: "M4 5h16v14H4V5Zm0 5h16M4 15h16M10 5v14",
  fijar: "M9 4h6l-1 6 3 3v2H7v-2l3-3-1-6Zm3 11v6",
  cerrar: "M6 6l12 12M18 6 6 18",
  // HU-15: Agente IA Tutor
  mensaje: "M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4v-4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm4 5h8M8 13h5",
  enviar: "M4 12 20 4l-4 16-4-7-8-1Zm8 1 8-9",
  basura: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  historial: "M3 12a9 9 0 1 0 3-6.7L3 8m0-4v4h4m5-1v5l3 2",
  mas: "M12 5v14M5 12h14",
  // HU-12
  correo: "M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Zm-.5 1 8.5 6 8.5-6",
  diana: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
  birrete: "M2 9l10-5 10 5-10 5L2 9Zm4 2v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5M22 9v6",
  // HU-26 / HU-17
  constancia: "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm-3.5 4.8L9.5 14m5 0 1 5.8L12 18l-3.5 1.8M10 9l1.5 1.5L14.5 7.5",
  subir: "M12 16V5m0 0-4 4m4-4 4 4M5 19h14",
  play: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-2-12.5v7l6-3.5-6-3.5Z",
  documento: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5M9 13h6M9 17h6",
  // Correcciones 29-10: navegación del espacio de la empresa
  empresa: "M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M3 21h18M8 7h4M8 11h4M8 15h4",
  carpeta: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
  salir: "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3",
  flechaIzq: "M19 12H5m6 6-6-6 6-6",
  // HU-10: comparativa sectorial (tu barra frente a las del grupo)
  sector: "M3 21h18M6 21v-6M10.5 21V9M15 21v-9M19.5 21V6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  title,
  ...props
}: { name: IconName; title?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      focusable="false"
      {...props}
    >
      {title ? <title>{title}</title> : null}
      <path d={PATHS[name]} />
    </svg>
  );
}

/** Marca TherionLabs (hexágono). Reemplazable por public/therion-logo.svg. */
export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" focusable="false" {...props}>
      <defs>
        <linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3be3b2" />
          <stop offset="1" stopColor="#1fa6e0" />
        </linearGradient>
      </defs>
      <path d="M20 3 35 11.5v17L20 37 5 28.5v-17L20 3Z" fill="#0b1512" stroke="url(#bm-g)" strokeWidth="2" />
      <path d="M12 15.5 20 20l8-4.5M20 20v9.5M12 15.5v9l8 4.5M28 15.5v9" fill="none" stroke="url(#bm-g)" strokeWidth="2.2" strokeLinejoin="round" />
    </svg>
  );
}
