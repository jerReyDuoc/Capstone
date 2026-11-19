"use client";

/**
 * Mejoras 19-11 · Plan de acción → Brechas:
 *   - "Progreso general de cumplimiento": porcentaje global, barra y desglose por normativa;
 *   - "Brechas por tipo": Cumple / Parcial / No cumple / Crítico;
 *   - pestañas por normativa (con su porcentaje) que filtran el listado de brechas.
 *
 * Todo se calcula con las respuestas y la matriz de controles de la evaluación
 * (lib/cumplimientoNormativa.ts). Nada queda fijo en el código.
 */
import { InfoTip } from "@/components/ui/InfoTip";
import {
  formatoPorcentaje, type BrechasPorTipo, type CumplimientoNormativa, type CumplimientoVista,
} from "@/lib/cumplimientoNormativa";

/** Tono de la barra según el avance (el verde queda solo para "casi todo cumplido"). */
export function tonoCumplimiento(p: number | null): "ok" | "bueno" | "medio" | "bajo" {
  if (p == null || p < 25) return "bajo";
  if (p < 50) return "medio";
  if (p < 75) return "bueno";
  return "ok";
}

const ancho = (p: number | null) => `${Math.max(0, Math.min(100, p ?? 0))}%`;

function FormulaAyuda() {
  return (
    <InfoTip etiqueta="¿Cómo se calcula el porcentaje?" icono="ayuda">
      Cada práctica cumplida suma 1 punto y cada una cumplida en parte suma medio punto. Se divide por las prácticas
      evaluadas de esa normativa (las que no aplican a tu empresa no cuentan; las que la IA aún revisa cuentan como no
      cumplidas hasta que se resuelvan) y se multiplica por 100.
    </InfoTip>
  );
}

