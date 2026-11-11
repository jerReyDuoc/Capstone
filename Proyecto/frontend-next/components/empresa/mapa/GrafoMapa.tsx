"use client";

/**
 * Mapa navegable de datos personales: nodos (sistemas, bases de datos y terceros) y flujos.
 *
 * - Disposición por capas en el sentido en que viajan los datos (lib/mapaDatos.ts), la misma
 *   del informe PDF y de la imagen PNG.
 * - Navegación: arrastrar para moverse (mouse o un dedo), pellizcar o Ctrl + rueda para acercar,
 *   botones de acercar, alejar y ajustar. Con el teclado: flechas para moverse, + y − para el
 *   zoom, 0 para ajustar; Tab recorre los elementos y flujos y Enter los selecciona.
 * - Los filtros atenúan lo que no cumple (se conserva el contexto) y la selección resalta los
 *   flujos del elemento elegido.
 * Los nombres que escribe la empresa se pintan como texto con React (nunca como HTML).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  ALTO_NODO, ANCHO_NODO, aplicarFiltros, calcularDisposicion, desfasesFlujos, ETIQUETA_TIPO, filtrosActivos,
  partirTexto, rutaFlujo, type FiltrosMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import s from "./mapa.module.css";

export type Seleccion = { tipo: "elemento" | "flujo"; id: number };

const COLOR_TIPO: Record<TipoElemento, { relleno: string; borde: string; texto: string }> = {
  sistema: { relleno: "#0d231b", borde: "#14d89e", texto: "#7cefc6" },
  base_datos: { relleno: "#131a34", borde: "#8fa3ff", texto: "#b8c5ff" },
  tercero: { relleno: "#28180c", borde: "#f58a4b", texto: "#ffb489" },
};
const COLOR_FLUJO = "#6f8a80";
const COLOR_SENSIBLE = "#ff5c7a";
const COLOR_INTERNACIONAL = "#f2b53f";
const COLOR_NNA = "#c4a5ff";
const COLOR_PENDIENTE = "#f2b53f";
const ZOOM_MIN = 0.2;
const ZOOM_MAX = 2.4;

interface Transformacion {
  x: number;
  y: number;
  k: number;
}

const limitar = (k: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, k));

export function GrafoMapa({
  vista,
  filtros,
  seleccion,
  onSeleccionar,
  nombrePaisDe,
}: {
  vista: VistaMapa;
  filtros: FiltrosMapa;
  seleccion: Seleccion | null;
  onSeleccionar: (s: Seleccion | null) => void;
  nombrePaisDe: (codigo: string | null) => string;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const [tamano, setTamano] = useState({ ancho: 800, alto: 520 });
  const [t, setT] = useState<Transformacion>({ x: 0, y: 0, k: 1 });
  const [arrastrando, setArrastrando] = useState(false);
  const punteros = useRef(new Map<number, { x: number; y: number }>());
  const inicio = useRef<{ t: Transformacion; x: number; y: number; distancia: number; movio: boolean } | null>(null);
  const movioRef = useRef(false);

  const lay = useMemo(() => calcularDisposicion(vista.elementos, vista.flujos), [vista.elementos, vista.flujos]);
  const desfases = useMemo(() => desfasesFlujos(vista.flujos), [vista.flujos]);
  const visibles = useMemo(() => aplicarFiltros(vista, filtros), [vista, filtros]);
  const hayFiltros = filtrosActivos(filtros) > 0;
  const porId = useMemo(() => new Map(vista.elementos.map((e) => [e.id, e])), [vista.elementos]);

  // Lo relacionado con la selección (para atenuar lo demás)
  const relacionados = useMemo(() => {
    if (!seleccion) return null;
    const elementos = new Set<number>();
    const flujos = new Set<number>();
    if (seleccion.tipo === "elemento") {
      elementos.add(seleccion.id);
      for (const f of vista.flujos) {
        if (f.origen_id === seleccion.id || f.destino_id === seleccion.id) {
          flujos.add(f.id);
          elementos.add(f.origen_id);
          elementos.add(f.destino_id);
        }
      }
    } else {
      const f = vista.flujos.find((x) => x.id === seleccion.id);
      if (f) {
        flujos.add(f.id);
        elementos.add(f.origen_id);
        elementos.add(f.destino_id);
      }
    }
    return { elementos, flujos };
  }, [seleccion, vista.flujos]);

  // Tamaño del lienzo
  useEffect(() => {
    const el = contenedor.current;
    if (!el) return;
    const medir = () => setTamano({ ancho: el.clientWidth || 800, alto: el.clientHeight || 520 });
    medir();
    const obs = typeof ResizeObserver !== "undefined" ? new ResizeObserver(medir) : null;
    obs?.observe(el);
    return () => obs?.disconnect();
  }, []);

  const ajustar = useCallback(() => {
    const margen = 32;
    const k = limitar(Math.min((tamano.ancho - margen) / Math.max(lay.ancho, 1), (tamano.alto - margen) / Math.max(lay.alto, 1), 1.15));
    setT({ k, x: (tamano.ancho - lay.ancho * k) / 2, y: (tamano.alto - lay.alto * k) / 2 });
  }, [lay.ancho, lay.alto, tamano.ancho, tamano.alto]);

  // Se ajusta al abrir y cuando cambia la forma del mapa (no en cada edición menor)
  const forma = `${lay.columnas}x${Math.round(lay.alto)}x${tamano.ancho}x${tamano.alto}`;
  useEffect(() => {
    ajustar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forma]);

  const zoomEn = useCallback((factor: number, cx?: number, cy?: number) => {
    setT((prev) => {
      const k = limitar(prev.k * factor);
      const px = cx ?? tamano.ancho / 2;
      const py = cy ?? tamano.alto / 2;
      return { k, x: px - ((px - prev.x) * k) / prev.k, y: py - ((py - prev.y) * k) / prev.k };
    });
  }, [tamano.ancho, tamano.alto]);

  // Ctrl/⌘ + rueda acerca (sin Ctrl, la rueda desplaza la página como siempre)
  useEffect(() => {
    const el = contenedor.current;
    if (!el) return;
    const rueda = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomEn(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", rueda, { passive: false });
    return () => el.removeEventListener("wheel", rueda);
  }, [zoomEn]);

  const alPresionar = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    punteros.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...punteros.current.values()];
    const distancia = pts.length >= 2 ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0;
    inicio.current = { t, x: e.clientX, y: e.clientY, distancia, movio: false };
    movioRef.current = false;
  };

  const alMover = (e: PointerEvent<HTMLDivElement>) => {
    if (!punteros.current.has(e.pointerId) || !inicio.current) return;
    punteros.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...punteros.current.values()];
    const ini = inicio.current;
    if (pts.length >= 2 && ini.distancia > 0) {
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const r = contenedor.current!.getBoundingClientRect();
      const cx = (pts[0].x + pts[1].x) / 2 - r.left;
      const cy = (pts[0].y + pts[1].y) / 2 - r.top;
      const k = limitar(ini.t.k * (d / ini.distancia));
      setT({ k, x: cx - ((cx - ini.t.x) * k) / ini.t.k, y: cy - ((cy - ini.t.y) * k) / ini.t.k });
      movioRef.current = true;
      return;
    }
    const dx = e.clientX - ini.x;
    const dy = e.clientY - ini.y;
    if (!movioRef.current && Math.hypot(dx, dy) < 5) return;
    if (!movioRef.current) {
      movioRef.current = true;
      setArrastrando(true);
      contenedor.current?.setPointerCapture(e.pointerId);
    }
    setT({ ...ini.t, x: ini.t.x + dx, y: ini.t.y + dy });
  };

  const alSoltar = (e: PointerEvent<HTMLDivElement>) => {
    punteros.current.delete(e.pointerId);
    if (contenedor.current?.hasPointerCapture(e.pointerId)) contenedor.current.releasePointerCapture(e.pointerId);
    if (punteros.current.size === 0) {
      setArrastrando(false);
      inicio.current = null;
    } else {
      const [p] = [...punteros.current.values()];
      inicio.current = { t, x: p.x, y: p.y, distancia: 0, movio: true };
    }
  };

  const alTeclado = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget && !["+", "-", "=", "0"].includes(e.key)) return;
    const paso = 48;
    const mover: Record<string, [number, number]> = {
      ArrowLeft: [paso, 0], ArrowRight: [-paso, 0], ArrowUp: [0, paso], ArrowDown: [0, -paso],
    };
    if (mover[e.key]) {
      e.preventDefault();
      const [dx, dy] = mover[e.key];
      setT((p) => ({ ...p, x: p.x + dx, y: p.y + dy }));
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      zoomEn(1.2);
    } else if (e.key === "-") {
      e.preventDefault();
      zoomEn(1 / 1.2);
    } else if (e.key === "0") {
      e.preventDefault();
      ajustar();
    } else if (e.key === "Escape") {
      onSeleccionar(null);
    }
  };

  // Un clic que fue en realidad un arrastre no selecciona
  const elegir = (sel: Seleccion | null) => {
    if (movioRef.current) return;
    onSeleccionar(sel);
  };

  const teclaItem = (sel: Seleccion) => (e: KeyboardEvent<SVGGElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      onSeleccionar(sel);
    } else if (e.key === "Escape") {
      onSeleccionar(null);
    }
  };

  const clase = (visible: boolean, relacionado: boolean | null) =>
    !visible ? s.atenuado : relacionado === false ? s.semi : undefined;

  const visiblesCount = visibles.elementos.size;

  return (
    <div
      ref={contenedor}
      className={s.lienzo}
      data-arrastrando={arrastrando || undefined}
      tabIndex={0}
      role="group"
      aria-roledescription="mapa interactivo"
      aria-label={`Mapa de datos personales con ${vista.elementos.length} elementos y ${vista.flujos.length} flujos`}
      aria-describedby="ayuda-mapa"
      onPointerDown={alPresionar}
      onPointerMove={alMover}
      onPointerUp={alSoltar}
      onPointerCancel={alSoltar}
      onKeyDown={alTeclado}
      onClick={(e) => {
        if (e.target === e.currentTarget || (e.target as Element).tagName === "svg") elegir(null);
      }}
    >
      <svg aria-hidden={false} role="presentation" style={{ fontFamily: "var(--font-body)" }}>
        <g transform={`translate(${t.x} ${t.y}) scale(${t.k})`}>
          {/* Flujos (debajo de los nodos) */}
          {vista.flujos.map((f) => {
            const o = lay.nodos.get(f.origen_id);
            const d = lay.nodos.get(f.destino_id);
            if (!o || !d) return null;
            const r = rutaFlujo(o, d, desfases.get(f.id) ?? 0, lay.pasos.get(f.id));
            const sensible = f.derivados.sensibles.length > 0;
            const color = f.derivados.internacional ? COLOR_INTERNACIONAL : sensible ? COLOR_SENSIBLE : COLOR_FLUJO;
            const sel = seleccion?.tipo === "flujo" && seleccion.id === f.id;
            const relacionado = relacionados ? relacionados.flujos.has(f.id) : null;
            const sentido = r.punta.haciaIzquierda ? 1 : -1;
            const origen = porId.get(f.origen_id)?.nombre ?? "?";
            const destino = porId.get(f.destino_id)?.nombre ?? "?";
            const etiqueta = `Flujo de ${origen} a ${destino}${f.finalidad ? `: ${f.finalidad}` : ""}${
              f.derivados.internacional ? ". Transferencia internacional" : ""}${sensible ? ". Con datos sensibles" : ""}`;
            return (
              <g
                key={`f${f.id}`}
                className={[s.flujo, clase(visibles.flujos.has(f.id), relacionado)].filter(Boolean).join(" ")}
                data-seleccionado={sel || undefined}
                role="button"
                tabIndex={visibles.flujos.has(f.id) ? 0 : -1}
                aria-label={etiqueta}
                aria-pressed={sel}
                onClick={(e) => {
                  e.stopPropagation();
                  elegir({ tipo: "flujo", id: f.id });
                }}
                onKeyDown={teclaItem({ tipo: "flujo", id: f.id })}
              >
                <title>{etiqueta}</title>
                <path className={s.golpe} d={r.d} />
                <path
                  className={s.trazo}
                  d={r.d}
                  fill="none"
                  stroke={color}
                  strokeWidth={sel ? 3.4 : sensible || f.derivados.internacional ? 2.4 : 1.7}
                  strokeDasharray={f.derivados.internacional ? "7 5" : undefined}
                  strokeLinecap="round"
                />
                <path
                  d={`M ${r.punta.x} ${r.punta.y} L ${r.punta.x + 11 * sentido} ${r.punta.y - 5.5} L ${r.punta.x + 11 * sentido} ${r.punta.y + 5.5} Z`}
                  fill={color}
                />
                {f.pendiente_revision ? <circle cx={r.medio.x} cy={r.medio.y} r={4} fill={COLOR_PENDIENTE} /> : null}
              </g>
            );
          })}

          {/* Nodos */}
          {vista.elementos.map((e) => {
            const n = lay.nodos.get(e.id);
            if (!n) return null;
            const c = COLOR_TIPO[e.tipo];
            const sel = seleccion?.tipo === "elemento" && seleccion.id === e.id;
            const relacionado = relacionados ? relacionados.elementos.has(e.id) : null;
            const sensible = e.derivados.sensibles.length > 0;
            const lineas = partirTexto(e.nombre, 25, 2);
            const pais = e.derivados.pais_efectivo;
            const marcas: { texto: string; color: string; tinta: string }[] = [];
            if (sensible) marcas.push({ texto: "SENSIBLE", color: COLOR_SENSIBLE, tinta: "#1a0208" });
            if (e.incluye_nna) marcas.push({ texto: "NNA", color: COLOR_NNA, tinta: "#160a2b" });
            let xm = ANCHO_NODO - 10;
            const etiqueta = `${ETIQUETA_TIPO[e.tipo]}: ${e.nombre}. País: ${nombrePaisDe(pais)}${sensible ? ". Trata datos sensibles" : ""}${
              e.incluye_nna ? ". Trata datos de niños, niñas o adolescentes" : ""}${e.pendiente_revision ? ". Por confirmar" : ""}`;
            return (
              <g
                key={`e${e.id}`}
                transform={`translate(${n.x} ${n.y})`}
                className={[s.nodo, clase(visibles.elementos.has(e.id), relacionado)].filter(Boolean).join(" ")}
                data-seleccionado={sel || undefined}
                role="button"
                tabIndex={visibles.elementos.has(e.id) ? 0 : -1}
                aria-label={etiqueta}
                aria-pressed={sel}
                onClick={(ev) => {
                  ev.stopPropagation();
                  elegir({ tipo: "elemento", id: e.id });
                }}
                onKeyDown={teclaItem({ tipo: "elemento", id: e.id })}
              >
                <title>{etiqueta}</title>
                <rect className={s.foco} x={-5} y={-5} width={ANCHO_NODO + 10} height={ALTO_NODO + 10} rx={15} />
                <rect
                  className={s.caja}
                  width={ANCHO_NODO}
                  height={ALTO_NODO}
                  rx={12}
                  fill={c.relleno}
                  stroke={sensible ? COLOR_SENSIBLE : c.borde}
                  strokeWidth={sensible ? 2 : 1.3}
                  strokeDasharray={e.pendiente_revision ? "5 4" : undefined}
                />
                <rect x={0} y={10} width={4} height={ALTO_NODO - 20} rx={2} fill={c.borde} />
                <text x={14} y={17} fontSize={9.5} fontWeight={700} letterSpacing="0.08em" fill={c.texto}>
                  {ETIQUETA_TIPO[e.tipo].toUpperCase()}
                </text>
                {e.pendiente_revision ? (
                  <g>
                    <circle cx={ANCHO_NODO - 13} cy={13} r={4.5} fill={COLOR_PENDIENTE} />
                  </g>
                ) : null}
                {lineas.map((linea, i) => (
                  <text key={i} x={14} y={33 + i * 14} fontSize={12.5} fontWeight={600} fill="#f1f4f3">
                    {linea}
                  </text>
                ))}
                <text x={14} y={ALTO_NODO - 8} fontSize={10.5} fontWeight={700} fill={e.derivados.fuera_de_chile ? COLOR_INTERNACIONAL : "#a9b3af"}>
                  {pais ?? "¿país?"}
                </text>
                {marcas.map((m) => {
                  const largo = m.texto.length * 6.1 + 12;
                  xm -= largo;
                  const x = xm;
                  xm -= 4;
                  return (
                    <g key={m.texto}>
                      <rect x={x} y={ALTO_NODO - 20} width={largo} height={14} rx={7} fill={m.color} />
                      <text x={x + 6} y={ALTO_NODO - 10} fontSize={8.5} fontWeight={800} fill={m.tinta}>
                        {m.texto}
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </g>
      </svg>

      {hayFiltros && visiblesCount === 0 ? (
        <div className={s.sinResultados}>
          <p>Ningún elemento cumple los filtros elegidos.</p>
        </div>
      ) : null}

      <span className={s.zoom} aria-hidden="true">{Math.round(t.k * 100)} %</span>
      <div className={s.controles} onPointerDown={(e) => e.stopPropagation()}>
        <button type="button" onClick={() => zoomEn(1.2)} aria-label="Acercar" title="Acercar">
          <Icon name="lupaMas" />
        </button>
        <button type="button" onClick={() => zoomEn(1 / 1.2)} aria-label="Alejar" title="Alejar">
          <Icon name="lupaMenos" />
        </button>
        <button type="button" onClick={ajustar} aria-label="Ajustar el mapa a la pantalla" title="Ajustar a la pantalla">
          <Icon name="ajustar" />
        </button>
      </div>
      <p id="ayuda-mapa" className={s.ayudaLienzo}>
        Arrastra para moverte · Ctrl + rueda o pellizca para acercar · Tab y Enter para elegir
      </p>
    </div>
  );
}
