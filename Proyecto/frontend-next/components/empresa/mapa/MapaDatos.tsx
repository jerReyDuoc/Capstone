"use client";

/**
 * /empresa/mapa-datos — Mapa de datos personales de la empresa.
 *
 * Qué datos personales trata la empresa, de quiénes, dónde están y con quién los comparte:
 *   Guía          los pasos recomendados para armar el mapa, cuáles están listos y el siguiente.
 *   Mapa          el diagrama primero (con filtros plegables) y, debajo, los indicadores y la
 *                 completitud. Al elegir un recuadro o una flecha se abre su ficha en una ventana
 *                 centrada (components/empresa/mapa/PanelDetalle.tsx).
 *   Inventario    las mismas piezas en tablas, con búsqueda.
 *   Riesgos       hallazgos priorizados y lo que falta completar.
 *   Sugerencias   propuestas según la evaluación y plantillas por rubro.
 *   Historial     versiones del mapa (cada cambio crea una) y la restauración.
 * Exporta a PDF (lo genera el servidor), a PNG y a CSV, y envía el informe por correo.
 *
 * Es parte del servicio contratado: sin contrato vigente, la página lo explica. Cada cambio
 * manda la versión del mapa que se está viendo; si otra pestaña guardó antes, se recarga.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { descargarBlob } from "@/lib/exportar";
import { fechaHoraChile } from "@/lib/fechas";
import {
  aceptarSugerencia, aplicarFiltros, aplicarPlantilla, cargarCatalogoMapa, cargarMapa, cargarPlantillasMapa,
  cargarSugerencias, confirmarRevision, crearElemento, crearFlujo, csvInventario, describirFiltros, descartarSugerencia,
  descargarInformeMapa, editarElemento, editarFlujo, eliminarElemento, eliminarFlujo, enviarInformeMapa, ETIQUETA_TIPO,
  filtrosActivos, mensajeError, nombrePais, plural, restablecerSugerencias, restaurarVersion, SIN_FILTROS, svgAPng,
  svgParaExportar, textoCambioMapa,
  type CatalogoMapa, type DatosElemento, type DatosFlujo, type ElementoMapa, type FiltrosMapa, type FlujoMapa,
  type PlantillaMapa, type SugerenciasApi, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import { useEspacioEmpresa } from "@/components/empresa/EspacioEmpresaContexto";
import { DialogoConfirmar, DialogoCorreo } from "./Dialogos";
import { FormElemento } from "./FormElemento";
import { FormFlujo } from "./FormFlujo";
import { GrafoMapa, type Seleccion } from "./GrafoMapa";
import { Inventario } from "./Inventario";
import { pasosGuia } from "@/lib/guiaMapa";
import { GuiaMapa } from "./GuiaMapa";
import { FichaDetalle } from "./PanelDetalle";
import { Historial, InicioMapa, Riesgos, Sugerencias } from "./Secciones";
import s from "./mapa.module.css";

type Pestana = "mapa" | "inventario" | "riesgos" | "sugerencias" | "historial";

type DialogoAbierto =
  | { tipo: "elemento"; elemento?: ElementoMapa; tipoInicial?: TipoElemento }
  | { tipo: "flujo"; flujo?: FlujoMapa; origen?: number | null; destino?: number | null }
  | { tipo: "correo" }
  | { tipo: "eliminarElemento"; elemento: ElementoMapa }
  | { tipo: "eliminarFlujo"; flujo: FlujoMapa }
  | { tipo: "plantilla"; plantilla: PlantillaMapa }
  | { tipo: "restaurar"; numero: number };

type Aviso = { tono: "ok" | "error"; texto: string } | null;

const PESTANAS: { id: Pestana; titulo: string; icono: IconName }[] = [
  { id: "mapa", titulo: "Mapa", icono: "mapa" },
  { id: "inventario", titulo: "Inventario", icono: "tabla" },
  { id: "riesgos", titulo: "Riesgos", icono: "brechas" },
  { id: "sugerencias", titulo: "Sugerencias y plantillas", icono: "chispa" },
  { id: "historial", titulo: "Historial", icono: "historial" },
];

export function MapaDatos() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const [catalogo, setCatalogo] = useState<CatalogoMapa | null>(null);
  const [vista, setVista] = useState<VistaMapa | null>(null);
  const [error, setError] = useState("");
  const [plantillas, setPlantillas] = useState<PlantillaMapa[] | null>(null);
  const [sugerencias, setSugerencias] = useState<SugerenciasApi | null>(null);
  const [errorSugerencias, setErrorSugerencias] = useState("");
  const [pestana, setPestana] = useState<Pestana>("mapa");
  const [filtros, setFiltros] = useState<FiltrosMapa>(SIN_FILTROS);
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  // La ficha (ventana centrada) se abre al elegir algo en el mapa; al cerrarla, lo elegido sigue resaltado
  const [fichaAbierta, setFichaAbierta] = useState(false);
  const [filtrosVisibles, setFiltrosVisibles] = useState(false);
  const [dialogo, setDialogo] = useState<DialogoAbierto | null>(null);
  const [aviso, setAviso] = useState<Aviso>(null);
  const [ocupado, setOcupado] = useState(false);
  const [exportando, setExportando] = useState<"" | "pdf" | "png">("");
  const menuExportar = useRef<HTMLDetailsElement>(null);
  const refPestanas = useRef<HTMLDivElement>(null);

  const listo = espacio.tipo === "listo";
  const empresa = listo ? espacio.datos.empresa.razon_social : "";
  const correoUsuario = listo ? espacio.datos.usuario.email : null;

  const sesionVencida = useCallback(
    (e: unknown) => {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace("/ingresar?motivo=sesion");
        return true;
      }
      return false;
    },
    [router],
  );

  const recargarSugerencias = useCallback(async () => {
    try {
      setErrorSugerencias("");
      setSugerencias(await cargarSugerencias());
    } catch (e) {
      if (!sesionVencida(e)) setErrorSugerencias(mensajeError(e, "No pudimos cargar las sugerencias."));
    }
  }, [sesionVencida]);

  useEffect(() => {
    if (!listo) return;
    Promise.all([cargarCatalogoMapa(), cargarMapa()])
      .then(([cat, v]) => {
        setCatalogo(cat);
        setVista(v);
      })
      .catch((e) => {
        if (!sesionVencida(e)) setError(mensajeError(e, "No pudimos cargar el mapa de datos. Inténtalo de nuevo."));
      });
    cargarPlantillasMapa().then((r) => setPlantillas(r.plantillas)).catch(() => setPlantillas([]));
    void recargarSugerencias();
  }, [listo, sesionVencida, recargarSugerencias]);

  // El menú Exportar se cierra al hacer clic fuera o con Esc
  useEffect(() => {
    const cerrarSiFuera = (e: Event) => {
      const menu = menuExportar.current;
      if (menu?.open && !menu.contains(e.target as Node)) menu.removeAttribute("open");
    };
    const conEsc = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && menuExportar.current?.open) {
        menuExportar.current.removeAttribute("open");
        menuExportar.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", cerrarSiFuera);
    document.addEventListener("keydown", conEsc);
    return () => {
      document.removeEventListener("pointerdown", cerrarSiFuera);
      document.removeEventListener("keydown", conEsc);
    };
  }, []);

  // Los avisos se van solos
  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), aviso.tono === "error" ? 9000 : 5000);
    return () => clearTimeout(t);
  }, [aviso]);

  /** Ejecuta un cambio del mapa: actualiza la vista, avisa el resultado y resuelve los conflictos. */
  const cambiar = useCallback(
    async (accion: () => Promise<VistaMapa>, opciones: { exito?: string; cerrar?: boolean; relanzar?: boolean } = {}) => {
      setOcupado(true);
      try {
        const nueva = await accion();
        setVista(nueva);
        if (opciones.cerrar !== false) setDialogo(null);
        setAviso({
          tono: "ok",
          texto: nueva.cambio === null
            ? "No había cambios que guardar."
            : textoCambioMapa(opciones.exito ?? nueva.cambio?.resumen ?? "Cambios guardados.", nueva.cambio?.actividades_afectadas),
        });
        return nueva;
      } catch (e) {
        if (sesionVencida(e)) return null;
        if (e instanceof ErrorBff && e.info.codigo === "MAPA_DESACTUALIZADO") {
          try {
            setVista(await cargarMapa());
          } catch {
            /* se informa igual */
          }
          setDialogo(null);
          setAviso({ tono: "error", texto: "El mapa cambió en otra pestaña o sesión. Cargamos la versión más reciente: revisa y vuelve a intentarlo." });
          return null;
        }
        if (opciones.relanzar) throw e;
        setAviso({ tono: "error", texto: mensajeError(e, "No pudimos guardar el cambio. Inténtalo de nuevo.") });
        return null;
      } finally {
        setOcupado(false);
      }
    },
    [sesionVencida],
  );

  const version = vista?.mapa.version ?? 0;
  const visibles = useMemo(() => (vista ? aplicarFiltros(vista, filtros) : null), [vista, filtros]);
  const nFiltros = filtrosActivos(filtros);
  const descripcionFiltros = vista ? describirFiltros(filtros, vista, catalogo) : "sin filtros";

  // Si lo elegido ya no existe (se eliminó o se restauró otra versión), se limpia la selección
  useEffect(() => {
    if (!vista || !seleccion) return;
    const existe = seleccion.tipo === "elemento"
      ? vista.elementos.some((e) => e.id === seleccion.id)
      : vista.flujos.some((f) => f.id === seleccion.id);
    if (!existe) {
      setSeleccion(null);
      setFichaAbierta(false);
    }
  }, [vista, seleccion]);

  const elegir = (sel: Seleccion | null) => {
    setSeleccion(sel);
    setFichaAbierta(Boolean(sel));
  };

  const verEnMapa = (tipo: "elemento" | "flujo", id: number) => {
    setPestana("mapa");
    setSeleccion({ tipo, id });
    setFichaAbierta(true);
    requestAnimationFrame(() => document.getElementById("zona-mapa")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const abrirEdicion = (tipo: "elemento" | "flujo", id: number) => {
    if (!vista) return;
    if (tipo === "elemento") {
      const e = vista.elementos.find((x) => x.id === id);
      if (e) setDialogo({ tipo: "elemento", elemento: e });
    } else {
      const f = vista.flujos.find((x) => x.id === id);
      if (f) setDialogo({ tipo: "flujo", flujo: f });
    }
  };

  /* ---------------------------------------------------- exportación */
  const cerrarMenu = () => menuExportar.current?.removeAttribute("open");
  const fechaArchivo = () => new Date().toISOString().slice(0, 10);

  const exportarPdf = async () => {
    cerrarMenu();
    setExportando("pdf");
    try {
      const { blob, nombre } = await descargarInformeMapa(filtros);
      descargarBlob(blob, nombre);
      setAviso({ tono: "ok", texto: "Descargamos el informe PDF del mapa." });
    } catch (e) {
      if (!sesionVencida(e)) setAviso({ tono: "error", texto: mensajeError(e, "No pudimos generar el PDF. Inténtalo de nuevo.") });
    } finally {
      setExportando("");
    }
  };

  const exportarPng = async () => {
    if (!vista) return;
    cerrarMenu();
    setExportando("png");
    try {
      const { svg, ancho, alto } = svgParaExportar(vista, filtros, { empresa, descripcionFiltros });
      const blob = await svgAPng(svg, ancho, alto, 2);
      descargarBlob(blob, `mapa_datos_personales_v${version}_${fechaArchivo()}.png`);
      setAviso({ tono: "ok", texto: "Descargamos la imagen del mapa." });
    } catch {
      setAviso({ tono: "error", texto: "Tu navegador no pudo generar la imagen. Prueba con el PDF." });
    } finally {
      setExportando("");
    }
  };

  const exportarCsv = () => {
    if (!vista || !visibles) return;
    cerrarMenu();
    const parcial = {
      elementos: vista.elementos.filter((e) => visibles.elementos.has(e.id)),
      flujos: vista.flujos.filter((f) => visibles.flujos.has(f.id)),
    };
    descargarBlob(new Blob([csvInventario(parcial, catalogo)], { type: "text/csv;charset=utf-8" }), `inventario_datos_personales_v${version}_${fechaArchivo()}.csv`);
    setAviso({ tono: "ok", texto: "Descargamos el inventario en CSV (se abre con Excel)." });
  };

  /* ---------------------------------------------------- encabezado */
  const encabezado = (
    <header className="page-head">
      <div>
        <span className="eyebrow">Privacidad</span>
        <h1 className="page-title">Mapa de datos personales</h1>
        <p className="page-sub">
          Qué datos personales trata tu empresa, de quiénes, dónde están y con quién los comparte. Es la base de tu
          registro de actividades de tratamiento.
        </p>
      </div>
      {vista && vista.elementos.length ? (
        <div className={s.acciones}>
          <button type="button" className="btn btn-primary" onClick={() => setDialogo({ tipo: "elemento" })} disabled={ocupado}>
            <Icon name="mas" />
            Agregar elemento
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setDialogo({ tipo: "flujo", origen: seleccion?.tipo === "elemento" ? seleccion.id : null })} disabled={ocupado || vista.elementos.length < 2}>
            <Icon name="flujo" />
            Agregar flujo
          </button>
          <details className={s.menuExportar} ref={menuExportar}>
            <summary className="btn btn-ghost" aria-label="Exportar o enviar el mapa">
              <Icon name="descargar" />
              {exportando ? "Generando…" : "Exportar"}
            </summary>
            <div className={s.menuLista}>
              <button type="button" className={s.menuItem} onClick={exportarPdf} disabled={Boolean(exportando)}>
                <Icon name="pdf" />
                <span>Informe PDF<small>Diagrama, inventario, riesgos y base para el registro de actividades</small></span>
              </button>
              <button type="button" className={s.menuItem} onClick={exportarPng} disabled={Boolean(exportando)}>
                <Icon name="imagen" />
                <span>Imagen PNG<small>El diagrama en alta resolución, para presentaciones</small></span>
              </button>
              <button type="button" className={s.menuItem} onClick={exportarCsv}>
                <Icon name="tabla" />
                <span>Inventario CSV<small>Para trabajarlo en Excel u otra planilla</small></span>
              </button>
              <button type="button" className={s.menuItem} onClick={() => { cerrarMenu(); setDialogo({ tipo: "correo" }); }}>
                <Icon name="correo" />
                <span>Enviar por correo<small>El informe PDF como adjunto</small></span>
              </button>
              <p className={s.menuNota}>
                {nFiltros ? `Se exporta la vista filtrada: ${descripcionFiltros}.` : "Se exporta el mapa completo."}
              </p>
            </div>
          </details>
        </div>
      ) : null}
    </header>
  );

  /* ---------------------------------------------------- estados de la página */
  if (espacio.tipo === "cargando" || (listo && !vista && !error)) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="skeleton" style={{ height: 120 }} role="status" aria-label="Cargando el mapa de datos" />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    );
  }
  if (espacio.tipo === "error" || error) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="callout" role="alert">
          <Icon name="alerta" />
          <span>{espacio.tipo === "error" ? espacio.mensaje : error}</span>
        </div>
      </div>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <div className={s.pagina}>
        {encabezado}
        <p className="callout" role="status">
          <Icon name="candado" />
          <span>
            El mapa de datos es parte del servicio contratado y el de tu empresa no está activo.{" "}
            {espacio.contrato.contrato.documentos_disponibles ? (
              <>Tus documentos siguen disponibles en <Link href="/empresa/documentos">Mis documentos</Link>.</>
            ) : (
              "Contacta a Therion Labs para renovarlo."
            )}
          </span>
        </p>
      </div>
    );
  }
  if (!vista || !catalogo) return null;

  const r = vista.resumen;
  const vacio = vista.elementos.length === 0;
  const graves = vista.conteo_hallazgos["Crítica"] + vista.conteo_hallazgos["Alta"];
  const terceros = vista.elementos.filter((e) => e.tipo === "tercero").sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));

  const kpis: { etiqueta: string; valor: number | string; pie?: string; icono: IconName; tono?: "alerta" | "aviso" }[] = [
    { etiqueta: "Sistemas", valor: r.sistemas, icono: "sistemaApp" },
    { etiqueta: "Bases de datos", valor: r.bases_datos, icono: "baseDatos" },
    { etiqueta: "Terceros", valor: r.terceros, icono: "empresa", pie: `${plural(r.flujos_a_terceros, "flujo recibido", "flujos recibidos")}` },
    { etiqueta: "Flujos", valor: r.flujos, icono: "flujo" },
    {
      etiqueta: "Transferencias internacionales", valor: r.transferencias_internacionales, icono: "globo",
      pie: r.transferencias_sin_garantia ? `${r.transferencias_sin_garantia} sin garantía` : r.transferencias_internacionales ? "todas con garantía" : undefined,
      tono: r.transferencias_sin_garantia ? "aviso" : undefined,
    },
    { etiqueta: "Con datos sensibles", valor: r.elementos_con_sensibles, icono: "candado", pie: "elementos" },
    { etiqueta: "Con datos de NNA", valor: r.elementos_con_nna, icono: "usuario", pie: "elementos" },
    { etiqueta: "Riesgos críticos o altos", valor: graves, icono: "brechas", tono: graves ? "alerta" : undefined },
  ];

  const resumenMapa = (
    <section className={s.resumenMapa} aria-labelledby="titulo-resumen-mapa">
      <div className={s.seccionCabeza}>
        <h2 id="titulo-resumen-mapa">Resumen del mapa</h2>
        <span className="card-sub">
          Versión {vista.mapa.version}
          {vista.mapa.fecha_actualizacion ? ` · actualizado ${fechaHoraChile(vista.mapa.fecha_actualizacion)}` : ""}
        </span>
      </div>
      <div className={s.kpis}>
        {kpis.map((k) => (
          <div key={k.etiqueta} className={s.kpi} data-tono={k.tono}>
            <span className={s.kpiEtiqueta}><Icon name={k.icono} />{k.etiqueta}</span>
            <span className={s.kpiValor}>{k.valor}</span>
            {k.pie ? <span className={s.kpiPie}>{k.pie}</span> : null}
          </div>
        ))}
      </div>
      <div className={s.completitud}>
        <div className={s.completitudFila}>
          <span className="card-sub">
            <strong style={{ color: "var(--text)" }}>Completitud del mapa: {vista.completitud.porcentaje} %</strong>
            {r.pendientes_revision ? ` · ${plural(r.pendientes_revision, "registro por confirmar", "registros por confirmar")}` : ""}
          </span>
          {vista.completitud.pendientes.length ? (
            <button type="button" className="link-btn" onClick={() => setPestana("riesgos")}>Ver qué falta</button>
          ) : null}
        </div>
        <div className={s.barra} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={vista.completitud.porcentaje} aria-label="Completitud del mapa">
          <span style={{ width: `${vista.completitud.porcentaje}%` }} />
        </div>
      </div>
    </section>
  );

  const contadorPestana = (id: Pestana) => {
    if (id === "riesgos" && vista.hallazgos.length) return { n: vista.hallazgos.length, tono: graves ? "alerta" : undefined };
    if (id === "sugerencias" && sugerencias?.sugerencias.length) return { n: sugerencias.sugerencias.length, tono: undefined };
    return null;
  };

  const moverPestana = (e: KeyboardEvent, actual: Pestana) => {
    const i = PESTANAS.findIndex((p) => p.id === actual);
    const destino = e.key === "ArrowRight" ? (i + 1) % PESTANAS.length : e.key === "ArrowLeft" ? (i - 1 + PESTANAS.length) % PESTANAS.length : -1;
    if (destino < 0) return;
    e.preventDefault();
    setPestana(PESTANAS[destino].id);
    refPestanas.current?.querySelectorAll<HTMLButtonElement>("[role=tab]")[destino]?.focus();
  };

  return (
    <div className={s.pagina}>
      {encabezado}

      {vacio && pestana !== "sugerencias" ? (
        <InicioMapa
          plantillas={plantillas}
          sugerencias={sugerencias}
          ocupado={ocupado}
          onPlantilla={(p) => setDialogo({ tipo: "plantilla", plantilla: p })}
          onVerSugerencias={() => setPestana("sugerencias")}
          onAgregar={() => setDialogo({ tipo: "elemento" })}
        />
      ) : (
        <>
          {!vacio ? (
            <GuiaMapa
              pasos={pasosGuia(vista)}
              onAccion={(a) => {
                if (a === "agregar_sistema") setDialogo({ tipo: "elemento", tipoInicial: "sistema" });
                else if (a === "agregar_tercero") setDialogo({ tipo: "elemento", tipoInicial: "tercero" });
                else if (a === "agregar_flujo") setDialogo({ tipo: "flujo" });
                else if (a === "ver_riesgos") setPestana("riesgos");
              }}
            />
          ) : null}

          <div className={s.pestanas} role="tablist" aria-label="Secciones del mapa" ref={refPestanas}>
            {PESTANAS.map((p) => {
              const c = contadorPestana(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  id={`tab-${p.id}`}
                  aria-selected={pestana === p.id}
                  aria-controls={`panel-${p.id}`}
                  tabIndex={pestana === p.id ? 0 : -1}
                  className={s.pestana}
                  onClick={() => setPestana(p.id)}
                  onKeyDown={(e) => moverPestana(e, p.id)}
                >
                  <Icon name={p.icono} />
                  {p.titulo}
                  {c ? <span className={s.contador} data-tono={c.tono}>{c.n}</span> : null}
                </button>
              );
            })}
          </div>

          <div role="tabpanel" id={`panel-${pestana}`} aria-labelledby={`tab-${pestana}`}>
            {pestana === "inventario" && !vacio ? (
              <BarraFiltros catalogo={catalogo} vista={vista} filtros={filtros} terceros={terceros} visibles={visibles} onCambiar={setFiltros} />
            ) : null}

            {pestana === "mapa" ? (
              vacio ? (
                <p className="callout"><Icon name="info" /><span>Tu mapa está vacío. Agrega un elemento o usa una plantilla.</span></p>
              ) : (
                <div style={{ display: "grid", gap: 20, marginTop: 16 }}>
                  <section id="zona-mapa" className={s.tarjetaMapa} aria-label="Diagrama del mapa" style={{ scrollMarginTop: 16 }}>
                    <div className={s.mapaBarra}>
                      <p className={s.mapaPista}>
                        <Icon name="info" />
                        <span>
                          <strong>Haz clic en un recuadro o en una flecha</strong> para ver su ficha completa. Arrastra para
                          moverte y usa los botones + y − para acercar.
                        </span>
                      </p>
                      <div className={s.mapaBarraAcciones}>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setFiltrosVisibles((v) => !v)}
                          aria-expanded={filtrosVisibles}
                          aria-controls="filtros-mapa"
                        >
                          <Icon name="filtro" />
                          {filtrosVisibles ? "Ocultar filtros" : "Filtrar"}
                          {nFiltros ? <span className={s.contador} data-tono="acento">{nFiltros}</span> : null}
                        </button>
                        {nFiltros ? (
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setFiltros(SIN_FILTROS)}>
                            <Icon name="cerrar" />
                            Quitar filtros
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {filtrosVisibles ? (
                      <div id="filtros-mapa">
                        <BarraFiltros catalogo={catalogo} vista={vista} filtros={filtros} terceros={terceros} visibles={visibles} onCambiar={setFiltros} compacta />
                      </div>
                    ) : nFiltros ? (
                      <p className={s.filtroResumen} aria-live="polite">Filtrando por {descripcionFiltros}: lo demás queda atenuado.</p>
                    ) : null}
                    <GrafoMapa
                      vista={vista}
                      filtros={filtros}
                      seleccion={seleccion}
                      onSeleccionar={elegir}
                      nombrePaisDe={(c) => nombrePais(catalogo, c)}
                    />
                    <Leyenda />
                  </section>
                  {resumenMapa}
                </div>
              )
            ) : null}

            {pestana === "inventario" ? (
              <div style={{ marginTop: 16 }}>
                <Inventario
                  catalogo={catalogo}
                  vista={vista}
                  filtros={filtros}
                  ocupado={ocupado}
                  onVer={verEnMapa}
                  onAbrir={(tipo, id) => elegir({ tipo, id })}
                  onAgregar={(t) => setDialogo({ tipo: "elemento", tipoInicial: t })}
                  onAgregarFlujo={() => setDialogo({ tipo: "flujo" })}
                  onEditarElemento={(e) => setDialogo({ tipo: "elemento", elemento: e })}
                  onEditarFlujo={(f) => setDialogo({ tipo: "flujo", flujo: f })}
                  onEliminarElemento={(e) => setDialogo({ tipo: "eliminarElemento", elemento: e })}
                  onEliminarFlujo={(f) => setDialogo({ tipo: "eliminarFlujo", flujo: f })}
                />
              </div>
            ) : null}

            {pestana === "riesgos" ? (
              <div style={{ marginTop: 8 }}>
                <Riesgos
                  vista={vista}
                  ocupado={ocupado}
                  onVer={verEnMapa}
                  onCompletar={abrirEdicion}
                  onConfirmarTodo={() => void cambiar(() => confirmarRevision(version, { todo: true }))}
                />
              </div>
            ) : null}

            {pestana === "sugerencias" ? (
              <div style={{ marginTop: 8 }}>
                <Sugerencias
                  sugerencias={sugerencias}
                  plantillas={plantillas}
                  cargando={!sugerencias && !errorSugerencias}
                  error={errorSugerencias}
                  ocupado={ocupado}
                  onAceptar={async (sug, origenId) => {
                    const nueva = await cambiar(() => aceptarSugerencia(sug.clave, version, origenId));
                    if (nueva) {
                      await recargarSugerencias();
                      const nuevo = nueva.elementos.find((e) => sug.elementos.some((x) => x.clave === e.clave));
                      if (nuevo) setSeleccion({ tipo: "elemento", id: nuevo.id });
                    }
                  }}
                  onDescartar={async (sug) => {
                    try {
                      setSugerencias(await descartarSugerencia(sug.clave));
                      setAviso({ tono: "ok", texto: "Descartamos la sugerencia. Puedes volver a mostrarla cuando quieras." });
                    } catch (e) {
                      if (!sesionVencida(e)) setAviso({ tono: "error", texto: mensajeError(e, "No pudimos descartar la sugerencia.") });
                    }
                  }}
                  onRestablecer={async () => {
                    try {
                      setSugerencias(await restablecerSugerencias());
                    } catch (e) {
                      if (!sesionVencida(e)) setAviso({ tono: "error", texto: mensajeError(e, "No pudimos volver a mostrar las sugerencias.") });
                    }
                  }}
                  onAplicarPlantilla={(p) => setDialogo({ tipo: "plantilla", plantilla: p })}
                />
              </div>
            ) : null}

            {pestana === "historial" ? (
              <div style={{ marginTop: 16 }}>
                <Historial versionActual={version} ocupado={ocupado} onRestaurar={(n) => setDialogo({ tipo: "restaurar", numero: n })} />
              </div>
            ) : null}
          </div>
        </>
      )}

      {/* ---------------------------------------------------- ficha y diálogos */}
      {fichaAbierta && seleccion && !dialogo ? (
        <FichaDetalle
          catalogo={catalogo}
          vista={vista}
          seleccion={seleccion}
          ocupado={ocupado}
          onSeleccionar={(sel) => {
            setSeleccion(sel);
            if (!sel) setFichaAbierta(false);
          }}
          onCerrar={() => setFichaAbierta(false)}
          onEditarElemento={(e) => setDialogo({ tipo: "elemento", elemento: e })}
          onEditarFlujo={(f) => setDialogo({ tipo: "flujo", flujo: f })}
          onNuevoFlujo={(o, d) => setDialogo({ tipo: "flujo", origen: o, destino: d })}
          onEliminarElemento={(e) => setDialogo({ tipo: "eliminarElemento", elemento: e })}
          onEliminarFlujo={(f) => setDialogo({ tipo: "eliminarFlujo", flujo: f })}
          onConfirmar={(sel) =>
            void cambiar(() => confirmarRevision(version, sel.tipo === "elemento" ? { elementos: [sel.id] } : { flujos: [sel.id] }), {
              exito: "Marcado como revisado.",
            })
          }
        />
      ) : null}
      {dialogo?.tipo === "elemento" ? (
        <FormElemento
          catalogo={catalogo}
          elemento={dialogo.elemento}
          tipoInicial={dialogo.tipoInicial}
          onCerrar={() => setDialogo(null)}
          onGuardar={async (datos: DatosElemento) => {
            const editado = dialogo.elemento;
            const nueva = await cambiar(() => (editado ? editarElemento(editado.id, version, datos) : crearElemento(version, datos)), { relanzar: true });
            if (nueva && !editado) {
              const creado = nueva.elementos.find((e) => e.nombre === datos.nombre && e.tipo === datos.tipo);
              if (creado) setSeleccion({ tipo: "elemento", id: creado.id });
              if (pestana !== "mapa" && pestana !== "inventario") setPestana("mapa");
            }
          }}
        />
      ) : null}
      {dialogo?.tipo === "flujo" ? (
        <FormFlujo
          catalogo={catalogo}
          vista={vista}
          flujo={dialogo.flujo}
          origenInicial={dialogo.origen}
          destinoInicial={dialogo.destino}
          onCerrar={() => setDialogo(null)}
          onGuardar={async (datos: DatosFlujo) => {
            const editado = dialogo.flujo;
            const nueva = await cambiar(() => (editado ? editarFlujo(editado.id, version, datos) : crearFlujo(version, datos)), { relanzar: true });
            if (nueva && !editado) {
              const creado = [...nueva.flujos].reverse().find((f) => f.origen_id === datos.origen_id && f.destino_id === datos.destino_id);
              if (creado) setSeleccion({ tipo: "flujo", id: creado.id });
            }
          }}
        />
      ) : null}
      {dialogo?.tipo === "eliminarElemento" ? (
        <DialogoConfirmar
          titulo={`¿Eliminar «${dialogo.elemento.nombre}»?`}
          textoConfirmar="Eliminar"
          peligro
          onCerrar={() => setDialogo(null)}
          onConfirmar={async () => {
            await cambiar(() => eliminarElemento(dialogo.elemento.id, version));
          }}
        >
          <p>
            Se quitará del mapa {ETIQUETA_TIPO[dialogo.elemento.tipo].toLowerCase() === "tercero" ? "este tercero" : "este elemento"}
            {(() => {
              const n = vista.flujos.filter((f) => f.origen_id === dialogo.elemento.id || f.destino_id === dialogo.elemento.id).length;
              return n ? ` junto con ${plural(n, "flujo", "flujos")} que lo conecta${n === 1 ? "" : "n"}` : "";
            })()}
            .
          </p>
          <p>Queda registrado en el historial: si te equivocas, puedes volver a la versión anterior.</p>
        </DialogoConfirmar>
      ) : null}
      {dialogo?.tipo === "eliminarFlujo" ? (
        <DialogoConfirmar
          titulo="¿Eliminar este flujo?"
          textoConfirmar="Eliminar flujo"
          peligro
          onCerrar={() => setDialogo(null)}
          onConfirmar={async () => {
            await cambiar(() => eliminarFlujo(dialogo.flujo.id, version));
          }}
        >
          <p>
            {vista.elementos.find((e) => e.id === dialogo.flujo.origen_id)?.nombre} →{" "}
            {vista.elementos.find((e) => e.id === dialogo.flujo.destino_id)?.nombre}
            {dialogo.flujo.finalidad ? ` (${dialogo.flujo.finalidad})` : ""}
          </p>
          <p>Queda registrado en el historial del mapa.</p>
        </DialogoConfirmar>
      ) : null}
      {dialogo?.tipo === "plantilla" ? (
        <DialogoConfirmar
          titulo={`¿Usar la plantilla «${dialogo.plantilla.nombre}»?`}
          textoConfirmar="Agregar al mapa"
          icono="lista"
          onCerrar={() => setDialogo(null)}
          onConfirmar={async () => {
            const nueva = await cambiar(() => aplicarPlantilla(dialogo.plantilla.codigo, version));
            if (nueva) {
              setPestana("mapa");
              void recargarSugerencias();
            }
          }}
        >
          <p>
            Agregaremos hasta {plural(dialogo.plantilla.sistemas + dialogo.plantilla.bases_datos + dialogo.plantilla.terceros, "elemento", "elementos")} y{" "}
            {plural(dialogo.plantilla.flujos, "flujo", "flujos")} típicos del rubro. Lo que ya tengas con el mismo nombre no se duplica.
          </p>
          <p>
            Todo quedará <strong>por confirmar</strong>: revisa cada elemento, ajusta los países, proveedores y responsables, y elimina
            lo que no aplique a tu empresa.
          </p>
        </DialogoConfirmar>
      ) : null}
      {dialogo?.tipo === "restaurar" ? (
        <DialogoConfirmar
          titulo={`¿Volver a la versión ${dialogo.numero}?`}
          textoConfirmar="Volver a esta versión"
          icono="historial"
          onCerrar={() => setDialogo(null)}
          onConfirmar={async () => {
            const nueva = await cambiar(() => restaurarVersion(dialogo.numero, version));
            if (nueva) setPestana("mapa");
          }}
        >
          <p>El mapa quedará como estaba en la versión {dialogo.numero}.</p>
          <p>No se pierde nada: la restauración crea una versión nueva y la actual sigue en el historial.</p>
        </DialogoConfirmar>
      ) : null}
      {dialogo?.tipo === "correo" ? (
        <DialogoCorreo
          correoUsuario={correoUsuario}
          descripcionFiltros={descripcionFiltros}
          onCerrar={() => setDialogo(null)}
          onEnviar={async (email) => {
            try {
              const r2 = await enviarInformeMapa(email, filtros);
              setDialogo(null);
              setAviso({ tono: "ok", texto: `Enviamos el informe a ${r2.destino}.` });
              return r2.destino;
            } catch (e) {
              if (sesionVencida(e)) return "";
              throw new Error(mensajeError(e, "No pudimos enviar el correo. Inténtalo de nuevo o descarga el PDF."));
            }
          }}
        />
      ) : null}

      {aviso ? (
        <div className={s.aviso} data-tono={aviso.tono} role={aviso.tono === "error" ? "alert" : "status"}>
          <Icon name={aviso.tono === "error" ? "alerta" : "check"} />
          <span>{aviso.texto}</span>
          <button type="button" className="icon-btn" onClick={() => setAviso(null)} aria-label="Cerrar aviso">
            <Icon name="cerrar" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

/* ============================================================ filtros y leyenda */

function BarraFiltros({
  catalogo,
  vista,
  filtros,
  terceros,
  visibles,
  onCambiar,
  compacta = false,
}: {
  catalogo: CatalogoMapa;
  vista: VistaMapa;
  filtros: FiltrosMapa;
  terceros: ElementoMapa[];
  visibles: { elementos: Set<number>; flujos: Set<number> } | null;
  onCambiar: (f: FiltrosMapa) => void;
  /** Dentro de la tarjeta del mapa: sin marco propio. */
  compacta?: boolean;
}) {
  const paises = vista.resumen.paises;
  const n = filtrosActivos(filtros);
  const chip = (clave: "sensibles" | "nna" | "internacional", texto: string, color: string) => (
    <button
      type="button"
      className="chip"
      aria-pressed={filtros[clave]}
      onClick={() => onCambiar({ ...filtros, [clave]: !filtros[clave] })}
    >
      <span className="chip-swatch" style={{ background: color }} />
      {texto}
    </button>
  );
  return (
    <div className={compacta ? s.filtrosCompactos : "card"} style={compacta ? undefined : { display: "grid", gap: 12, padding: "var(--sp-4)" }} role="search" aria-label="Filtros del mapa">
      <div className={s.filtros}>
        <div className="field">
          <span className="field-label" id="filtros-rapidos"><Icon name="filtro" width={14} height={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />Mostrar</span>
          <div className={s.filtrosChips} role="group" aria-labelledby="filtros-rapidos">
            {chip("sensibles", "Datos sensibles", "var(--critico)")}
            {chip("nna", "Niños, niñas y adolescentes", "#c4a5ff")}
            {chip("internacional", "Transferencias internacionales", "var(--medio)")}
          </div>
        </div>
        <div className={`field ${s.filtroSelect}`}>
          <label className="field-label" htmlFor="filtro-tercero">Tercero</label>
          <select id="filtro-tercero" className="select" value={filtros.tercero ?? ""} onChange={(e) => onCambiar({ ...filtros, tercero: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Todos</option>
            {terceros.map((t) => (
              <option key={t.id} value={t.id}>{t.nombre}</option>
            ))}
          </select>
        </div>
        <div className={`field ${s.filtroSelect}`}>
          <label className="field-label" htmlFor="filtro-pais">País</label>
          <select id="filtro-pais" className="select" value={filtros.pais ?? ""} onChange={(e) => onCambiar({ ...filtros, pais: e.target.value || null })}>
            <option value="">Todos</option>
            {paises.map((p) => (
              <option key={p.codigo} value={p.codigo}>{p.nombre} ({p.elementos})</option>
            ))}
          </select>
        </div>
        <div className={`field ${s.filtroSelect}`}>
          <label className="field-label" htmlFor="filtro-tipo">Tipo</label>
          <select id="filtro-tipo" className="select" value={filtros.tipo ?? ""} onChange={(e) => onCambiar({ ...filtros, tipo: (e.target.value || null) as TipoElemento | null })}>
            <option value="">Todos</option>
            <option value="sistema">Sistemas</option>
            <option value="base_datos">Bases de datos</option>
            <option value="tercero">Terceros</option>
          </select>
        </div>
        {n && !compacta ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onCambiar(SIN_FILTROS)}>
            <Icon name="cerrar" />
            Quitar filtros ({n})
          </button>
        ) : null}
      </div>
      <p className={s.filtroResumen} aria-live="polite">
        {n && visibles
          ? `Mostrando ${plural(visibles.elementos.size, "elemento", "elementos")} de ${vista.elementos.length} y ${plural(visibles.flujos.size, "flujo", "flujos")} de ${vista.flujos.length}. Lo demás queda atenuado. Filtra por ${describirFiltros(filtros, vista, catalogo)}.`
          : `${plural(vista.elementos.length, "elemento", "elementos")} y ${plural(vista.flujos.length, "flujo", "flujos")} en el mapa.`}
      </p>
    </div>
  );
}

function Leyenda() {
  return (
    <div className={s.leyenda} aria-label="Leyenda del mapa">
      <span><i className={s.muestra} style={{ borderColor: "#14d89e", background: "#0d231b" }} />Sistema</span>
      <span><i className={s.muestra} style={{ borderColor: "#8fa3ff", background: "#131a34" }} />Base de datos</span>
      <span><i className={s.muestra} style={{ borderColor: "#f58a4b", background: "#28180c" }} />Tercero</span>
      <span><i className={s.linea} style={{ borderColor: "#6f8a80" }} />Flujo</span>
      <span><i className={s.linea} style={{ borderColor: "#ff5c7a" }} />Con datos sensibles</span>
      <span><i className={s.lineaPunteada} style={{ borderColor: "#f2b53f" }} />Transferencia internacional</span>
      <span><i className={s.muestra} style={{ borderColor: "#a9b3af", borderStyle: "dashed" }} />Por confirmar</span>
    </div>
  );
}
