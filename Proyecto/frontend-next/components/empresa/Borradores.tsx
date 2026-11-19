"use client";

/**
 * /empresa/borradores — Generador de reportes y documentos.
 *
 * Mejoras 19-11: la página pasa de un formulario simple a un generador con tarjetas, vista previa
 * lateral e historial, SIN quitar nada de lo que ya hacía (HU-16):
 *
 *   C1  Elegir el documento (Política de uso de IA, Aviso de privacidad, Evaluación de impacto) y
 *       generarlo; se edita en Markdown y se descarga en Markdown o PDF.
 *   C2  El backend lo ajusta a la Ley 21.719 y a las brechas y dimensiones de la evaluación más
 *       reciente; con "Adaptar con el Agente IA" además lo redacta para el rubro y las
 *       instrucciones de la empresa. Límite de borradores en revisión y cuota diaria de IA.
 *   C3  Revisión y edición (vista previa y campos [COMPLETAR] pendientes), descarga previa y, al
 *       final, "Marcar como final" (consolidar): queda de solo lectura y su PDF pasa a Mis documentos.
 *
 * Nuevo:
 *   - Tarjetas de documentos que se generan con IA y de los REPORTES que la plataforma ya genera en
 *     otras secciones (reporte ejecutivo, informe de brechas, registro de actividades, RoPA y
 *     revisión interna): se descargan aquí o se abre su sección, sin duplicar lógica.
 *   - Panel lateral "Vista previa" con "Ver completo" y "Exportar" (en celular queda debajo).
 *   - "Documentos generados": historial con fecha, formato y estado (Borrador / Final); abrir,
 *     descargar o eliminar.
 *   - Desde una brecha del Plan de acción (?plantilla=…&brecha=ID) se llega con el documento que
 *     ayuda a cerrarla ya elegido; esa relación se ve en el historial (lib/generadorDocumentos.ts).
 *
 * La vista previa pinta el Markdown como texto con React (lib/borradores.ts): lo que escribe el
 * usuario nunca se inserta como HTML. HU-30: sin contrato vigente la página lo explica.
 */
import { BotonConMotivo } from "@/components/ui/BotonConMotivo";
import { Icon } from "@/components/ui/Icon";
import { InfoTip } from "@/components/ui/InfoTip";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { descargarInformePdf } from "@/lib/api";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { fechaCorta } from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import {
  advertenciasVisibles, cargarBorrador, cargarCatalogoBorradores, consolidarBorrador, cuotaBorradoresTexto,
  actividadesPiaIniciales, descargarBorrador, descartarBorrador, ETIQUETA_TIPO, generarBorrador,
  guardarBorrador, MAX_ACTIVIDADES_PIA, textoRegistroBorrador,
  listarBorradores, parsearMarkdown, pendientesDe, segmentos, siguientePendiente, validarContenido,
  type BloqueMd, type BorradorApi, type CatalogoBorradoresApi, type FormatoBorrador, type PlantillaApi, type TipoBorrador,
} from "@/lib/borradores";
import {
  ESTADO_HISTORIAL, FORMATOS_DOCUMENTO, guardarRelacion, hrefVolverABrecha, leerBrechaPendiente, leerRelaciones,
  PRESENTACION_PLANTILLA, REPORTES, type BrechaRelacionada, type ReporteDisponible,
} from "@/lib/generadorDocumentos";
import { TONO_RIESGO } from "@/lib/registroActividades";
import { useEspacioEmpresa } from "./EspacioEmpresaContexto";
import s from "@/components/ui/comunes.module.css";
import b from "./borradores.module.css";

type Carga = { tipo: "cargando" } | { tipo: "listo" } | { tipo: "error"; mensaje: string };

/** Lo que muestra el panel de vista previa. */
type Seleccion =
  | { tipo: "plantilla"; plantilla: TipoBorrador }
  | { tipo: "reporte"; reporte: ReporteDisponible["id"] }
  | { tipo: "documento"; id: number };

function mensaje(e: unknown, porDefecto: string): string {
  return e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : porDefecto;
}

/** En pantallas angostas la vista previa queda debajo: se lleva la vista hasta ella. */
function irAVistaPrevia() {
  if (typeof window === "undefined" || window.matchMedia("(min-width: 1100px)").matches) return;
  requestAnimationFrame(() => document.getElementById("vista-previa-documento")?.scrollIntoView({ block: "start", behavior: "smooth" }));
}

