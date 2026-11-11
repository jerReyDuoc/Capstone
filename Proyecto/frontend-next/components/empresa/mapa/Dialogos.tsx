"use client";

/**
 * Piezas comunes de los formularios del mapa de datos: el diálogo (<dialog> nativo: foco
 * atrapado y Esc), la confirmación de acciones, el envío del informe por correo y el selector
 * de categorías del catálogo común (datos con las sensibles marcadas y titulares con NNA).
 */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import type { CatalogoMapa } from "@/lib/mapaDatos";
import s from "./mapa.module.css";

export function Dialogo({
  titulo,
  descripcion,
  onCerrar,
  onEnviar,
  pie,
  children,
  estrecho = false,
}: {
  titulo: string;
  descripcion?: ReactNode;
  onCerrar: () => void;
  onEnviar?: () => void;
  pie: ReactNode;
  children: ReactNode;
  estrecho?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    // El foco va al primer campo (no al botón Cerrar)
    const primero = d?.querySelector<HTMLElement>("[data-autofoco]");
    primero?.focus();
  }, []);

  return (
    <dialog
      ref={ref}
      className={s.dialogoAncho}
      style={estrecho ? { width: "min(540px, calc(100vw - 24px))" } : undefined}
      aria-labelledby={idTitulo}
      onCancel={(e) => {
        e.preventDefault();
        onCerrar();
      }}
    >
      <form
        className={s.dialogoForm}
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          onEnviar?.();
        }}
      >
        <div className={s.dialogoCabeza}>
          <div>
            <h2 id={idTitulo} className="card-title">{titulo}</h2>
            {descripcion ? <p className="card-sub">{descripcion}</p> : null}
          </div>
          <button type="button" className="icon-btn" onClick={onCerrar} aria-label="Cerrar">
            <Icon name="cerrar" />
          </button>
        </div>
        <div className={s.dialogoCuerpo}>{children}</div>
        <div className={s.dialogoPie}>{pie}</div>
      </form>
    </dialog>
  );
}

export function DialogoConfirmar({
  titulo,
  children,
  textoConfirmar,
  peligro = false,
  onConfirmar,
  onCerrar,
}: {
  titulo: string;
  children: ReactNode;
  textoConfirmar: string;
  peligro?: boolean;
  onConfirmar: () => Promise<void>;
  onCerrar: () => void;
}) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  return (
    <Dialogo
      titulo={titulo}
      estrecho
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
        <div>
          <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={ocupado}
            data-autofoco
            style={peligro ? { background: "var(--alto)", color: "#1a0303" } : undefined}
          >
            {ocupado ? "Un momento…" : textoConfirmar}
          </button>
        </div>
      }
    >
      <div style={{ display: "grid", gap: 12, fontSize: "var(--fs-sm)", color: "var(--text-muted)" }}>{children}</div>
      {error ? (
        <p className="dialogo-error" role="alert">
          <Icon name="alerta" />
          {error}
        </p>
      ) : null}
    </Dialogo>
  );
}

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
      estrecho
      onCerrar={onCerrar}
      onEnviar={enviar}
      pie={
        <div>
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
      <p className={s.ayuda}>
        <strong>Vista que se enviará:</strong> {descripcionFiltros}.
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
}: {
  catalogo: CatalogoMapa;
  modo: "datos" | "titulares";
  valor: string[];
  onCambiar: (v: string[]) => void;
  etiqueta: string;
  ayuda?: string;
  error?: string;
  autofoco?: boolean;
}) {
  const id = useId();
  const [busqueda, setBusqueda] = useState("");
  const q = busqueda.trim().toLowerCase();
  const elegido = new Set(valor);

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
              placeholder={modo === "datos" ? "Buscar (ej.: salud, correo, IP)" : "Buscar titulares"}
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              aria-label={`Buscar en ${etiqueta.toLowerCase()}`}
              data-autofoco={autofoco || undefined}
            />
          </div>
          <span className={s.ayuda} aria-live="polite">
            {valor.length ? `${valor.length} elegida${valor.length === 1 ? "" : "s"}` : "Ninguna elegida"}
            {sensibles ? ` · ${sensibles} sensible${sensibles === 1 ? "" : "s"}` : ""}
            {valor.length ? (
              <>
                {" · "}
                <button type="button" className="link-btn" onClick={() => onCambiar([])}>
                  Quitar todas
                </button>
              </>
            ) : null}
          </span>
        </div>
        {grupos.length === 0 ? <p className={s.ayuda}>No hay coincidencias con «{busqueda}».</p> : null}
        {grupos.map((g) => (
          <fieldset key={g.nombre} className={s.grupoCategorias}>
            {modo === "datos" ? <legend>{g.nombre}</legend> : <legend className="sr-only">{g.nombre}</legend>}
            <div className={s.opcionesCategoria}>
              {g.items.map((c) => (
                <label key={c.codigo} className={s.pastilla} data-sensible={c.sensible || undefined} title={c.ayuda}>
                  <input type="checkbox" checked={elegido.has(c.codigo)} onChange={() => alternar(c.codigo)} />
                  <span>{c.nombre}</span>
                  {c.sensible ? <span className={s.marcaSensible}>SENSIBLE</span> : null}
                  {c.nna ? <span className={s.marcaNna}>NNA</span> : null}
                  {c.posibleNna ? <span className={s.marcaNna} title="Puede incluir menores de 18 años">¿NNA?</span> : null}
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
