"use client";

/**
 * Edición de una propuesta del asistente antes de aceptarla. Muestra solo los campos de su tipo, con las
 * listas de los catálogos del mapa y del registro. Al guardar se envían solo los cambios y la propuesta se
 * acepta con ellos (queda marcada como «aceptada con cambios»). Las validaciones son las mismas que al
 * escribir en el mapa o el registro a mano.
 */
import { useState, type FormEvent, type ReactNode } from "react";
import { cambios, type EstadoAsistente, type PayloadPropuesta, type PlazoPropuesta, type PropuestaApi } from "@/lib/asistente";
import type { CatalogoMapa, TipoElemento } from "@/lib/mapaDatos";
import type { CatalogoRat } from "@/lib/registroActividades";
import a from "./asistente.module.css";

type Opcion = { codigo: string; nombre: string };

export function EditorPropuesta({
  propuesta, referencias, catMapa, catRat, ocupado, alGuardar, alCancelar,
}: {
  propuesta: PropuestaApi;
  referencias: EstadoAsistente["referencias"];
  catMapa: CatalogoMapa;
  catRat: CatalogoRat;
  ocupado: boolean;
  alGuardar: (cambios: PayloadPropuesta) => Promise<void>;
  alCancelar: () => void;
}) {
  const original = propuesta.payload;
  const [d, setD] = useState<PayloadPropuesta>(() => JSON.parse(JSON.stringify(original)) as PayloadPropuesta);
  const id = (campo: string) => `editar-${propuesta.id}-${campo}`;
  const poner = <K extends keyof PayloadPropuesta>(k: K, v: PayloadPropuesta[K]) => setD((x) => ({ ...x, [k]: v }));

  async function guardar(ev: FormEvent) {
    ev.preventDefault();
    await alGuardar(cambios(original, d));
  }

  const elementos: Opcion[] = Object.entries(referencias.elementos).map(([codigo, nombre]) => ({ codigo, nombre }));
  const flujos: Opcion[] = Object.entries(referencias.flujos).map(([codigo, nombre]) => ({ codigo, nombre }));
  const tipo = (d.tipo ?? "sistema") as TipoElemento;

  return (
    <form className={a.editor} onSubmit={guardar} noValidate>
      {propuesta.tipo === "elemento" ? (
        <>
          <Texto id={id("nombre")} etiqueta="Nombre" valor={d.nombre} alCambiar={(v) => poner("nombre", v)} />
          <Lista id={id("tipo")} etiqueta="Qué es" valor={d.tipo} opciones={catMapa.tipos}
            alCambiar={(v) => setD((x) => ({ ...x, tipo: v, subtipo: null }))} sinVacio />
          <Lista id={id("subtipo")} etiqueta="Categoría" valor={d.subtipo} opciones={catMapa.subtipos[tipo] ?? []}
            alCambiar={(v) => poner("subtipo", v)} />
          <Texto id={id("proveedor")} etiqueta="Proveedor (empresa)" valor={d.proveedor} alCambiar={(v) => poner("proveedor", v)} />
          <Lista id={id("pais")} etiqueta="País donde están los datos" valor={d.pais} opciones={catMapa.paises}
            alCambiar={(v) => poner("pais", v)} />
          <Texto id={id("responsable")} etiqueta="Área o cargo responsable" valor={d.responsable}
            ayuda="Un cargo o un área, no una persona." alCambiar={(v) => poner("responsable", v)} />
          <Varios etiqueta="Datos que guarda" valores={d.categorias_datos} opciones={catMapa.categorias_datos}
            alCambiar={(v) => poner("categorias_datos", v)} />
          <Varios etiqueta="De quiénes son los datos" valores={d.categorias_titulares} opciones={catMapa.categorias_titulares}
            alCambiar={(v) => poner("categorias_titulares", v)} />
          {d.tipo === "tercero" ? (
            <>
              <Lista id={id("rol")} etiqueta="Rol del tercero" valor={d.rol_tercero} opciones={catMapa.roles_tercero}
                alCambiar={(v) => poner("rol_tercero", v)} />
              <SiNo id={id("contrato")} etiqueta="¿Hay contrato de tratamiento firmado?" valor={d.contrato_firmado}
                alCambiar={(v) => poner("contrato_firmado", v)} />
            </>
          ) : null}
        </>
      ) : null}

      {propuesta.tipo === "flujo" ? (
        <>
          <Lista id={id("origen")} etiqueta="Desde" valor={d.origen} opciones={elementos} alCambiar={(v) => poner("origen", v)} sinVacio />
          <Lista id={id("destino")} etiqueta="Hacia" valor={d.destino} opciones={elementos} alCambiar={(v) => poner("destino", v)} sinVacio />
          <Texto id={id("finalidad")} etiqueta="Para qué se envían" valor={d.finalidad} alCambiar={(v) => poner("finalidad", v)} />
          <Varios etiqueta="Datos que viajan" valores={d.categorias_datos} opciones={catMapa.categorias_datos}
            alCambiar={(v) => poner("categorias_datos", v)} />
          <Lista id={id("garantia")} etiqueta="Garantía del envío (si sale de Chile)" valor={d.garantia}
            opciones={catMapa.garantias} alCambiar={(v) => poner("garantia", v)} />
          <SiNo id={id("cifrado")} etiqueta="¿Viajan cifrados?" valor={d.cifrado} alCambiar={(v) => poner("cifrado", v)} />
        </>
      ) : null}

      {propuesta.tipo === "actividad" ? (
        <>
          <Texto id={id("nombre")} etiqueta="Nombre de la actividad" valor={d.nombre} alCambiar={(v) => poner("nombre", v)} />
          <Texto id={id("area")} etiqueta="Área que la lleva" valor={d.area} alCambiar={(v) => poner("area", v)} />
          <Campo id={id("finalidades")} etiqueta="Para qué (una por línea)">
            <textarea id={id("finalidades")} rows={3} value={(d.finalidades ?? []).join("\n")}
              onChange={(e) => poner("finalidades", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} />
          </Campo>
          <Varios etiqueta="Sistemas que usa" valores={d.elementos} opciones={elementos} alCambiar={(v) => poner("elementos", v)} />
          <Varios etiqueta="Envíos de datos" valores={d.flujos} opciones={flujos} alCambiar={(v) => poner("flujos", v)} />
          <Lista id={id("base")} etiqueta="Base legal" valor={d.base_licitud} opciones={catRat.bases_licitud}
            alCambiar={(v) => poner("base_licitud", v)} />
          {d.base_licitud === "interes_legitimo" ? (
            <Texto id={id("interes")} etiqueta="¿Cuál es el interés legítimo y cómo lo ponderaste?" valor={d.interes_legitimo}
              alCambiar={(v) => poner("interes_legitimo", v)} />
          ) : null}
          <Lista id={id("sensibles")} etiqueta="Base para datos sensibles (si los hay)" valor={d.base_sensibles}
            opciones={catRat.bases_sensibles} alCambiar={(v) => poner("base_sensibles", v)} />
          <Plazos idBase={id("plazos")} plazos={d.plazos ?? []} catMapa={catMapa} catRat={catRat}
            alCambiar={(v) => poner("plazos", v)} />
        </>
      ) : null}

      <div className={a.acciones}>
        <button type="submit" className="btn btn-primary btn-sm" disabled={ocupado}>
          {ocupado ? "Guardando…" : "Guardar y aceptar"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={alCancelar} disabled={ocupado}>Cancelar</button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------ campos */
function Campo({ id, etiqueta, ayuda, children }: { id: string; etiqueta: string; ayuda?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id} className="field-label">{etiqueta}</label>
      {children}
      {ayuda ? <span className={a.ayuda}>{ayuda}</span> : null}
    </div>
  );
}

function Texto({ id, etiqueta, valor, ayuda, alCambiar }: {
  id: string; etiqueta: string; valor: string | null | undefined; ayuda?: string; alCambiar: (v: string | null) => void;
}) {
  return (
    <Campo id={id} etiqueta={etiqueta} ayuda={ayuda}>
      <input id={id} type="text" value={valor ?? ""} onChange={(e) => alCambiar(e.target.value.trim() ? e.target.value : null)} />
    </Campo>
  );
}

function Lista({ id, etiqueta, valor, opciones, alCambiar, sinVacio }: {
  id: string; etiqueta: string; valor: string | null | undefined; opciones: Opcion[];
  alCambiar: (v: string | null) => void; sinVacio?: boolean;
}) {
  return (
    <Campo id={id} etiqueta={etiqueta}>
      <select id={id} value={valor ?? ""} onChange={(e) => alCambiar(e.target.value || null)}>
        {!sinVacio || !valor ? <option value="">Sin elegir</option> : null}
        {opciones.map((o) => <option key={o.codigo} value={o.codigo}>{o.nombre}</option>)}
      </select>
    </Campo>
  );
}

function SiNo({ id, etiqueta, valor, alCambiar }: {
  id: string; etiqueta: string; valor: boolean | null | undefined; alCambiar: (v: boolean | null) => void;
}) {
  return (
    <Campo id={id} etiqueta={etiqueta}>
      <select id={id} value={valor == null ? "" : valor ? "si" : "no"}
        onChange={(e) => alCambiar(e.target.value === "" ? null : e.target.value === "si")}>
        <option value="">No lo sé</option>
        <option value="si">Sí</option>
        <option value="no">No</option>
      </select>
    </Campo>
  );
}

function Varios({ etiqueta, valores, opciones, alCambiar }: {
  etiqueta: string; valores: string[] | undefined; opciones: Opcion[]; alCambiar: (v: string[]) => void;
}) {
  const elegidos = new Set(valores ?? []);
  return (
    <fieldset className={a.varios}>
      <legend className="field-label">{etiqueta}</legend>
      {opciones.length === 0 ? <p className={a.ayuda}>No hay opciones todavía.</p> : null}
      {opciones.map((o) => (
        <label key={o.codigo} className={a.casilla}>
          <input type="checkbox" checked={elegidos.has(o.codigo)}
            onChange={(e) => alCambiar(e.target.checked ? [...elegidos, o.codigo] : [...elegidos].filter((x) => x !== o.codigo))} />
          {o.nombre}
        </label>
      ))}
    </fieldset>
  );
}

function Plazos({ idBase, plazos, catMapa, catRat, alCambiar }: {
  idBase: string; plazos: PlazoPropuesta[]; catMapa: CatalogoMapa; catRat: CatalogoRat; alCambiar: (v: PlazoPropuesta[]) => void;
}) {
  const [nueva, setNueva] = useState("");
  const usadas = new Set(plazos.map((p) => p.categoria));
  const nombreDato = (c: string) => catMapa.categorias_datos.find((x) => x.codigo === c)?.nombre ?? c;
  const cambiar = (i: number, cambio: Partial<PlazoPropuesta>) =>
    alCambiar(plazos.map((p, j) => (j === i ? { ...p, ...cambio } : p)));

  return (
    <fieldset className={a.varios}>
      <legend className="field-label">Cuánto tiempo se guarda cada dato</legend>
      {plazos.map((p, i) => (
        <div key={p.categoria} className={a.plazo}>
          <span>{nombreDato(p.categoria)}</span>
          <label className="sr-only" htmlFor={`${idBase}-${i}-n`}>Plazo</label>
          <input id={`${idBase}-${i}-n`} type="number" min={1} inputMode="numeric" value={p.plazo ?? ""}
            onChange={(e) => cambiar(i, { plazo: e.target.value ? Math.max(1, Math.trunc(Number(e.target.value))) : null })} />
          <label className="sr-only" htmlFor={`${idBase}-${i}-u`}>Unidad</label>
          <select id={`${idBase}-${i}-u`} value={p.unidad ?? ""} onChange={(e) => cambiar(i, { unidad: e.target.value || null })}>
            <option value="">Unidad</option>
            {catRat.unidades_plazo.map((o) => <option key={o.codigo} value={o.codigo}>{o.nombre}</option>)}
          </select>
          <label className="sr-only" htmlFor={`${idBase}-${i}-d`}>Desde cuándo</label>
          <select id={`${idBase}-${i}-d`} value={p.desde ?? ""} onChange={(e) => cambiar(i, { desde: e.target.value || null })}>
            <option value="">Desde…</option>
            {catRat.inicios_plazo.map((o) => <option key={o.codigo} value={o.codigo}>{o.nombre}</option>)}
          </select>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => alCambiar(plazos.filter((_, j) => j !== i))}>
            Quitar<span className="sr-only"> el plazo de {nombreDato(p.categoria)}</span>
          </button>
        </div>
      ))}
      <div className={a.plazo}>
        <label className="sr-only" htmlFor={`${idBase}-nueva`}>Agregar un plazo para</label>
        <select id={`${idBase}-nueva`} value={nueva} onChange={(e) => setNueva(e.target.value)}>
          <option value="">Agregar un plazo para…</option>
          {catMapa.categorias_datos.filter((c) => !usadas.has(c.codigo)).map((c) => (
            <option key={c.codigo} value={c.codigo}>{c.nombre}</option>
          ))}
        </select>
        <button type="button" className="btn btn-ghost btn-sm" disabled={!nueva} onClick={() => {
          alCambiar([...plazos, { categoria: nueva, plazo: null, unidad: null, desde: null, fundamento: null }]);
          setNueva("");
        }}>Agregar</button>
      </div>
    </fieldset>
  );
}