export function Borradores() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const [catalogo, setCatalogo] = useState<CatalogoBorradoresApi | null>(null);
  const [lista, setLista] = useState<BorradorApi[]>([]);
  const [abierto, setAbierto] = useState<BorradorApi | null>(null);
  const [aviso, setAviso] = useState("");
  const [error, setError] = useState("");
  // Mejoras 19-11: tarjeta o documento seleccionado, formulario abierto y brecha de origen
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  const [previa, setPrevia] = useState<BorradorApi | null>(null);
  const [cargandoPrevia, setCargandoPrevia] = useState(false);
  const [formTipo, setFormTipo] = useState<TipoBorrador | null>(null);
  const [generando, setGenerando] = useState(false);
  const [brecha, setBrecha] = useState<BrechaRelacionada | null>(null);
  const [relaciones, setRelaciones] = useState<Record<number, BrechaRelacionada>>({});
  const refForm = useRef<HTMLDivElement>(null);

  const recargarLista = useCallback(async () => {
    setLista((await listarBorradores()).items);
  }, []);

  useEffect(() => {
    if (espacio.tipo !== "listo") return;
    Promise.all([cargarCatalogoBorradores(), listarBorradores()])
      .then(([cat, l]) => {
        setCatalogo(cat);
        setLista(l.items);
        setCarga({ tipo: "listo" });
        // Desde Mi empresa, el registro o una brecha: ?plantilla=pia&actividad=ID / ?plantilla=…&brecha=ID
        const q = new URLSearchParams(window.location.search);
        const pedida = cat.plantillas.find((p) => p.tipo === q.get("plantilla"))?.tipo ?? null;
        const idBrecha = Number(q.get("brecha"));
        setBrecha(leerBrechaPendiente(Number.isInteger(idBrecha) && idBrecha > 0 ? idBrecha : null));
        setRelaciones(leerRelaciones());
        if (pedida) {
          setSeleccion({ tipo: "plantilla", plantilla: pedida });
          setFormTipo(pedida);
        } else if (cat.plantillas[0]) {
          setSeleccion({ tipo: "plantilla", plantilla: cat.plantillas[0].tipo });
        }
      })
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
        }
        setCarga({ tipo: "error", mensaje: mensaje(e, "No pudimos cargar tus documentos. Inténtalo de nuevo.") });
      });
  }, [espacio.tipo, router]);

  const informar = (texto: string, esError = false) => {
    setAviso(esError ? "" : texto);
    setError(esError ? texto : "");
  };

  async function abrir(id: number) {
    try {
      const doc = (await cargarBorrador(id)).borrador;
      setAbierto(doc);
      setPrevia(doc);
      setSeleccion({ tipo: "documento", id });
      requestAnimationFrame(() => document.getElementById("editor-borrador")?.scrollIntoView({ block: "start" }));
    } catch (e) {
      informar(mensaje(e, "No pudimos abrir el documento. Inténtalo de nuevo."), true);
    }
  }

  async function verPrevia(id: number) {
    setSeleccion({ tipo: "documento", id });
    irAVistaPrevia();
    if (previa?.id === id && previa.contenido !== undefined) return;
    setCargandoPrevia(true);
    try {
      setPrevia((await cargarBorrador(id)).borrador);
    } catch (e) {
      setPrevia(null);
      informar(mensaje(e, "No pudimos cargar la vista previa."), true);
    } finally {
      setCargandoPrevia(false);
    }
  }

  async function exportar(doc: Pick<BorradorApi, "id" | "tipo">, formato: FormatoBorrador) {
    try {
      const { blob, nombre } = await descargarBorrador(doc.id, formato);
      descargarBlob(blob, nombre);
      informar(`Listo: descargamos ${nombre}.`);
    } catch (e) {
      informar(mensaje(e, "No pudimos descargar el documento. Inténtalo de nuevo."), true);
    }
  }

  const abrirFormulario = (tipo: TipoBorrador) => {
    setSeleccion({ tipo: "plantilla", plantilla: tipo });
    setFormTipo(tipo);
    requestAnimationFrame(() => refForm.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  };

  const encabezado = (
    <header className="page-head">
      <div>
        <span className="eyebrow">Mi empresa</span>
        <h1 className="page-title">Generador de reportes y documentos</h1>
        <p className="page-sub">
          Genera con IA los documentos que te ayudan a cerrar tus brechas (política de uso de IA, aviso de privacidad,
          evaluación de impacto), ajustados a la Ley 21.719 y a tu última evaluación, y descarga los reportes de tu
          empresa. Revisa cada documento antes de dejarlo como final.
        </p>
      </div>
    </header>
  );

  if (espacio.tipo === "cargando" || (espacio.tipo === "listo" && carga.tipo === "cargando")) {
    return (
      <>
        {encabezado}
        <div className="skeleton" style={{ height: 240 }} role="status" aria-label="Cargando tus documentos" />
      </>
    );
  }
  if (espacio.tipo === "error" || carga.tipo === "error") {
    return (
      <>
        {encabezado}
        <div className={s.alerta} role="alert">
          <strong>{espacio.tipo === "error" ? espacio.mensaje : carga.tipo === "error" ? carga.mensaje : ""}</strong>
        </div>
      </>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <>
        {encabezado}
        <p className="callout" role="status">
          El generador de documentos es parte del servicio contratado y el de tu empresa no está activo.{" "}
          {espacio.contrato.contrato.documentos_disponibles ? (
            <>Tus documentos finales siguen en <Link href="/empresa/documentos">Mis documentos</Link>.</>
          ) : (
            "Contacta a Therion Labs para renovarlo."
          )}
        </p>
      </>
    );
  }

  const evaluaciones = espacio.tipo === "listo" ? espacio.datos.evaluaciones : [];
  const ultimaCompletada = [...evaluaciones].filter((e) => e.completada).sort((x, y) => y.id - x.id)[0] ?? null;
  const enRevision = lista.filter((x) => x.estado === "en_revision").length;
  const plantillaSel = seleccion?.tipo === "plantilla" ? catalogo?.plantillas.find((p) => p.tipo === seleccion.plantilla) ?? null : null;
  const reporteSel = seleccion?.tipo === "reporte" ? REPORTES.find((r) => r.id === seleccion.reporte) ?? null : null;
  const documentoSel = seleccion?.tipo === "documento" ? lista.find((x) => x.id === seleccion.id) ?? null : null;

  return (
    <>
      {encabezado}

      {brecha ? (
        <div className={`callout ${b.brechaOrigen}`} role="status">
          <Icon name="brechas" className="icono-estado" />
          <span>
            Vas a generar un documento para cerrar la brecha <strong>#{brecha.prioridad}</strong> de tu plan de acción:{" "}
            «{brecha.descripcion.replace(/[.\s]+$/, "")}». Ya elegimos el documento que más ayuda; puedes cambiarlo.{" "}
            <Link href={hrefVolverABrecha(brecha)}>Volver a la brecha</Link>
          </span>
        </div>
      ) : null}

      <div className={b.generador}>
        <div className={b.principal}>
          {/* ---------------- Documentos para cerrar brechas (con IA) ---------------- */}
          {catalogo ? (
            <section className="card" aria-labelledby="titulo-docs-ia">
              <div className="card-head">
                <div>
                  <h2 id="titulo-docs-ia" className="card-title">
                    Documentos para cerrar brechas
                    <InfoTip etiqueta="¿Qué son estos documentos?" icono="ayuda">
                      Son borradores que la IA redacta con los datos de tu empresa y de tu última evaluación. Siempre
                      quedan como borrador para que los revises y completes antes de usarlos. No reemplazan la
                      asesoría legal.
                    </InfoTip>
                  </h2>
                  <p className="card-sub">
                    {catalogo.ia_habilitada ? cuotaBorradoresTexto(catalogo.cuota) || "Generados con IA a partir de tu evaluación." : "El Agente IA no está habilitado: los documentos se arman con la plantilla."}
                  </p>
                </div>
              </div>
              <div className={b.tarjetas}>
                {catalogo.plantillas.map((p) => {
                  const pres = PRESENTACION_PLANTILLA[p.tipo];
                  return (
                    <TarjetaDocumento
                      key={p.tipo}
                      icono={pres.icono}
                      titulo={ETIQUETA_TIPO[p.tipo]}
                      descripcion={p.descripcion || pres.resumen}
                      incluye={pres.incluye}
                      formatos={[...FORMATOS_DOCUMENTO]}
                      seleccionada={seleccion?.tipo === "plantilla" && seleccion.plantilla === p.tipo}
                      recomendada={Boolean(brecha) && formTipo === p.tipo}
                      ayuda={`${pres.resumen} Cubre: ${p.dimensiones.join(", ")}.`}
                      onVistaPrevia={() => {
                        setSeleccion({ tipo: "plantilla", plantilla: p.tipo });
                        irAVistaPrevia();
                      }}
                    >
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => abrirFormulario(p.tipo)}
                              aria-expanded={formTipo === p.tipo} aria-controls="form-generar">
                        <Icon name="chispa" />
                        {catalogo.ia_habilitada ? "Generar con IA" : "Generar"}
                        <span className="sr-only">: {ETIQUETA_TIPO[p.tipo]}</span>
                      </button>
                    </TarjetaDocumento>
                  );
                })}
              </div>

              <div ref={refForm} id="form-generar" className={b.formZona}>
                {formTipo ? (
                  <GenerarBorrador
                    key={formTipo}
                    tipo={formTipo}
                    catalogo={catalogo}
                    enRevision={enRevision}
                    alCerrar={() => setFormTipo(null)}
                    alCambiarOcupado={setGenerando}
                    alGenerar={async (borrador, avisoIa, cuota) => {
                      setCatalogo({ ...catalogo, cuota });
                      setAbierto(borrador);
                      setPrevia(borrador);
                      setSeleccion({ tipo: "documento", id: borrador.id });
                      setFormTipo(null);
                      if (brecha) {
                        setRelaciones(guardarRelacion(borrador.id, brecha));
                        setBrecha(null);
                      }
                      informar(
                        avisoIa ??
                          `¡Listo! Generamos tu ${ETIQUETA_TIPO[borrador.tipo].toLocaleLowerCase("es")}. Revísalo y completa los campos pendientes antes de dejarlo como final.`,
                      );
                      await recargarLista().catch(() => undefined);
                      requestAnimationFrame(() => document.getElementById("editor-borrador")?.scrollIntoView({ block: "start" }));
                    }}
                  />
                ) : null}
              </div>
            </section>
          ) : null}

          {/* ---------------- Reportes que ya genera la plataforma ---------------- */}
          <section className="card" aria-labelledby="titulo-reportes">
            <div className="card-head">
              <div>
                <h2 id="titulo-reportes" className="card-title">
                  Reportes de tu empresa
                  <InfoTip etiqueta="¿De dónde salen los reportes?" icono="ayuda">
                    Se arman con la información que ya registraste: tu evaluación, tus brechas y tu registro de
                    actividades. Algunos se descargan aquí mismo y otros se generan en su sección.
                  </InfoTip>
                </h2>
                <p className="card-sub">Informes listos para compartir con tu directorio, auditores o la autoridad.</p>
              </div>
            </div>
            <div className={b.tarjetas}>
              {REPORTES.map((r) => (
                <TarjetaDocumento
                  key={r.id}
                  icono={r.icono}
                  titulo={r.titulo}
                  descripcion={r.descripcion}
                  incluye={r.incluye}
                  formatos={r.formatos}
                  seleccionada={seleccion?.tipo === "reporte" && seleccion.reporte === r.id}
                  ayuda={r.ayuda}
                  onVistaPrevia={() => {
                    setSeleccion({ tipo: "reporte", reporte: r.id });
                    irAVistaPrevia();
                  }}
                >
                  <AccionReporte reporte={r} evaluacionId={ultimaCompletada?.id ?? null} onAviso={informar} />
                </TarjetaDocumento>
              ))}
            </div>
          </section>

          {/* ---------------- Historial ---------------- */}
          <HistorialDocumentos
            items={lista}
            seleccionado={seleccion?.tipo === "documento" ? seleccion.id : null}
            relaciones={relaciones}
            alVerPrevia={verPrevia}
            alAbrir={abrir}
            alDescargar={(x) => exportar(x, "pdf")}
            alEliminar={async (x) => {
              try {
                await descartarBorrador(x.id);
                if (abierto?.id === x.id) setAbierto(null);
                if (previa?.id === x.id) setPrevia(null);
                if (seleccion?.tipo === "documento" && seleccion.id === x.id) setSeleccion(null);
                informar(`Eliminamos el documento ${ETIQUETA_TIPO[x.tipo]}.`);
                await recargarLista();
              } catch (e) {
                informar(mensaje(e, "No pudimos eliminar el documento. Inténtalo de nuevo."), true);
              }
            }}
          />
        </div>

        {/* ---------------- Vista previa (lateral; en celular, debajo) ---------------- */}
        <aside id="vista-previa-documento" className={b.lateral} aria-labelledby="titulo-vista-previa">
          <div className={`card ${b.previaCard}`}>
            <h2 id="titulo-vista-previa" className="card-title">Vista previa</h2>
            {generando ? (
              <div className={b.previaEstado} role="status">
                <span className={b.puntos} aria-hidden="true"><span /><span /><span /></span>
                Estamos redactando tu documento. Puede tardar hasta un minuto; no cierres esta página.
              </div>
            ) : seleccion?.tipo === "documento" ? (
              <PreviaDocumento
                doc={previa?.id === seleccion.id ? previa : null}
                resumen={documentoSel}
                cargando={cargandoPrevia}
                relacion={relaciones[seleccion.id] ?? null}
                alVerCompleto={() => abrir(seleccion.id)}
                alExportar={(f) => exportar({ id: seleccion.id, tipo: documentoSel?.tipo ?? "politica_llm" }, f)}
              />
            ) : plantillaSel ? (
              <PreviaPlantilla plantilla={plantillaSel} alGenerar={() => abrirFormulario(plantillaSel.tipo)} ia={catalogo?.ia_habilitada ?? false} />
            ) : reporteSel ? (
              <PreviaReporte reporte={reporteSel} evaluacionId={ultimaCompletada?.id ?? null} onAviso={informar} />
            ) : (
              <p className={b.previaVacia}>Elige un documento o un reporte para ver qué incluye.</p>
            )}
          </div>
        </aside>
      </div>

      {abierto && catalogo ? (
        <EditorBorrador
          key={abierto.id}
          borrador={abierto}
          maxCaracteres={catalogo.max_caracteres_contenido}
          alCambiar={async (nuevo) => {
            setAbierto(nuevo);
            setPrevia(nuevo);
            await recargarLista().catch(() => undefined);
          }}
          alCerrar={() => setAbierto(null)}
        />
      ) : null}

      <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
      {aviso ? (
        <p className={`callout ${b.avisoExito}`} aria-hidden="true">
          <Icon name="check" className="icono-estado icono-ok" />
          <span>{aviso}</span>
        </p>
      ) : null}
      {error ? <div className={s.alerta} role="alert"><strong>{error}</strong></div> : null}
    </>
  );
}

