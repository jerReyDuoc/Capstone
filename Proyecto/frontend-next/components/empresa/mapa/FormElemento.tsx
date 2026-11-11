"use client";

/**
 * Agregar o editar un elemento del mapa: sistema, base de datos o tercero, con su proveedor,
 * país de alojamiento, responsable interno (cargo o área) y las categorías de datos y de
 * titulares del catálogo común. Si es un tercero: su rol y si hay contrato firmado.
 */
import { useId, useMemo, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { contieneContacto, mensajeError, type CatalogoMapa, type DatosElemento, type ElementoMapa, type TipoElemento } from "@/lib/mapaDatos";
import { Dialogo, SelectorCategorias } from "./Dialogos";
import s from "./mapa.module.css";

const ICONO_TIPO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };
const AYUDA_TIPO: Record<TipoElemento, string> = {
  sistema: "Software donde se capturan o usan datos (ERP, CRM, sitio web, asistente con IA…).",
  base_datos: "Donde se guardan los datos (bases, planillas, repositorios, respaldos…).",
  tercero: "Organización externa que recibe o trata datos (proveedores, socios, autoridades…).",
};

type Errores = Partial<Record<keyof DatosElemento | "general", string>>;

export function FormElemento({
  catalogo,
  elemento,
  tipoInicial = "sistema",
  onGuardar,
  onCerrar,
}: {
  catalogo: CatalogoMapa;
  elemento?: ElementoMapa | null;
  tipoInicial?: TipoElemento;
  onGuardar: (datos: DatosElemento) => Promise<void>;
  onCerrar: () => void;
}) {
  const id = useId();
  const editando = Boolean(elemento);
  const [tipo, setTipo] = useState<TipoElemento>(elemento?.tipo ?? tipoInicial);
  const [nombre, setNombre] = useState(elemento?.nombre ?? "");
  const [subtipo, setSubtipo] = useState(elemento?.subtipo ?? "");
  const [proveedor, setProveedor] = useState(elemento?.proveedor ?? "");
  const [pais, setPais] = useState(elemento?.pais ?? (elemento ? "" : tipoInicial === "tercero" ? "" : catalogo.pais_local));
  const [responsable, setResponsable] = useState(elemento?.responsable ?? "");
  const [descripcion, setDescripcion] = useState(elemento?.descripcion ?? "");
  const [datos, setDatos] = useState<string[]>(elemento?.categorias_datos ?? []);
  const [titulares, setTitulares] = useState<string[]>(elemento?.categorias_titulares ?? []);
  const [nna, setNna] = useState(elemento?.nna_declarado ?? false);
  const [rol, setRol] = useState(elemento?.rol_tercero ?? "");
  const [contrato, setContrato] = useState<"si" | "no" | "">(
    elemento?.contrato_firmado === true ? "si" : elemento?.contrato_firmado === false ? "no" : "",
  );
  const [errores, setErrores] = useState<Errores>({});
  const [ocupado, setOcupado] = useState(false);

  const subtipos = catalogo.subtipos[tipo] ?? [];
  const rolElegido = catalogo.roles_tercero.find((r) => r.codigo === rol);
  const titularNna = titulares.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna);
  const posibleNna = titulares.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.posible_nna);
  const sensibles = useMemo(
    () => datos.filter((c) => catalogo.categorias_datos.find((x) => x.codigo === c)?.sensible),
    [datos, catalogo],
  );
  const fueraDeChile = Boolean(pais) && pais !== catalogo.pais_local;

  const cambiarTipo = (t: TipoElemento) => {
    setTipo(t);
    if (!(catalogo.subtipos[t] ?? []).some((o) => o.codigo === subtipo)) setSubtipo("");
  };

  const validar = (): Errores => {
    const e: Errores = {};
    const n = nombre.trim();
    if (n.length < 2) e.nombre = "Escribe un nombre de al menos 2 caracteres para identificarlo en el mapa.";
    else if (n.length > 120) e.nombre = "Usa como máximo 120 caracteres.";
    if (contieneContacto(responsable)) e.responsable = "Indica el cargo o el área (por ejemplo, «Jefatura de TI»), sin correos, RUT ni teléfonos.";
    for (const [campo, valor] of [["nombre", nombre], ["proveedor", proveedor], ["descripcion", descripcion]] as const) {
      if (!e[campo] && contieneContacto(valor)) e[campo] = "No escribas correos, RUT ni teléfonos de personas: describe el sistema, no a una persona.";
    }
    return e;
  };

  const guardar = async () => {
    const e = validar();
    setErrores(e);
    if (Object.keys(e).length) {
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-form="${id}"] [aria-invalid="true"]`)?.focus());
      return;
    }
    const salida: DatosElemento = {
      tipo,
      nombre: nombre.trim(),
      subtipo: subtipo || null,
      proveedor: proveedor.trim() || null,
      pais: pais || null,
      responsable: responsable.trim() || null,
      descripcion: descripcion.trim() || null,
      categorias_datos: datos,
      categorias_titulares: titulares,
      nna_declarado: nna,
      rol_tercero: tipo === "tercero" ? rol || null : null,
      contrato_firmado: tipo === "tercero" ? (contrato === "si" ? true : contrato === "no" ? false : null) : null,
    };
    setOcupado(true);
    try {
      await onGuardar(salida);
    } catch (err) {
      const campo = err instanceof ErrorBff ? (err.info.campo as keyof DatosElemento | undefined) : undefined;
      setErrores({ [campo ?? "general"]: mensajeError(err, "No pudimos guardar el elemento. Inténtalo de nuevo.") });
      setOcupado(false);
    }
  };

  const campoTexto = (
    campo: "nombre" | "proveedor" | "responsable",
    etiqueta: string,
    valor: string,
    cambiar: (v: string) => void,
    opciones: { obligatorio?: boolean; ayuda?: string; placeholder?: string; autofoco?: boolean } = {},
  ) => (
    <div className={s.campo}>
      <label htmlFor={`${id}-${campo}`}>
        {etiqueta}
        {opciones.obligatorio ? <span className={s.obligatorio} aria-hidden="true">*</span> : null}
      </label>
      <input
        id={`${id}-${campo}`}
        className={s.control}
        value={valor}
        maxLength={120}
        onChange={(e) => cambiar(e.target.value)}
        placeholder={opciones.placeholder}
        aria-required={opciones.obligatorio || undefined}
        aria-invalid={Boolean(errores[campo]) || undefined}
        aria-describedby={`${id}-${campo}-ayuda`}
        data-autofoco={opciones.autofoco || undefined}
      />
      {errores[campo] ? (
        <p className={s.error} id={`${id}-${campo}-ayuda`} role="alert">{errores[campo]}</p>
      ) : (
        <p className={s.ayuda} id={`${id}-${campo}-ayuda`}>{opciones.ayuda ?? ""}</p>
      )}
    </div>
  );

  return (
    <Dialogo
      titulo={editando ? `Editar «${elemento!.nombre}»` : "Agregar al mapa"}
      descripcion={editando ? "Los cambios quedan registrados como una nueva versión del mapa." : "Registra dónde trata datos personales tu empresa. Podrás completar o cambiar la información cuando quieras."}
      onCerrar={onCerrar}
      onEnviar={guardar}
      pie={
        <>
          <p className={s.ayuda}>
            <span className={s.obligatorio}>*</span> Obligatorio. Lo demás puedes completarlo después.
          </p>
          <div>
            <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary" disabled={ocupado}>
              <Icon name="check" />
              {ocupado ? "Guardando…" : editando ? "Guardar cambios" : "Agregar al mapa"}
            </button>
          </div>
        </>
      }
    >
      <div data-form={id} style={{ display: "contents" }}>
        <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className={s.etiquetaCampo}>¿Qué quieres registrar?</legend>
          <div className={s.segmentado}>
            {(["sistema", "base_datos", "tercero"] as TipoElemento[]).map((t) => (
              <label key={t} className={s.segmento}>
                <input type="radio" name={`${id}-tipo`} value={t} checked={tipo === t} onChange={() => cambiarTipo(t)} />
                <Icon name={ICONO_TIPO[t]} />
                <span>{t === "sistema" ? "Sistema o aplicación" : t === "base_datos" ? "Base de datos" : "Tercero o destinatario"}</span>
              </label>
            ))}
          </div>
          <p className={s.ayuda}>{AYUDA_TIPO[tipo]}</p>
        </fieldset>

        <div className={s.rejilla}>
          {campoTexto("nombre", "Nombre", nombre, setNombre, {
            obligatorio: true, autofoco: !editando,
            placeholder: tipo === "tercero" ? "Ej.: Proveedor de nube, Courier" : tipo === "base_datos" ? "Ej.: Base de clientes" : "Ej.: CRM de ventas",
            ayuda: "Un nombre que todos en tu empresa reconozcan.",
          })}
          <div className={s.campo}>
            <label htmlFor={`${id}-subtipo`}>Categoría</label>
            <select id={`${id}-subtipo`} className={`select ${s.control}`} value={subtipo} onChange={(e) => setSubtipo(e.target.value)}>
              <option value="">Elige una categoría</option>
              {subtipos.map((o) => (
                <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
              ))}
            </select>
            <p className={s.ayuda}>Ayuda a detectar riesgos (por ejemplo, un proveedor de IA).</p>
          </div>
          {campoTexto("proveedor", tipo === "tercero" ? "Razón social o marca (opcional)" : "Proveedor o fabricante", proveedor, setProveedor, {
            placeholder: tipo === "tercero" ? "Ej.: nombre comercial del proveedor" : "Ej.: desarrollado internamente, o la empresa que lo provee",
          })}
          <div className={s.campo}>
            <label htmlFor={`${id}-pais`}>País donde se alojan los datos</label>
            <select id={`${id}-pais`} className={`select ${s.control}`} value={pais} onChange={(e) => setPais(e.target.value)} aria-invalid={Boolean(errores.pais) || undefined}>
              <option value="">Aún no lo sé</option>
              {catalogo.paises.map((p) => (
                <option key={p.codigo} value={p.codigo}>{p.nombre}</option>
              ))}
            </select>
            {errores.pais ? (
              <p className={s.error} role="alert">{errores.pais}</p>
            ) : (
              <p className={s.ayuda}>
                {fueraDeChile ? "Los flujos hacia aquí serán transferencias internacionales." : "Revisa el contrato o la configuración del servicio en la nube."}
              </p>
            )}
          </div>
          {campoTexto("responsable", tipo === "tercero" ? "Responsable interno de la relación" : "Responsable interno", responsable, setResponsable, {
            placeholder: "Cargo o área, ej.: Jefatura de TI",
            ayuda: "Indica un cargo o un área, no el nombre ni los datos de una persona.",
          })}
          {tipo === "tercero" ? (
            <div className={s.campo}>
              <label htmlFor={`${id}-rol`}>Rol del tercero</label>
              <select id={`${id}-rol`} className={`select ${s.control}`} value={rol} onChange={(e) => setRol(e.target.value)} aria-describedby={`${id}-rol-ayuda`}>
                <option value="">Elige el rol</option>
                {catalogo.roles_tercero.map((r) => (
                  <option key={r.codigo} value={r.codigo}>{r.nombre}</option>
                ))}
              </select>
              <p className={s.ayuda} id={`${id}-rol-ayuda`}>{rolElegido?.descripcion ?? "¿Trata los datos por cuenta de tu empresa o para sus propios fines?"}</p>
            </div>
          ) : (
            <div />
          )}
          {tipo === "tercero" && (!rolElegido || rolElegido.requiere_contrato) ? (
            <fieldset className={`${s.campo} ${s.ancho}`} style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className={s.etiquetaCampo}>¿Hay un contrato de tratamiento de datos firmado?</legend>
              <div className={s.segmentado}>
                {([["si", "Sí, firmado"], ["no", "No"], ["", "No lo sé"]] as const).map(([v, t]) => (
                  <label key={v || "nose"} className={s.segmento}>
                    <input type="radio" name={`${id}-contrato`} checked={contrato === v} onChange={() => setContrato(v)} />
                    <span>{t}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}
          <div className={`${s.campo} ${s.ancho}`}>
            <label htmlFor={`${id}-descripcion`}>Descripción (opcional)</label>
            <textarea
              id={`${id}-descripcion`}
              className={s.control}
              value={descripcion}
              maxLength={500}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Para qué se usa, qué procesos apoya…"
              aria-invalid={Boolean(errores.descripcion) || undefined}
            />
            {errores.descripcion ? <p className={s.error} role="alert">{errores.descripcion}</p> : <p className={s.ayuda}>{descripcion.length}/500</p>}
          </div>
        </div>

        <SelectorCategorias
          catalogo={catalogo}
          modo="datos"
          valor={datos}
          onCambiar={setDatos}
          etiqueta={tipo === "tercero" ? "Datos personales que recibe o trata" : "Datos personales que trata"}
          ayuda="Elige todas las que correspondan. Las marcadas como sensibles requieren un resguardo reforzado."
          error={errores.categorias_datos}
        />
        {sensibles.length ? (
          <p className={s.alertaInfo} role="status">
            <Icon name="alerta" />
            <span>
              Marcaste {sensibles.length} categoría{sensibles.length === 1 ? "" : "s"} de datos sensibles. Asegúrate de
              registrar un responsable y de que los flujos que salen de aquí viajen cifrados.
            </span>
          </p>
        ) : null}

        <SelectorCategorias
          catalogo={catalogo}
          modo="titulares"
          valor={titulares}
          onCambiar={(v) => {
            setTitulares(v);
            if (v.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna)) setNna(true);
          }}
          etiqueta="¿De quiénes son esos datos?"
          error={errores.categorias_titulares}
        />
        <label className={s.casillaLinea}>
          <input type="checkbox" checked={nna || titularNna} disabled={titularNna} onChange={(e) => setNna(e.target.checked)} />
          <span>
            <strong>Incluye datos de niños, niñas o adolescentes (menores de 18 años)</strong>
            <span className={s.ayuda} style={{ display: "block" }}>
              {titularNna ? "Se marcó porque elegiste «Niños, niñas y adolescentes» entre los titulares." : "Su tratamiento exige un resguardo reforzado y, a veces, la autorización de sus padres o representantes."}
            </span>
          </span>
        </label>
        {posibleNna && !nna && !titularNna ? (
          <p className={s.alertaInfo} data-tono="nna" role="status">
            <Icon name="info" />
            <span>Algunos titulares que elegiste pueden incluir menores de 18 años. Si es así, marca la casilla de arriba.</span>
          </p>
        ) : null}

        {errores.general ? (
          <p className="dialogo-error" role="alert">
            <Icon name="alerta" />
            {errores.general}
          </p>
        ) : null}
      </div>
    </Dialogo>
  );
}
