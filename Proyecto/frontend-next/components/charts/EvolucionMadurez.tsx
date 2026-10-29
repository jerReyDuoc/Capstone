"use client";

/**
 * HU-29 criterio 1 · Evolución de la madurez de la empresa: puntaje global y por dimensión.
 *
 * Una línea por serie sobre el eje 0–100 con las bandas de nivel de madurez de fondo. El eje
 * X es ordinal (una posición por evaluación completada, rotulada con su fecha): lo que
 * importa es el antes y el después, no la distancia en días.
 *
 * Dos vistas, un solo eje: "Global" (la serie de la empresa, color de marca) y "Por
 * dimensión" (una línea por dimensión, colores categóricos en orden fijo validados contra
 * la superficie oscura; cada color sigue a su dimensión aunque se oculten otras). La
 * identidad nunca va solo en el color: leyenda con botones, rótulos directos al final de
 * cada línea y la tabla de datos (ChartFrame).
 *
 * Correcciones 29-10: el ancho del dibujo sigue al de la tarjeta (antes el viewBox fijo dejaba
 * el gráfico encajonado al centro en pantallas anchas) y el eje ya no muestra los números
 * internos de las evaluaciones, solo su fecha.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { COLORES_DIMENSION, fechaCorta, textoVariacion, type HistorialApi } from "@/lib/empresa";
import { formatoPuntaje, NIVELES, nivelDesdePuntaje } from "@/lib/madurez";
import { ChartFrame, posicionEnContenedor, Tooltip, type TooltipState } from "./ChartFrame";

const ANCHO_MIN = 320;
const H = 300;
// Margen derecho: en "Por dimensión" hay rótulos con el nombre al final de cada línea; en
// "Global" basta el espacio del valor.
const M_GLOBAL = { top: 20, right: 56, bottom: 36, left: 44 };
const M_DIMENSION = { ...M_GLOBAL, right: 132 };

type Vista = "global" | "dimension";

interface Serie {
  clave: string;
  nombre: string;
  color: string;
  puntos: (number | null)[];
}

export function EvolucionMadurez({ evolucion }: { evolucion: HistorialApi["evolucion"] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  // Nodo por estado (no ref) para volver a observar cuando el gráfico se remonta tras "Ver como tabla"
  const [caja, setCaja] = useState<HTMLDivElement | null>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    if (!caja || typeof ResizeObserver === "undefined") return;
    const obs = new ResizeObserver(([e]) => setW(Math.max(ANCHO_MIN, Math.round(e.contentRect.width))));
    obs.observe(caja);
    return () => obs.disconnect();
  }, [caja]);
  const [tip, setTip] = useState<TooltipState>(null);
  const [vista, setVista] = useState<Vista>("global");
  const [ocultas, setOcultas] = useState<Set<number>>(new Set());

  const fechas = evolucion.global.map((p) => p.fecha);
  const n = fechas.length;
  // El color sigue a la dimensión (orden alfabético estable del backend), no a su visibilidad
  const dimensiones = evolucion.dimensiones.slice(0, COLORES_DIMENSION.length);
  const sobran = evolucion.dimensiones.length - dimensiones.length;

  const series: Serie[] = useMemo(() => {
    if (vista === "global") {
      return [{ clave: "global", nombre: "Puntaje global", color: "var(--serie-empresa)", puntos: evolucion.global.map((p) => p.puntaje) }];
    }
    return dimensiones
      .map((d, i) => ({ id: d.dominio_id, s: { clave: `d${d.dominio_id}`, nombre: d.dominio, color: COLORES_DIMENSION[i], puntos: d.puntos.map((p) => p.puntaje) } }))
      .filter((x) => !ocultas.has(x.id))
      .map((x) => x.s);
  }, [vista, evolucion, dimensiones, ocultas]);

  const M = vista === "dimension" ? M_DIMENSION : M_GLOBAL;
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const x = (i: number) => (n <= 1 ? M.left + iw / 2 : M.left + (i / (n - 1)) * iw);
  const y = (v: number) => M.top + (1 - Math.max(0, Math.min(100, v)) / 100) * ih;

  const bandas = [
    { desde: 0, hasta: 25, nivel: "inicial" as const },
    { desde: 25, hasta: 50, nivel: "en_desarrollo" as const },
    { desde: 50, hasta: 75, nivel: "gestionado" as const },
    { desde: 75, hasta: 100, nivel: "optimizado" as const },
  ];

  // Rótulos directos al final de cada línea, separados para que no se encimen (≥ 15 px)
  const rotulos = useMemo(() => {
    const finales = series
      .map((s) => {
        const ultimo = [...s.puntos.keys()].reverse().find((i) => s.puntos[i] != null);
        return ultimo == null ? null : { s, i: ultimo, v: s.puntos[ultimo] as number, yy: y(s.puntos[ultimo] as number) };
      })
      .filter((r): r is NonNullable<typeof r> => r != null)
      .sort((a, b) => a.yy - b.yy);
    for (let k = 1; k < finales.length; k++) {
      if (finales[k].yy - finales[k - 1].yy < 15) finales[k].yy = finales[k - 1].yy + 15;
    }
    return finales;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series]);

  const primera = evolucion.global[0]?.puntaje ?? null;
  const ultima = evolucion.global[n - 1]?.puntaje ?? null;
  const resumen =
    n === 0
      ? "Aún no hay evaluaciones completadas."
      : n === 1
        ? `Una evaluación completada (${fechaCorta(fechas[0])}): ${formatoPuntaje(ultima)} puntos, nivel ${NIVELES[nivelDesdePuntaje(ultima ?? 0)].etiqueta}. Completa una reevaluación para ver la evolución.`
        : `El puntaje global pasó de ${formatoPuntaje(primera)} a ${formatoPuntaje(ultima)} (${textoVariacion(
            ultima != null && primera != null ? ultima - primera : null,
          )}) entre ${fechaCorta(fechas[0])} y ${fechaCorta(fechas[n - 1])}, en ${n} evaluaciones.`;

  const tabla = (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Puntaje global y por dimensión de cada evaluación completada</caption>
        <thead>
          <tr>
            <th scope="col">Evaluación</th>
            <th scope="col" className="num">Global</th>
            {evolucion.dimensiones.map((d) => (
              <th scope="col" className="num" key={d.dominio_id}>{d.dominio}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {evolucion.global.map((p, i) => (
            <tr key={p.evaluacion_id}>
              <th scope="row">{fechaCorta(p.fecha)}</th>
              <td className="num">{formatoPuntaje(p.puntaje)}</td>
              {evolucion.dimensiones.map((d) => (
                <td className="num" key={d.dominio_id}>{formatoPuntaje(d.puntos[i]?.puntaje)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const acciones = (
    <div className="chip-group" role="group" aria-label="Qué mostrar">
      <button type="button" className="chip" aria-pressed={vista === "global"} onClick={() => setVista("global")}>
        Global
      </button>
      <button type="button" className="chip" aria-pressed={vista === "dimension"} onClick={() => setVista("dimension")} disabled={!dimensiones.length}>
        Por dimensión
      </button>
    </div>
  );

  const leyenda =
    vista === "dimension" ? (
      <div className="chip-group" role="group" aria-label="Dimensiones visibles">
        {dimensiones.map((d, i) => {
          const visible = !ocultas.has(d.dominio_id);
          return (
            <button
              key={d.dominio_id}
              type="button"
              className="chip"
              aria-pressed={visible}
              onClick={() =>
                setOcultas((prev) => {
                  const sig = new Set(prev);
                  if (visible) sig.add(d.dominio_id);
                  else sig.delete(d.dominio_id);
                  return sig;
                })
              }
            >
              <span className="chip-swatch" style={{ background: COLORES_DIMENSION[i] }} aria-hidden="true" />
              {d.dominio}
            </button>
          );
        })}
        {sobran > 0 ? <span className="card-sub">+{sobran} en la tabla</span> : null}
      </div>
    ) : null;

  return (
    <ChartFrame
      titulo="Evolución de la madurez"
      subtitulo={vista === "global" ? "Puntaje global (0–100) de cada evaluación completada" : "Puntaje de cada dimensión normativa (0–100)"}
      resumen={resumen}
      acciones={acciones}
      tabla={tabla}
    >
      {leyenda}
      <div ref={setCaja} style={{ position: "relative" }}>
        <svg
          ref={svgRef}
          className="chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="group"
          aria-label={vista === "global" ? "Línea del puntaje global por evaluación" : "Líneas del puntaje por dimensión"}
          onMouseLeave={() => setTip(null)}
        >
          {bandas.map((b, i) => (
            <g key={b.nivel} aria-hidden="true">
              <rect x={M.left} y={y(b.hasta)} width={iw} height={y(b.desde) - y(b.hasta)} fill={i % 2 ? "rgba(255,255,255,0.018)" : "transparent"} />
              <text className="tick" x={M.left + 6} y={y(b.hasta) + 14}>{NIVELES[b.nivel].etiqueta}</text>
            </g>
          ))}
          {[0, 25, 50, 75, 100].map((t) => (
            <g key={t} aria-hidden="true">
              <line x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
              <text className="tick" x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">{t}</text>
            </g>
          ))}
          {fechas.map((f, i) => (
            <text key={i} className="tick" x={x(i)} y={H - M.bottom + 20} textAnchor="middle" aria-hidden="true">
              {fechaCorta(f)}
            </text>
          ))}

          {series.map((s) => {
            // La línea se corta donde la dimensión no aplicó (punto vacío)
            const tramos: string[] = [];
            let actual: string[] = [];
            s.puntos.forEach((v, i) => {
              if (v == null) {
                if (actual.length) tramos.push(actual.join(" "));
                actual = [];
              } else actual.push(`${actual.length ? "L" : "M"}${x(i)},${y(v)}`);
            });
            if (actual.length) tramos.push(actual.join(" "));
            return (
              <g key={s.clave}>
                {tramos.map((d, k) => (
                  <path key={k} d={d} fill="none" stroke={s.color} strokeWidth={vista === "global" ? 2.5 : 2} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" />
                ))}
                {s.puntos.map((v, i) => {
                  if (v == null) return null;
                  const p = evolucion.global[i];
                  const anterior = i > 0 ? s.puntos[i - 1] : null;
                  const etiqueta = `${s.nombre}, evaluación del ${fechaCorta(p.fecha)}: ${formatoPuntaje(v)} puntos, nivel ${NIVELES[nivelDesdePuntaje(v)].etiqueta}${anterior != null ? `, ${textoVariacion(v - anterior)} frente a la anterior` : ""}.`;
                  const mostrar = () => {
                    const pos = posicionEnContenedor(svgRef.current, x(i), y(v) - 8);
                    setTip({
                      ...pos,
                      titulo: `${s.nombre} · ${fechaCorta(p.fecha)}`,
                      filas: [
                        ["Puntaje", formatoPuntaje(v)],
                        ["Nivel", NIVELES[nivelDesdePuntaje(v)].etiqueta],
                        ["Frente a la anterior", anterior != null ? textoVariacion(v - anterior) : "—"],
                      ],
                    });
                  };
                  return (
                    <g
                      key={i}
                      className="chart-point"
                      tabIndex={0}
                      role="img"
                      aria-label={etiqueta}
                      onMouseEnter={mostrar}
                      onFocus={mostrar}
                      onBlur={() => setTip(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") setTip(null);
                      }}
                    >
                      <circle className="hit" cx={x(i)} cy={y(v)} r={14} />
                      {/* anillo del color de la superficie: separa puntos que se cruzan */}
                      <circle className="ring" cx={x(i)} cy={y(v)} r={6} fill="var(--surface)" stroke="var(--surface)" strokeWidth={2} />
                      <circle className="dot" cx={x(i)} cy={y(v)} r={4} fill={s.color} />
                    </g>
                  );
                })}
              </g>
            );
          })}

          {rotulos.map((r) => (
            <g key={r.s.clave} aria-hidden="true">
              <line x1={x(r.i) + 8} x2={x(r.i) + 14} y1={y(r.v)} y2={r.yy} stroke={r.s.color} strokeWidth={1.5} />
              <text x={x(r.i) + 18} y={r.yy} dominantBaseline="middle" className="value-label">
                {formatoPuntaje(r.v)}
              </text>
              {vista === "dimension" ? (
                <text x={x(r.i) + 52} y={r.yy} dominantBaseline="middle" className="tick">
                  {r.s.nombre.length > 14 ? `${r.s.nombre.slice(0, 13)}…` : r.s.nombre}
                </text>
              ) : null}
            </g>
          ))}
        </svg>
        {tip ? <Tooltip {...tip} /> : null}
      </div>
    </ChartFrame>
  );
}
