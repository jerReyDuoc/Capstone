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