/* ================================================================== tarjetas */
function TarjetaDocumento({
  icono, titulo, descripcion, incluye, formatos, seleccionada, recomendada = false, ayuda, onVistaPrevia, children,
}: {
  icono: (typeof PRESENTACION_PLANTILLA)[TipoBorrador]["icono"];
  titulo: string;
  descripcion: string;
  incluye: string[];
  formatos: readonly string[];
  seleccionada: boolean;
  recomendada?: boolean;
  ayuda: string;
  onVistaPrevia: () => void;
  children: ReactNode;
}) {
  return (
    <article className={b.tarjeta} data-seleccionada={seleccionada || undefined}>
      <div className={b.tarjetaCabeza}>
        <span className={b.tarjetaIcono} aria-hidden="true"><Icon name={icono} /></span>
        <h3 className={b.tarjetaTitulo}>{titulo}</h3>
        <InfoTip etiqueta={`Ayuda: ${titulo}`} icono="ayuda">{ayuda}</InfoTip>
      </div>
      {recomendada ? <span className="badge tone-ok">Recomendado para tu brecha</span> : null}
      <p className={b.tarjetaTexto}>{descripcion}</p>
      <div>
        <span className={b.rotulo}>Incluye</span>
        <ul className={b.etiquetas}>
          {incluye.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>
      <p className={b.formatos}>
        <span className={b.rotulo}>Formatos</span>
        {formatos.map((f) => <span key={f} className={b.formato}>{f}</span>)}
      </p>
      <div className={b.tarjetaAcciones}>
        {children}
        <button type="button" className="btn btn-ghost btn-sm" onClick={onVistaPrevia} aria-pressed={seleccionada}>
          Vista previa<span className="sr-only">: {titulo}</span>
        </button>
      </div>
    </article>
  );
}

/** Botón de cada reporte: descarga directa (reporte ejecutivo) o enlace a la sección que lo genera. */
function AccionReporte({
  reporte, evaluacionId, onAviso, grande = false,
}: {
  reporte: ReporteDisponible;
  evaluacionId: number | null;
  onAviso: (texto: string, esError?: boolean) => void;
  grande?: boolean;
}) {
  const [ocupado, setOcupado] = useState(false);
  const tam = grande ? "" : "btn-sm";
  const sinEvaluacion = reporte.requiereEvaluacion && evaluacionId == null;
  if (reporte.accion === "descarga") {
    return (
      <BotonConMotivo
        className={`btn btn-primary ${tam}`}
        ocupado={ocupado}
        aria-busy={ocupado}
        motivo={sinEvaluacion ? "Necesitas una evaluación completada" : null}
        onClick={async () => {
          if (evaluacionId == null) return;
          setOcupado(true);
          onAviso("Estamos generando el PDF…");
          try {
            const { blob, nombre } = await descargarInformePdf(evaluacionId, undefined, "/bff/cliente/api");
            descargarBlob(blob, nombre);
            onAviso(`¡Listo! Descargamos ${nombre}.`);
          } catch {
            onAviso("No pudimos generar el reporte. Inténtalo de nuevo en unos minutos.", true);
          } finally {
            setOcupado(false);
          }
        }}
      >
        <Icon name="descargar" />
        {ocupado ? "Generando…" : "Descargar PDF"}
        <span className="sr-only">: {reporte.titulo}</span>
      </BotonConMotivo>
    );
  }
  const ruta = reporte.ruta === "/panel/brechas" && evaluacionId != null ? `/panel/brechas?evaluacion=${evaluacionId}` : reporte.ruta ?? "/empresa";
  if (sinEvaluacion) {
    return <BotonConMotivo className={`btn ${tam}`} motivo="Necesitas una evaluación completada">Ir a generar</BotonConMotivo>;
  }
  return (
    <Link href={ruta} className={`btn ${tam}`} prefetch={false}>
      <Icon name="flecha" />
      Ir a generar<span className="sr-only">: {reporte.titulo}</span>
    </Link>
  );
}

/* ================================================================== vista previa lateral */
function PreviaPlantilla({ plantilla, alGenerar, ia }: { plantilla: PlantillaApi; alGenerar: () => void; ia: boolean }) {
  const pres = PRESENTACION_PLANTILLA[plantilla.tipo];
  return (
    <div className={b.previa}>
      <div className={b.previaCabeza}>
        <span className={b.tarjetaIcono} aria-hidden="true"><Icon name={pres.icono} /></span>
        <div>
          <strong>{ETIQUETA_TIPO[plantilla.tipo]}</strong>
          <span className={s.sub}>Plantilla {plantilla.version}</span>
        </div>
      </div>
      <p className={b.tarjetaTexto}>{plantilla.descripcion || pres.resumen}</p>
      <div>
        <span className={b.rotulo}>Así se organiza ({plantilla.secciones.length} secciones)</span>
        <ol className={b.indice}>
          {plantilla.secciones.map((x) => <li key={x}>{x}</li>)}
        </ol>
      </div>
      <p className={s.sub}>El contenido completo aparece aquí cuando generes el documento.</p>
      <div className={b.previaAcciones}>
        <BotonConMotivo className="btn btn-ghost btn-sm" motivo="Primero genera el documento">Ver completo</BotonConMotivo>
        <BotonConMotivo className="btn btn-ghost btn-sm" motivo="Primero genera el documento">Exportar</BotonConMotivo>
      </div>
      <button type="button" className="btn btn-primary" onClick={alGenerar}>
        <Icon name="chispa" />
        {ia ? "Generar con IA" : "Generar"}
      </button>
    </div>
  );
}

function PreviaReporte({
  reporte, evaluacionId, onAviso,
}: {
  reporte: ReporteDisponible;
  evaluacionId: number | null;
  onAviso: (texto: string, esError?: boolean) => void;
}) {
  return (
    <div className={b.previa}>
      <div className={b.previaCabeza}>
        <span className={b.tarjetaIcono} aria-hidden="true"><Icon name={reporte.icono} /></span>
        <div>
          <strong>{reporte.titulo}</strong>
          <span className={s.sub}>{reporte.formatos.join(" · ")}</span>
        </div>
      </div>
      <p className={b.tarjetaTexto}>{reporte.descripcion}</p>
      <div>
        <span className={b.rotulo}>Incluye</span>
        <ul className={b.indice}>
          {reporte.incluye.map((x) => <li key={x}>{x}</li>)}
        </ul>
      </div>
      <p className={s.sub}>{reporte.ayuda}</p>
      <AccionReporte reporte={reporte} evaluacionId={evaluacionId} onAviso={onAviso} grande />
    </div>
  );
}

function PreviaDocumento({
  doc, resumen, cargando, relacion, alVerCompleto, alExportar,
}: {
  doc: BorradorApi | null;
  resumen: BorradorApi | null;
  cargando: boolean;
  relacion: BrechaRelacionada | null;
  alVerCompleto: () => void;
  alExportar: (f: FormatoBorrador) => Promise<void>;
}) {
  const [menu, setMenu] = useState(false);
  const [exportando, setExportando] = useState<FormatoBorrador | null>(null);
  const bloques = useMemo(() => parsearMarkdown(doc?.contenido ?? ""), [doc?.contenido]);
  const base = doc ?? resumen;
  if (cargando) return <div className="skeleton esq-320" role="status" aria-label="Cargando la vista previa" />;
  if (!base) return <p className={b.previaVacia}>Este documento ya no está disponible.</p>;
  const estado = ESTADO_HISTORIAL[base.estado];
  return (
    <div className={b.previa}>
      <div className={b.previaCabeza}>
        <span className={b.tarjetaIcono} aria-hidden="true"><Icon name={PRESENTACION_PLANTILLA[base.tipo].icono} /></span>
        <div>
          <strong>{base.titulo}</strong>
          <span className={s.sub}>
            <span className={`badge tone-${estado.tono}`}>{estado.texto}</span> · Actualizado {fechaCorta(base.fecha_actualizacion)}
          </span>
        </div>
      </div>
      {relacion ? (
        <p className={b.relacion}>
          <Icon name="brechas" />
          <span>Para cerrar la brecha #{relacion.prioridad}: {relacion.descripcion}</span>
        </p>
      ) : null}
      <div className={b.previaHoja} aria-label="Vista previa del documento" tabIndex={0}>
        {doc ? <VistaPrevia bloques={bloques.slice(0, 18)} /> : <p className={s.sub}>Cargando el contenido…</p>}
        {bloques.length > 18 ? <p className={b.previaMas}>… continúa en «Ver completo».</p> : null}
      </div>
      <div className={b.previaAcciones}>
        <button type="button" className="btn btn-sm" onClick={alVerCompleto}>
          <Icon name="lupaMas" />
          Ver completo
        </button>
        <div className={b.menuExportar}>
          <button type="button" className="btn btn-primary btn-sm" aria-expanded={menu} aria-controls="menu-exportar"
                  aria-busy={exportando !== null} onClick={() => setMenu((v) => !v)}>
            <Icon name="descargar" />
            {exportando ? "Exportando…" : "Exportar"}
          </button>
          {menu ? (
            <div id="menu-exportar" className={b.menuOpciones} role="group" aria-label="Formato de exportación">
              {(["pdf", "md"] as const).map((f) => (
                <button key={f} type="button" className="btn btn-ghost btn-sm" disabled={exportando !== null}
                        onClick={async () => {
                          setExportando(f);
                          await alExportar(f);
                          setExportando(null);
                          setMenu(false);
                        }}>
                  {f === "pdf" ? "PDF" : "Markdown (texto editable)"}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== generar (C1 y C2) */
function GenerarBorrador({
  tipo, catalogo, enRevision, alGenerar, alCerrar, alCambiarOcupado,
}: {
  tipo: TipoBorrador;
  catalogo: CatalogoBorradoresApi;
  enRevision: number;
  alGenerar: (b: BorradorApi, aviso: string | undefined, cuota: CatalogoBorradoresApi["cuota"]) => Promise<void>;
  alCerrar: () => void;
  alCambiarOcupado: (ocupado: boolean) => void;
}) {
  // Desde Mi empresa o el registro: ?plantilla=pia&actividad=ID abre la evaluación de impacto con esa actividad
  const [elegidas, setElegidas] = useState<number[]>(() => {
    const id = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("actividad")) : NaN;
    return actividadesPiaIniciales(catalogo.registro, Number.isInteger(id) && id > 0 ? id : null);
  });
  const ayudaRegistro = textoRegistroBorrador(tipo, catalogo.registro, elegidas.length);
  const [instrucciones, setInstrucciones] = useState("");
  const [usarIa, setUsarIa] = useState(catalogo.ia_habilitada);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const max = catalogo.max_caracteres_instrucciones;
  const lleno = enRevision >= catalogo.max_en_revision;
  const plantilla = catalogo.plantillas.find((p) => p.tipo === tipo);

  async function generar(ev: FormEvent) {
    ev.preventDefault();
    if (ocupado || lleno) return;
    if (instrucciones.length > max) {
      setError(`Las indicaciones superan los ${max} caracteres.`);
      return;
    }
    setOcupado(true);
    alCambiarOcupado(true);
    setError("");
    try {
      const r = await generarBorrador(tipo, instrucciones, usarIa && catalogo.ia_habilitada, elegidas);
      setInstrucciones("");
      alCambiarOcupado(false);
      await alGenerar(r.borrador, r.aviso, r.cuota);
    } catch (e) {
      setError(mensaje(e, "No pudimos generar el documento. Revisa tu conexión e inténtalo de nuevo."));
    } finally {
      setOcupado(false);
      alCambiarOcupado(false);
    }
  }

  return (
    <form className={b.generar} onSubmit={generar} aria-busy={ocupado} aria-labelledby="titulo-generar">
      <div className={b.cabeza}>
        <h3 id="titulo-generar" className={b.formTitulo}>Generar: {ETIQUETA_TIPO[tipo]}</h3>
        <button type="button" className="btn btn-ghost btn-sm" onClick={alCerrar} disabled={ocupado}>Cancelar</button>
      </div>
      <p className={s.sub}>Parte de la evaluación más reciente de tu empresa.</p>

      {plantilla ? (
        <p className={s.sub}>
          {plantilla.secciones.length} secciones: {plantilla.secciones.slice(0, 5).join(", ")}
          {plantilla.secciones.length > 5 ? "…" : "."}
        </p>
      ) : null}

      {ayudaRegistro ? <p className="callout" role="status"><span>{ayudaRegistro}</span></p> : null}
      {tipo === "pia" && catalogo.registro?.actividades.length ? (
        <fieldset className={b.plantillas}>
          <legend>Actividades del registro que evalúa</legend>
          {catalogo.registro.actividades.map((a) => {
            const marcada = elegidas.includes(a.actividad_id);
            return (
              <label key={a.actividad_id} className="check">
                <input
                  type="checkbox"
                  checked={marcada}
                  disabled={!marcada && elegidas.length >= MAX_ACTIVIDADES_PIA}
                  onChange={(e) =>
                    setElegidas((x) => (e.target.checked ? [...x, a.actividad_id] : x.filter((i) => i !== a.actividad_id)))
                  }
                />
                <span>
                  {a.nombre}{" "}
                  <span className={`badge ${TONO_RIESGO[a.nivel]}`}>
                    Riesgo {a.nivel.toLocaleLowerCase("es")}
                  </span>
                  <span className={s.sub}>
                    {a.requiere_pia ? `Recomendada: ${a.motivos_pia.join(" ")}` : "Sin evaluación de impacto recomendada."}
                    {a.vigente ? "" : " Aún no está vigente."}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>
      ) : null}

      <div className="field">
        <label className="field-label" htmlFor="instrucciones-borrador">
          Cuéntale a la IA sobre tu empresa <span className="field-opcional">(opcional)</span>
          <InfoTip etiqueta="¿Qué escribo aquí?" icono="ayuda">
            Describe a qué se dedica tu empresa y cómo usan la IA. Mientras más contexto, más ajustado queda el documento.
            No escribas nombres, RUT ni otros datos personales.
          </InfoTip>
        </label>
        <textarea
          id="instrucciones-borrador"
          className="input"
          rows={3}
          value={instrucciones}
          maxLength={max}
          disabled={!usarIa || !catalogo.ia_habilitada}
          onChange={(e) => setInstrucciones(e.target.value)}
          placeholder="Ej.: somos una clínica que usa un chatbot para agendar horas y un proveedor de IA en la nube."
          aria-describedby="ayuda-instrucciones"
        />
        <span id="ayuda-instrucciones" className="field-ayuda">
          Describe tu operación y cómo usan la IA. No escribas datos personales: se anonimizan antes de llegar al
          Agente IA y quedarán como campos por completar.
        </span>
        <span className={b.contador} aria-live="off">{instrucciones.length} / {max}</span>
      </div>

      <div className={b.fila}>
        <label className="check">
          <input
            type="checkbox"
            checked={usarIa && catalogo.ia_habilitada}
            disabled={!catalogo.ia_habilitada}
            onChange={(e) => setUsarIa(e.target.checked)}
          />
          <span>
            Adaptar con el Agente IA
            <span className={s.sub}>
              {catalogo.ia_habilitada ? cuotaBorradoresTexto(catalogo.cuota) : "El Agente IA no está habilitado."}
            </span>
          </span>
        </label>
        <BotonConMotivo type="submit" className="btn btn-primary" ocupado={ocupado} aria-busy={ocupado}
                        motivo={!ocupado && lleno ? `Ya tienes ${catalogo.max_en_revision} borradores en revisión: termina o elimina uno para generar otro` : null}>
          <Icon name="chispa" />
          {ocupado ? "Generando…" : usarIa && catalogo.ia_habilitada ? "Generar con IA" : "Generar"}
        </BotonConMotivo>
      </div>
      {ocupado ? (
        <p className={b.espera} role="status">
          <span className={b.puntos} aria-hidden="true"><span /><span /><span /></span>
          {usarIa ? "El Agente IA está redactando tu documento. Puede tardar hasta un minuto." : "Estamos armando tu documento…"}
        </p>
      ) : null}
      {lleno ? (
        <p className="callout" role="status">
          Tienes {enRevision} borradores en revisión. Deja alguno como final o elimínalo para generar otro.
        </p>
      ) : null}
      {error ? <div className={s.alerta} role="alert"><strong>{error}</strong></div> : null}
    </form>
  );
}

/* ================================================================== historial */
function HistorialDocumentos({
  items, seleccionado, relaciones, alVerPrevia, alAbrir, alDescargar, alEliminar,
}: {
  items: BorradorApi[];
  seleccionado: number | null;
  relaciones: Record<number, BrechaRelacionada>;
  alVerPrevia: (id: number) => void;
  alAbrir: (id: number) => void;
  alDescargar: (b: BorradorApi) => Promise<void>;
  alEliminar: (b: BorradorApi) => Promise<void>;
}) {
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [descargando, setDescargando] = useState<number | null>(null);

  return (
    <section className="card" aria-labelledby="titulo-mis-borradores">
      <div className="card-head">
        <div>
          <h2 id="titulo-mis-borradores" className="card-title">
            Documentos generados
            <InfoTip etiqueta="¿Qué significan Borrador y Final?" icono="ayuda">
              «Borrador»: todavía puedes revisarlo y editarlo. «Final»: quedó de solo lectura y su PDF está en Mis
              documentos. Para cambiar un documento final, genera uno nuevo.
            </InfoTip>
          </h2>
          <p className="card-sub">
            Los documentos finales también están en <Link href="/empresa/documentos">Mis documentos</Link>.
          </p>
        </div>
      </div>
      {!items.length ? (
        <div className={b.vacio}>
          <Icon name="carpeta" width={32} height={32} className="icono-estado icono-ok" />
          <strong>Aún no has generado documentos</strong>
          <p>
            Elige un documento arriba y presiona «Generar con IA». Aparecerá aquí como borrador para que lo revises y
            completes; cuando lo dejes como final, su PDF quedará guardado en Mis documentos.
          </p>
        </div>
      ) : (
        <ul className={b.historial}>
          {items.map((x) => {
            const estado = ESTADO_HISTORIAL[x.estado];
            const rel = relaciones[x.id];
            return (
              <li key={x.id} className={b.historialItem} aria-current={seleccionado === x.id ? "true" : undefined}>
                <span className={b.tarjetaIcono} aria-hidden="true"><Icon name={PRESENTACION_PLANTILLA[x.tipo].icono} /></span>
                <div className={b.historialDatos}>
                  <strong>{ETIQUETA_TIPO[x.tipo]}</strong>
                  <span className={b.historialMeta}>
                    <span className={`badge tone-${estado.tono}`} title={estado.ayuda}>{estado.texto}</span>
                    <span>{fechaCorta(x.fecha_actualizacion)}</span>
                    <span>{FORMATOS_DOCUMENTO.join(" · ")}</span>
                    <span>Versión {x.version}</span>
                    {x.adaptado_ia ? <span>Adaptado con IA</span> : null}
                    {x.pendientes ? <span className={b.pendienteTexto}>{x.pendientes} campos por completar</span> : null}
                  </span>
                  {rel ? (
                    <Link href={hrefVolverABrecha(rel)} className={b.relacion}>
                      <Icon name="brechas" />
                      <span>Para cerrar la brecha #{rel.prioridad}: {rel.descripcion}</span>
                    </Link>
                  ) : null}
                </div>
                {confirmar === x.id ? (
                  <div className={s.acciones} role="group" aria-label="Confirmar la eliminación">
                    <span className={s.sub}>
                      ¿Eliminar?{x.estado === "consolidado" ? " El PDF sigue en Mis documentos." : " Se pierden los cambios."}
                    </span>
                    <button
                      type="button"
                      className={`btn btn-sm ${b.peligro}`}
                      disabled={ocupado !== null}
                      aria-busy={ocupado === x.id}
                      onClick={async () => {
                        setOcupado(x.id);
                        await alEliminar(x);
                        setOcupado(null);
                        setConfirmar(null);
                      }}
                    >
                      Sí, eliminar
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(null)}>Cancelar</button>
                  </div>
                ) : (
                  <div className={b.historialAcciones}>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => alVerPrevia(x.id)}
                            aria-label={`Vista previa de ${ETIQUETA_TIPO[x.tipo]}`}>
                      <Icon name="ojo" />
                      <span className={b.textoAccion}>Vista previa</span>
                    </button>
                    <button type="button" className="btn btn-sm" onClick={() => alAbrir(x.id)}
                            aria-label={`${x.editable ? "Abrir y editar" : "Abrir"} ${ETIQUETA_TIPO[x.tipo]}`}>
                      <Icon name={x.editable ? "editar" : "documento"} />
                      <span className={b.textoAccion}>{x.editable ? "Abrir" : "Ver"}</span>
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" disabled={descargando !== null}
                            aria-busy={descargando === x.id} aria-label={`Descargar ${ETIQUETA_TIPO[x.tipo]} en PDF`}
                            onClick={async () => {
                              setDescargando(x.id);
                              await alDescargar(x);
                              setDescargando(null);
                            }}>
                      <Icon name="descargar" />
                      <span className={b.textoAccion}>{descargando === x.id ? "Descargando…" : "Descargar"}</span>
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(x.id)}
                            aria-label={`Eliminar ${ETIQUETA_TIPO[x.tipo]}`}>
                      <Icon name="basura" />
                      <span className={b.textoAccion}>Eliminar</span>
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ================================================================== editor (C3) */
function EditorBorrador({
  borrador, maxCaracteres, alCambiar, alCerrar,
}: {
  borrador: BorradorApi;
  maxCaracteres: number;
  alCambiar: (b: BorradorApi) => Promise<void>;
  alCerrar: () => void;
}) {
  const [texto, setTexto] = useState(borrador.contenido ?? "");
  const [guardado, setGuardado] = useState(borrador.contenido ?? "");
  const [version, setVersion] = useState(borrador.version);
  const [vista, setVista] = useState<"editar" | "previa">("editar");
  const [ocupado, setOcupado] = useState<"guardar" | "md" | "pdf" | "consolidar" | null>(null);
  const [mensajeEditor, setMensajeEditor] = useState("");
  const [error, setError] = useState("");
  const [consolidando, setConsolidando] = useState(false);
  const [confirmarPendientes, setConfirmarPendientes] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const editable = borrador.editable;
  const sucio = texto !== guardado;
  const pendientes = useMemo(() => pendientesDe(texto), [texto]);
  const bloques = useMemo(() => parsearMarkdown(texto), [texto]);
  const validacion = validarContenido(texto, maxCaracteres);
  const advertencias = advertenciasVisibles(borrador.advertencias);

  // Cambios sin guardar: el navegador avisa antes de salir
  useEffect(() => {
    if (!sucio) return;
    const antes = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", antes);
    return () => window.removeEventListener("beforeunload", antes);
  }, [sucio]);

  async function guardar(): Promise<boolean> {
    if (!validacion.ok) {
      setError(validacion.motivo ?? "");
      return false;
    }
    setOcupado("guardar");
    setError("");
    try {
      const r = await guardarBorrador(borrador.id, texto, version);
      setGuardado(r.borrador.contenido ?? texto);
      setTexto(r.borrador.contenido ?? texto);
      setVersion(r.borrador.version);
      setMensajeEditor(`Guardamos la versión ${r.borrador.version}.`);
      await alCambiar(r.borrador);
      return true;
    } catch (e) {
      setError(mensaje(e, "No pudimos guardar los cambios."));
      return false;
    } finally {
      setOcupado(null);
    }
  }

  async function descargar(formato: FormatoBorrador) {
    if (sucio && editable && !(await guardar())) return;
    setOcupado(formato);
    try {
      const { blob, nombre } = await descargarBorrador(borrador.id, formato);
      descargarBlob(blob, nombre);
      setMensajeEditor(`Descargamos ${nombre}.`);
    } catch (e) {
      setError(mensaje(e, "No pudimos descargar el borrador."));
    } finally {
      setOcupado(null);
    }
  }

  async function consolidar() {
    if (sucio && !(await guardar())) return;
    setOcupado("consolidar");
    setError("");
    try {
      const r = await consolidarBorrador(borrador.id, version, confirmarPendientes);
      setConsolidando(false);
      setMensajeEditor(`¡Listo! El documento quedó como final. Su PDF (${r.documento.nombre}) está en Mis documentos.`);
      await alCambiar(r.borrador);
    } catch (e) {
      setError(mensaje(e, "No pudimos dejar el documento como final. Inténtalo de nuevo."));
    } finally {
      setOcupado(null);
    }
  }

  function irAlPendiente() {
    const el = area.current;
    if (!el) return;
    setVista("editar");
    const pos = siguientePendiente(texto, el.selectionEnd);
    if (!pos) return;
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(pos.inicio, pos.fin);
    });
  }

  const estado = ESTADO_HISTORIAL[borrador.estado];

  return (
    <section id="editor-borrador" className="card" aria-labelledby="titulo-editor" style={{ scrollMarginTop: 16 }}>
      <div className={b.editor}>
        <div className={b.cabeza}>
          <div>
            <h2 id="titulo-editor" className="card-title">{borrador.titulo}</h2>
            <div className={b.metas}>
              <span className={`badge tone-${estado.tono}`}>{estado.texto}</span>
              <span>Versión {version}</span>
              {borrador.adaptado_ia ? <span className="badge tone-info">Adaptado con IA</span> : null}
              <span>· {fechaCorta(borrador.fecha_creacion)}</span>
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={alCerrar}>Cerrar</button>
        </div>

        {!editable ? (
          <p className="callout" role="status">
            Este documento es final: es de solo lectura. Su PDF está en{" "}
            <Link href="/empresa/documentos">Mis documentos</Link>. Para cambiarlo, genera uno nuevo.
          </p>
        ) : null}

        {advertencias.length ? (
          <div className="callout callout-aviso" role="note">
            <ul className={b.notas}>{advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
          </div>
        ) : null}

        {borrador.notas.length && editable ? (
          <div className="callout" role="note">
            <strong>El Agente IA sugiere revisar:</strong>
            <ul className={b.notas}>{borrador.notas.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        ) : null}

        {editable ? (
          <div className={b.pendientes} aria-live="polite">
            {pendientes.length ? (
              <>
                <span className="badge tone-medio">{pendientes.length} campos por completar</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={irAlPendiente}>
                  Ir al siguiente
                </button>
                <span className={s.sub}>Reemplaza cada [COMPLETAR: …] por el dato de tu empresa.</span>
              </>
            ) : (
              <span className="badge tone-ok">Sin campos por completar</span>
            )}
          </div>
        ) : null}

        <div className={`${s.pestanas} ${b.pestanasEditor}`} role="tablist" aria-label="Modo del editor">
          {(["editar", "previa"] as const).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={vista === v} className={s.pestana}
                    aria-controls={`panel-${v}`} id={`tab-${v}`} onClick={() => setVista(v)}>
              {v === "editar" ? (editable ? "Editar" : "Markdown") : "Vista previa"}
            </button>
          ))}
        </div>

        <div className={b.paneles}>
          <div id="panel-editar" className={`${b.panel} ${vista === "editar" ? "" : b.oculto}`}>
            <label className={b.panelTitulo} htmlFor="contenido-borrador">Markdown</label>
            <textarea
              id="contenido-borrador"
              ref={area}
              className={b.texto}
              value={texto}
              readOnly={!editable}
              spellCheck
              onChange={(e) => setTexto(e.target.value)}
              aria-describedby="ayuda-markdown"
            />
            <span id="ayuda-markdown" className={s.sub}>
              {texto.length.toLocaleString("es-CL")} / {maxCaracteres.toLocaleString("es-CL")} caracteres · # títulos,
              - viñetas, **negrita**, tablas con |.
            </span>
          </div>
          <div id="panel-previa" className={`${b.panel} ${vista === "previa" ? "" : b.oculto}`}>
            <span className={b.panelTitulo}>Vista previa</span>
            <div className={b.vista} aria-label="Vista previa del borrador">
              <VistaPrevia bloques={bloques} />
            </div>
          </div>
        </div>

        <div className={b.acciones}>
          {editable ? (
            <button type="button" className="btn btn-primary" onClick={guardar}
                    disabled={!sucio || ocupado !== null} aria-busy={ocupado === "guardar"}>
              {ocupado === "guardar" ? "Guardando…" : sucio ? "Guardar cambios" : "Guardado"}
            </button>
          ) : null}
          <button type="button" className="btn" onClick={() => descargar("pdf")} disabled={ocupado !== null}
                  aria-busy={ocupado === "pdf"}>
            Descargar PDF
          </button>
          <button type="button" className="btn" onClick={() => descargar("md")} disabled={ocupado !== null}
                  aria-busy={ocupado === "md"}>
            Descargar Markdown
          </button>
          {editable && !consolidando ? (
            <button type="button" className="btn btn-ghost" onClick={() => setConsolidando(true)} disabled={ocupado !== null}>
              Marcar como final…
            </button>
          ) : null}
        </div>

        {editable && consolidando ? (
          <div className={b.consolidar} role="group" aria-labelledby="titulo-consolidar">
            <strong id="titulo-consolidar">Marcar el documento como final</strong>
            <p className={s.sub} style={{ margin: 0 }}>
              Queda de solo lectura y su PDF final (sin la marca «BORRADOR») se guarda en Mis documentos.
              {sucio ? " Antes guardaremos tus cambios." : ""}
            </p>
            {pendientes.length ? (
              <label className="check">
                <input type="checkbox" checked={confirmarPendientes} onChange={(e) => setConfirmarPendientes(e.target.checked)} />
                <span>Marcarlo como final aunque queden {pendientes.length} campos por completar</span>
              </label>
            ) : null}
            <div className={b.acciones}>
              <button type="button" className="btn btn-primary" onClick={consolidar}
                      disabled={ocupado !== null || (pendientes.length > 0 && !confirmarPendientes)}
                      aria-busy={ocupado === "consolidar"}>
                {ocupado === "consolidar" ? "Guardando como final…" : "Sí, marcar como final"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setConsolidando(false)}>Cancelar</button>
            </div>
          </div>
        ) : null}

        {error ? <div className={s.alerta} role="alert"><strong>{error}</strong></div> : null}
        <p className="sr-only" role="status" aria-live="polite">{mensajeEditor}</p>
        {mensajeEditor && !error ? <p className={s.sub} aria-hidden="true">{mensajeEditor}</p> : null}
      </div>
    </section>
  );
}

/* ================================================================== vista previa segura */
function EnLinea({ texto }: { texto: string }) {
  return (
    <>
      {segmentos(texto).map((g, i) => {
        if (g.tipo === "negrita") return <strong key={i}>{g.texto}</strong>;
        if (g.tipo === "cursiva") return <em key={i}>{g.texto}</em>;
        if (g.tipo === "codigo") return <code key={i}>{g.texto}</code>;
        if (g.tipo === "pendiente") return <mark key={i} className={b.pendiente}>{g.texto}</mark>;
        return <span key={i}>{g.texto}</span>;
      })}
    </>
  );
}

function VistaPrevia({ bloques }: { bloques: BloqueMd[] }) {
  if (!bloques.length) return <p className={s.sub}>El borrador está vacío.</p>;
  return (
    <>
      {bloques.map((x, i) => {
        switch (x.tipo) {
          case "titulo": {
            // h1 del documento → h3 en la página (la página ya tiene su h1 y el h2 del editor)
            const Tag = x.nivel === 1 ? "h3" : x.nivel === 2 ? "h4" : "h5";
            return <Tag key={i}><EnLinea texto={x.texto} /></Tag>;
          }
          case "parrafo":
            return <p key={i}><EnLinea texto={x.texto} /></p>;
          case "cita":
            return <blockquote key={i}><EnLinea texto={x.texto} /></blockquote>;
          case "separador":
            return <hr key={i} />;
          case "lista": {
            const Lista = x.ordenada ? "ol" : "ul";
            return <Lista key={i}>{x.items.map((t, j) => <li key={j}><EnLinea texto={t} /></li>)}</Lista>;
          }
          case "tabla":
            return (
              <div key={i} className="table-wrap">
                <table>
                  <thead><tr>{x.cabecera.map((c, j) => <th key={j} scope="col"><EnLinea texto={c} /></th>)}</tr></thead>
                  <tbody>
                    {x.filas.map((f, j) => (
                      <tr key={j}>{f.map((c, k) => <td key={k}><EnLinea texto={c} /></td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </>
  );
}