export function ProgresoCumplimiento({
  cumplimiento,
  seleccion,
  onSeleccionar,
}: {
  cumplimiento: CumplimientoVista;
  seleccion: string | null;
  onSeleccionar: (id: string | null) => void;
}) {
  const g = cumplimiento.general;
  return (
    <section className="card cumplimiento" aria-labelledby="cumplimiento-titulo">
      <div className="cumplimiento-cabeza">
        <div>
          <h2 className="card-title" id="cumplimiento-titulo">
            Progreso general de cumplimiento
            <FormulaAyuda />
          </h2>
          <p className="card-sub">
            {g.evaluados} {g.evaluados === 1 ? "práctica evaluada" : "prácticas evaluadas"} · {g.cumplidos} cumplidas ·{" "}
            {g.parciales} en parte · {g.noCumplidos} sin cumplir
            {g.enRevision ? ` · ${g.enRevision} en revisión` : ""}
          </p>
        </div>
        <p className={`cumplimiento-cifra cump-${tonoCumplimiento(g.porcentaje)}`}>
          {formatoPorcentaje(g.porcentaje)}
        </p>
      </div>
      <div
        className={`cumplimiento-barra cump-${tonoCumplimiento(g.porcentaje)}`}
        role="meter"
        aria-label={`Cumplimiento general: ${formatoPorcentaje(g.porcentaje)}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(g.porcentaje ?? 0)}
      >
        <span style={{ width: ancho(g.porcentaje) }} />
      </div>

      {cumplimiento.normativas.length ? (
        <>
          <h3 className="cumplimiento-subtitulo">Por normativa</h3>
          <ul className="cumplimiento-lista">
            {cumplimiento.normativas.map((n) => (
              <li key={n.id}>
                <FilaNormativa n={n} activa={seleccion === n.id} onClick={() => onSeleccionar(seleccion === n.id ? null : n.id)} />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="card-sub">
          Los controles de esta evaluación no informan su normativa, por eso no podemos mostrar el desglose.
        </p>
      )}
    </section>
  );
}

function FilaNormativa({ n, activa, onClick }: { n: CumplimientoNormativa; activa: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className="cumplimiento-fila"
      aria-pressed={activa}
      title={n.nombreCompleto}
      aria-label={`${n.nombreCompleto}: ${formatoPorcentaje(n.porcentaje)} de cumplimiento, ${n.evaluados} prácticas evaluadas. ${
        activa ? "Quitar el filtro del listado." : "Filtrar el listado por esta normativa."
      }`}
      onClick={onClick}
    >
      <span className="cumplimiento-fila-nombre">{n.nombre}</span>
      <span className={`cumplimiento-barra cumplimiento-barra-fina cump-${tonoCumplimiento(n.porcentaje)}`} aria-hidden="true">
        <span style={{ width: ancho(n.porcentaje) }} />
      </span>
      <span className="cumplimiento-fila-valor">
        <strong>{formatoPorcentaje(n.porcentaje)}</strong>
        <span>{n.evaluados} {n.evaluados === 1 ? "práctica" : "prácticas"}</span>
      </span>
    </button>
  );
}

const TIPOS: { clave: keyof BrechasPorTipo; texto: string; ayuda: string; clase: string }[] = [
  { clave: "cumple", texto: "Cumple", ayuda: "Prácticas cumplidas", clase: "tipo-cumple" },
  { clave: "parcial", texto: "Parcial", ayuda: "Brechas cumplidas en parte", clase: "tipo-parcial" },
  { clave: "noCumple", texto: "No cumple", ayuda: "Brechas sin cumplir (no críticas)", clase: "tipo-no-cumple" },
  { clave: "critico", texto: "Crítico", ayuda: "Brechas de severidad crítica: atiéndelas primero", clase: "tipo-critico" },
];

export function TarjetaBrechasPorTipo({ tipos, normativa }: { tipos: BrechasPorTipo; normativa: string | null }) {
  return (
    <section className="card brechas-tipo" aria-labelledby="brechas-tipo-titulo">
      <h2 className="card-title" id="brechas-tipo-titulo">
        Brechas por tipo
        <InfoTip etiqueta="¿Qué significa cada tipo?" icono="ayuda">
          Cada práctica se cuenta en un solo tipo. Una brecha crítica (alto impacto y sin cumplir) se cuenta solo en
          «Crítico», no también en «No cumple».
        </InfoTip>
      </h2>
      <p className="card-sub">{normativa ? `Solo ${normativa}` : "Todas las normativas"}</p>
      <ul className="brechas-tipo-lista">
        {TIPOS.map((t) => (
          <li key={t.clave} className={t.clase} title={t.ayuda}>
            <span className="brechas-tipo-valor">{tipos[t.clave]}</span>
            <span className="brechas-tipo-texto">{t.texto}</span>
            <span className="sr-only">: {t.ayuda}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PestanasNormativa({
  cumplimiento,
  seleccion,
  onSeleccionar,
}: {
  cumplimiento: CumplimientoVista;
  seleccion: string | null;
  onSeleccionar: (id: string | null) => void;
}) {
  if (!cumplimiento.normativas.length) return null;
  const opciones: { id: string | null; nombre: string; porcentaje: number | null; titulo: string }[] = [
    { id: null, nombre: "Todas", porcentaje: cumplimiento.general.porcentaje, titulo: "Todas las normativas" },
    ...cumplimiento.normativas.map((n) => ({ id: n.id, nombre: n.nombre, porcentaje: n.porcentaje, titulo: n.nombreCompleto })),
  ];
  return (
    <div className="pestanas-normativa" role="group" aria-label="Filtrar las brechas por normativa">
      {opciones.map((o) => (
        <button
          key={o.id ?? "todas"}
          type="button"
          className="pestana-normativa"
          aria-pressed={seleccion === o.id}
          title={o.titulo}
          onClick={() => onSeleccionar(o.id)}
        >
          <span>{o.nombre}</span>
          <span className={`pestana-normativa-pct cump-${tonoCumplimiento(o.porcentaje)}`}>{formatoPorcentaje(o.porcentaje)}</span>
        </button>
      ))}
    </div>
  );
}
