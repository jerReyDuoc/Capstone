"use client";

/**
 * Ficha de solo lectura de una actividad: la de una actividad vigente o archivada (que ya no se
 * edita) y la de cualquier versión guardada del historial. Muestra los 13 campos en el orden del
 * registro, con lo que la actividad tomó del mapa en ese momento.
 */
import type { ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { nombreDato, nombreOpcion, plural, type CatalogoMapa } from "@/lib/mapaDatos";
import type { CatalogoRat, ContenidoActividad, Derivados } from "@/lib/registroActividades";
import s from "./rat.module.css";

type MapaFicha = Pick<Derivados, "tipos_datos" | "titulares" | "bases_datos" | "paises" | "terceros" | "transferencias">;

function nombre(lista: { codigo: string; nombre: string }[], codigo: string | null): string {
  if (!codigo) return "";
  return lista.find((o) => o.codigo === codigo)?.nombre ?? codigo;
}

const SIN = <span className={ms.sinDato}>Sin completar</span>;

export function FichaActividad({
  contenido: c,
  mapa: d,
  catalogo,
  catalogoMapa,
}: {
  contenido: ContenidoActividad;
  mapa: MapaFicha;
  catalogo: CatalogoRat;
  catalogoMapa: CatalogoMapa | null;
}) {
  const filas: { titulo: string; valor: ReactNode }[] = [
    { titulo: "Descripción", valor: c.descripcion || <span className={ms.sinDato}>Sin descripción</span> },
    { titulo: "Área responsable", valor: c.area || <span className={ms.sinDato}>Sin indicar</span> },
    {
      titulo: "Rol de tu empresa",
      valor: c.rol
        ? `${nombre(catalogo.roles_empresa, c.rol)}${c.rol === "encargado" && c.responsable_mandante ? ` por cuenta de ${c.responsable_mandante}` : ""}`
        : SIN,
    },
    ...(c.volumen
      ? [{ titulo: "Personas que abarca", valor: nombre(catalogo.volumenes ?? [], c.volumen) }]
      : []),
    {
      titulo: "Finalidades",
      valor: c.finalidades.length ? <ul>{c.finalidades.map((f) => <li key={f}>{f}</li>)}</ul> : SIN,
    },
    {
      titulo: "Tipos de datos",
      valor: d.tipos_datos.length ? (
        <ul className={ms.etiquetas}>
          {d.tipos_datos.map((t) => <li key={t.codigo} className={ms.etiqueta} data-tono={t.sensible ? "sensible" : undefined}>{t.nombre}{t.sensible ? " · sensible" : ""}</li>)}
        </ul>
      ) : SIN,
    },
    {
      titulo: "Categorías de titulares",
      valor: d.titulares.length ? (
        <ul className={ms.etiquetas}>
          {d.titulares.map((t) => <li key={t.codigo} className={ms.etiqueta} data-tono={t.nna ? "nna" : undefined}>{t.nombre}</li>)}
        </ul>
      ) : SIN,
    },
    { titulo: "Sistemas y bases de datos", valor: d.bases_datos.length ? d.bases_datos.map((b) => b.nombre).join(", ") : SIN },
    {
      titulo: "Ámbito territorial",
      valor: d.paises.length ? `${d.paises.map((p) => p.nombre).join(", ")}${c.ambito_nota ? `. ${c.ambito_nota}` : ""}` : SIN,
    },
    {
      titulo: "Fuentes de los datos",
      valor: c.fuentes.length ? (
        <ul>
          {c.fuentes.map((f, i) => {
            const o = catalogo.fuentes.find((x) => x.codigo === f.tipo);
            return <li key={i}>{o?.nombre ?? f.tipo}{f.detalle ? `: ${f.detalle}` : ""}{o?.acceso_publico ? " (acceso público)" : ""}</li>;
          })}
        </ul>
      ) : SIN,
    },
    {
      titulo: "Base de licitud",
      valor: c.base_licitud ? (
        <>
          {nombre(catalogo.bases_licitud, c.base_licitud)}
          {c.interes_legitimo ? `\nInterés legítimo: ${c.interes_legitimo}` : ""}
          {c.base_sensibles ? `\nDatos sensibles: ${nombre(catalogo.bases_sensibles, c.base_sensibles)}` : ""}
        </>
      ) : SIN,
    },
    {
      titulo: "Terceros destinatarios",
      valor: d.terceros.length ? d.terceros.map((t) => t.nombre).join(", ")
        : c.sin_destinatarios ? "No se comunican a terceros" : SIN,
    },
    {
      titulo: "Transferencias internacionales",
      valor: d.transferencias.length ? (
        <ul>
          {d.transferencias.map((t) => (
            <li key={t.flujo_id}>{t.nombre} ({t.pais_nombre}): {t.garantia_valida ? t.garantia_nombre : "sin garantía documentada"}</li>
          ))}
        </ul>
      ) : "No hay",
    },
    {
      titulo: "Plazos de conservación",
      valor: c.plazos.length ? (
        <ul>
          {c.plazos.filter((p) => p.plazo && p.unidad).map((p) => (
            <li key={p.categoria}>
              {nombreDato(catalogoMapa, p.categoria)}: {p.plazo} {nombre(catalogo.unidades_plazo, p.unidad)}
              {p.desde ? ` ${nombre(catalogo.inicios_plazo, p.desde)}` : ""}{p.fundamento ? ` (${p.fundamento})` : ""}
            </li>
          ))}
        </ul>
      ) : SIN,
    },
    {
      titulo: "Decisiones automatizadas",
      valor: c.decisiones.existe === null ? SIN : c.decisiones.existe ? (
        <>
          {c.decisiones.perfilamiento ? "Sí, con perfilamiento." : "Sí."}
          {c.decisiones.logica ? `\nLógica: ${c.decisiones.logica}` : ""}
          {c.decisiones.consecuencias ? `\nEfectos: ${c.decisiones.consecuencias}` : ""}
          {c.decisiones.intervencion_humana !== null ? `\nRevisión por una persona: ${c.decisiones.intervencion_humana ? "sí" : "no"}` : ""}
        </>
      ) : "No toma decisiones automatizadas ni arma perfiles",
    },
    {
      titulo: "Medidas de seguridad",
      valor: c.medidas.codigos.length || c.medidas.otras ? (
        <>
          {c.medidas.codigos.map((m) => nombreOpcion(catalogo.medidas_seguridad, m)).join(", ")}
          {c.medidas.otras ? `${c.medidas.codigos.length ? "\n" : ""}${c.medidas.otras}` : ""}
        </>
      ) : SIN,
    },
  ];
  return (
    <dl className={s.ficha}>
      {filas.map((f) => (
        <div key={f.titulo}>
          <dt>{f.titulo}</dt>
          <dd>{f.valor}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ResumenCorto({ porcentaje, faltan }: { porcentaje: number; faltan: number }) {
  return (
    <span className="card-sub" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      <Icon name={faltan ? "alerta" : "check"} width={16} height={16} aria-hidden />
      {porcentaje} % completa{faltan ? ` · ${plural(faltan, "dato pendiente", "datos pendientes")}` : ""}
    </span>
  );
}
