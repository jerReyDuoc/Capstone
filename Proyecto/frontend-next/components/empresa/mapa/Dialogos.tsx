"use client";

/**
 * Piezas comunes de las ventanas del mapa de datos (y del registro de actividades):
 *   Dialogo            ventana centrada (<dialog> nativo: foco atrapado, Esc y la X para cerrar). Se
 *                      ajusta a su contenido —sin espacio vacío al final—, el cuerpo hace scroll si no
 *                      cabe y en el teléfono aparece desde abajo, a todo el ancho.
 *   IndicadorPasos     la barra de pasos de los asistentes (agregar elemento, agregar flujo).
 *   DialogoConfirmar   confirmación de acciones (eliminar, restaurar, usar una plantilla…).
 *   DialogoCorreo      envío del informe por correo.
 *   SelectorCategorias categorías del catálogo común (datos con las sensibles marcadas y titulares con NNA).
 */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import type { CatalogoMapa } from "@/lib/mapaDatos";
import s from "./mapa.module.css";

export type TamanoDialogo = "sm" | "md" | "lg" | "xl";

export function Dialogo({
  titulo,
  descripcion,
  onCerrar,
  onEnviar,
  pie,
  children,
  estrecho = false,
  tamano,
  icono,
  tonoIcono,
  antetitulo,
  cabeceraExtra,
  cerrarAlHacerClicFuera = false,
  etiquetaCerrar = "Cerrar",
}: {
  titulo: ReactNode;
  descripcion?: ReactNode;
  onCerrar: () => void;
  onEnviar?: () => void;
  pie?: ReactNode;
  children: ReactNode;
  /** Compatibilidad: equivale a tamano="sm". */
  estrecho?: boolean;
  tamano?: TamanoDialogo;
  icono?: IconName;
  tonoIcono?: "acento" | "peligro" | "aviso" | "info";
  antetitulo?: ReactNode;
  /** Algo que va pegado bajo el título y no hace scroll (p. ej. la barra de pasos). */
  cabeceraExtra?: ReactNode;
  /** Las fichas y confirmaciones se cierran al hacer clic fuera; los formularios no (no se pierde lo escrito). */
  cerrarAlHacerClicFuera?: boolean;
  etiquetaCerrar?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();
  const idDescripcion = useId();
  const pulsoFuera = useRef(false);
  const t: TamanoDialogo = tamano ?? (estrecho ? "sm" : "lg");

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    // El foco va al primer campo marcado (si no hay, queda en la ventana, no en la X)
    const primero = d?.querySelector<HTMLElement>("[data-autofoco]");
    if (primero) primero.focus();
    else d?.querySelector<HTMLElement>(`.${s.modalCuerpo}`)?.focus();
    // Mientras está abierta, la página de atrás no se desplaza
    const html = document.documentElement;
    const antes = html.style.overflow;
    html.style.overflow = "hidden";
    return () => {
      html.style.overflow = antes;
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={s.modal}
      data-tamano={t}
      aria-labelledby={idTitulo}
      aria-describedby={descripcion ? idDescripcion : undefined}
      onCancel={(e) => {
        e.preventDefault();
        onCerrar();
      }}
      onPointerDown={(e) => {
        pulsoFuera.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        // Solo si el clic empezó y terminó en el fondo (no al soltar una selección de texto afuera)
        if (cerrarAlHacerClicFuera && pulsoFuera.current && e.target === e.currentTarget) onCerrar();
        pulsoFuera.current = false;
      }}
    >
      <form
        className={s.modalForm}
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          onEnviar?.();
        }}
      >
        <header className={s.modalCabeza}>
          {icono ? (
            <span className={s.modalIcono} data-tono={tonoIcono ?? "acento"} aria-hidden="true">
              <Icon name={icono} />
            </span>
          ) : null}
          <div className={s.modalTitulos}>
            {antetitulo ? <span className={s.modalAntetitulo}>{antetitulo}</span> : null}
            <h2 id={idTitulo} className={s.modalTitulo}>{titulo}</h2>
            {descripcion ? <p id={idDescripcion} className={s.modalDescripcion}>{descripcion}</p> : null}
          </div>
          <button type="button" className={s.modalCerrar} onClick={onCerrar} aria-label={etiquetaCerrar} title={etiquetaCerrar}>
            <Icon name="cerrar" />
          </button>
        </header>
        {cabeceraExtra ? <div className={s.modalCabeceraExtra}>{cabeceraExtra}</div> : null}
        <div className={s.modalCuerpo} tabIndex={-1}>{children}</div>
        {pie ? <footer className={s.modalPie}>{pie}</footer> : null}
      </form>
    </dialog>
  );
}

/* ============================================================ pasos de un asistente */

export interface PasoAsistente {
  titulo: string;
  /** Texto corto bajo el título del paso (se oculta en pantallas angostas). */
  resumen?: string;
  completo?: boolean;
  conError?: boolean;
}

export function IndicadorPasos({
  pasos,
  actual,
  onIr,
  libre = false,
}: {
  pasos: PasoAsistente[];
  actual: number;
  onIr: (i: number) => void;
  /** Al editar se puede saltar a cualquier paso; al crear, solo a los ya visitados. */
  libre?: boolean;
}) {
  const [maximo, setMaximo] = useState(actual);
  useEffect(() => setMaximo((m) => Math.max(m, actual)), [actual]);
  return (
    <nav aria-label="Pasos">
      <ol className={s.pasos}>
        {pasos.map((p, i) => {
          // "Listo" solo si el paso tiene lo suyo (visitarlo no basta)
          const estado = i === actual ? "actual" : p.conError ? "error" : p.completo ? "hecho" : "pendiente";
          const habilitado = libre || i <= maximo;
          return (
            <li key={p.titulo} className={s.paso} data-estado={estado}>
              <button
                type="button"
                className={s.pasoBoton}
                onClick={() => onIr(i)}
                disabled={!habilitado}
                aria-current={i === actual ? "step" : undefined}
              >
                <span className={s.pasoNumero} aria-hidden="true">
                  {estado === "hecho" ? <Icon name="check" /> : estado === "error" ? "!" : i + 1}
                </span>
                <span className={s.pasoTexto}>
                  <span className={s.pasoTitulo}>{p.titulo}</span>
                  {p.resumen ? <span className={s.pasoResumen}>{p.resumen}</span> : null}
                </span>
                <span className="sr-only">
                  {estado === "hecho" ? " (listo)" : estado === "error" ? " (revisar)" : estado === "actual" ? " (paso actual)" : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className={s.pasosBarra} aria-hidden="true">
        <span style={{ width: `${((actual + 1) / pasos.length) * 100}%` }} />
      </div>
    </nav>
  );
}

/** Encabezado de un paso: qué se pide y por qué. */
export function EncabezadoPaso({ numero, titulo, children }: { numero: number; titulo: string; children?: ReactNode }) {
  return (
    <div className={s.encabezadoPaso}>
      <span className={s.encabezadoNumero} aria-hidden="true">{numero}</span>
      <div>
        <h3 className={s.encabezadoTitulo}>{titulo}</h3>
        {children ? <p className={s.encabezadoTexto}>{children}</p> : null}
      </div>
    </div>
  );
}

/** Recuadro "¿Por qué lo pedimos?" / consejos al costado de un paso. */
export function Consejo({ titulo = "¿Por qué lo pedimos?", children, icono = "info" }: { titulo?: string; children: ReactNode; icono?: IconName }) {
  return (
    <aside className={s.consejo}>
      <span className={s.consejoTitulo}><Icon name={icono} />{titulo}</span>
      <div className={s.consejoTexto}>{children}</div>
    </aside>
  );
}

/* ============================================================ confirmar */

export function DialogoConfirmar({
  titulo,
  children,
  textoConfirmar,
  peligro = false,
  onConfirmar,
  onCerrar,
  icono,
}: {
  titulo: string;
  children: ReactNode;
  textoConfirmar: string;
  peligro?: boolean;
  onConfirmar: () => Promise<void>;
  onCerrar: () => void;
  icono?: IconName;
}) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  return (
    <Dialogo
      titulo={titulo}
      tamano="sm"
      icono={icono ?? (peligro ? "basura" : "info")}
      tonoIcono={peligro ? "peligro" : "acento"}
      cerrarAlHacerClicFuera={!ocupado}
      onCerrar={onCerrar}
      onEnviar={async () => {
        setOcupado(true);
        setError("");
        try {
          await onConfirmar();
        } catch (e) {
          setError(e instanceof Error && e.message ? e.message : "No pudimos completar la acción. Inténtalo de nuevo.");
        } finally {
          // Si la acción falló el diálogo sigue abierto (el aviso explica el motivo): se puede reintentar
          setOcupado(false);
        }
      }}
      pie={
        <div className={s.modalAcciones}>
          <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>
            Cancelar
          </button>
          <button type="submit" className={`btn btn-primary ${peligro ? s.botonPeligro : ""}`} disabled={ocupado} data-autofoco>
            {peligro ? <Icon name="basura" /> : <Icon name="check" />}
            {ocupado ? "Un momento…" : textoConfirmar}
          </button>
        </div>
      }
    >
      <div className={s.textoConfirmar}>{children}</div>
      {error ? (
        <p className="dialogo-error" role="alert">
          <Icon name="alerta" />
          {error}
        </p>
      ) : null}
    </Dialogo>
  );
}

/* ============================================================ correo */

export function DialogoCorreo({
  correoUsuario,
  descripcionFiltros,
  onEnviar,
  onCerrar,
}: {
  correoUsuario: string | null;
  descripcionFiltros: string;
  onEnviar: (email: string) => Promise<string>;
  onCerrar: () => void;
}) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [otro, setOtro] = useState(!correoUsuario);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  const enviar = async () => {
    const valor = otro ? email.trim() : "";
    if (otro && !/^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/.test(valor)) {
      setError("Revisa el formato del correo (ejemplo: nombre@empresa.cl).");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      await onEnviar(valor);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "No pudimos enviar el correo. Inténtalo de nuevo.");
      setOcupado(false);
    }
  };

  return (
    <Dialogo
      titulo="Enviar el informe por correo"
      descripcion="Te enviamos el mismo informe PDF que descargas: diagrama, inventario, flujos, transferencias internacionales, riesgos y la base para el registro de actividades de tratamiento."
      tamano="sm"
      icono="correo"
      onCerrar={onCerrar}
      onEnviar={enviar}
      pie={
        <div className={s.modalAcciones}>
          <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={ocupado}>
            <Icon name="enviar" />
            {ocupado ? "Enviando…" : "Enviar informe"}
          </button>
        </div>
      }
    >
      {correoUsuario ? (
        <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className={s.etiquetaCampo}>¿A quién se lo enviamos?</legend>
          <div className={`${s.segmentado} ${s.dos}`}>
            <label className={s.segmento}>
              <input type="radio" name={`${id}-destino`} checked={!otro} onChange={() => setOtro(false)} data-autofoco />
              <Icon name="usuario" />
              <span>A mi correo</span>
            </label>
            <label className={s.segmento}>
              <input type="radio" name={`${id}-destino`} checked={otro} onChange={() => setOtro(true)} />
              <Icon name="correo" />
              <span>A otro correo</span>
            </label>
          </div>
          {!otro ? <p className={s.ayuda}>Se enviará a {correoUsuario}.</p> : null}
        </fieldset>
      ) : null}
      {otro ? (
        <div className={s.campo}>
          <label htmlFor={`${id}-email`}>Correo de destino</label>
          <input
            id={`${id}-email`}
            type="email"
            inputMode="email"
            autoComplete="email"
            className={s.control}
            placeholder="nombre@empresa.cl"
            value={email}
            maxLength={100}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(error) || undefined}
            data-autofoco={!correoUsuario || undefined}
          />
          <p className={s.ayuda}>Por ejemplo, el de tu encargado de protección de datos o tu asesor.</p>
        </div>
      ) : null}
      <p className={s.notaSuave}>
        <Icon name="filtro" />
        <span><strong>Vista que se enviará:</strong> {descripcionFiltros}.</span>
      </p>
      {error ? (
        <p className="dialogo-error" role="alert">
          <Icon name="alerta" />
          {error}
        </p>
      ) : null}
    </Dialogo>
  );
}

/* ============================================================ selector de categorías */

export function SelectorCategorias({
  catalogo,
  modo,
  valor,
  onCambiar,
  etiqueta,
  ayuda,
  error,
  autofoco = false,
  destacadas,
}: {
  catalogo: CatalogoMapa;
  modo: "datos" | "titulares";
  valor: string[];
  onCambiar: (v: string[]) => void;
  etiqueta: string;
  ayuda?: string;
  error?: string;
  autofoco?: boolean;
  /** Códigos sugeridos (p. ej. los que ya tiene el origen del flujo): se muestran primero y marcados. */
  destacadas?: string[];
}) {
  const id = useId();
  const [busqueda, setBusqueda] = useState("");
  const q = busqueda.trim().toLowerCase();
  const elegido = new Set(valor);
  const sugeridas = new Set(destacadas ?? []);

  const grupos = useMemo(() => {
    if (modo === "titulares") {
      const lista = catalogo.categorias_titulares.filter(
        (c) => !q || c.nombre.toLowerCase().includes(q) || c.descripcion.toLowerCase().includes(q),
      );
      return [{ nombre: "Titulares", items: lista.map((c) => ({ codigo: c.codigo, nombre: c.nombre, ayuda: c.descripcion, sensible: false, nna: c.nna, posibleNna: c.posible_nna })) }];
    }
    return catalogo.grupos_datos
      .map((g) => ({
        nombre: g,
        items: catalogo.categorias_datos
          .filter((c) => c.grupo === g)
          .filter((c) => !q || c.nombre.toLowerCase().includes(q) || c.ejemplos.some((x) => x.toLowerCase().includes(q)))
          .map((c) => ({ codigo: c.codigo, nombre: c.nombre, ayuda: `${c.descripcion} Ej.: ${c.ejemplos.join(", ")}.`, sensible: c.sensible, nna: false, posibleNna: false })),
      }))
      .filter((g) => g.items.length);
  }, [catalogo, modo, q]);

  const alternar = (codigo: string) => {
    onCambiar(elegido.has(codigo) ? valor.filter((x) => x !== codigo) : [...valor, codigo]);
  };
  const sensibles = modo === "datos" ? valor.filter((c) => catalogo.categorias_datos.find((x) => x.codigo === c)?.sensible).length : 0;

  return (
    <div className={s.campo}>
      <span className={s.etiquetaCampo} id={`${id}-titulo`}>{etiqueta}</span>
      <div className={s.selector} role="group" aria-labelledby={`${id}-titulo`} aria-describedby={ayuda ? `${id}-ayuda` : undefined}>
        <div className={s.selectorCabeza}>
          <div className={`input-wrap ${s.selectorBuscar}`}>
            <Icon name="buscar" />
            <input
              type="search"
              className="input"
              placeholder={modo === "datos" ? "Buscar (ej.: salud, correo, IP)" : "Buscar titulares (ej.: clientes)"}
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              aria-label={`Buscar en ${etiqueta.toLowerCase()}`}
              data-autofoco={autofoco || undefined}
            />
          </div>
          <span className={s.selectorConteo} aria-live="polite">
            <strong>{valor.length ? `${valor.length} elegida${valor.length === 1 ? "" : "s"}` : "Ninguna elegida"}</strong>
            {sensibles ? <span className={s.marcaSensible}> · {sensibles} sensible{sensibles === 1 ? "" : "s"}</span> : null}
            {valor.length ? (
              <button type="button" className="link-btn" onClick={() => onCambiar([])}>
                Quitar todas
              </button>
            ) : null}
          </span>
        </div>
        {grupos.length === 0 ? <p className={s.ayuda}>No hay coincidencias con «{busqueda}».</p> : null}
        {grupos.map((g) => (
          <fieldset key={g.nombre} className={s.grupoCategorias}>
            {modo === "datos" ? <legend>{g.nombre}</legend> : <legend className="sr-only">{g.nombre}</legend>}
            <div className={s.opcionesCategoria}>
              {g.items.map((c) => (
                <label key={c.codigo} className={s.pastilla} data-sensible={c.sensible || undefined} data-sugerida={sugeridas.has(c.codigo) || undefined} title={c.ayuda}>
                  <input type="checkbox" checked={elegido.has(c.codigo)} onChange={() => alternar(c.codigo)} />
                  <span>{c.nombre}</span>
                  {c.sensible ? <span className={s.marcaSensible}>SENSIBLE</span> : null}
                  {c.nna ? <span className={s.marcaNna}>NNA</span> : null}
                  {c.posibleNna ? <span className={s.marcaNna} title="Puede incluir menores de 18 años">¿NNA?</span> : null}
                  {sugeridas.has(c.codigo) && !elegido.has(c.codigo) ? <span className={s.marcaSugerida}>sugerida</span> : null}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      {ayuda ? <p className={s.ayuda} id={`${id}-ayuda`}>{ayuda}</p> : null}
      {error ? <p className={s.error} role="alert">{error}</p> : null}
    </div>
  );
}
