"use client";

/**
 * Agregar o editar un elemento del mapa (sistema, base de datos o tercero) con un asistente por pasos:
 *   1. Tipo                    qué se registra, con ejemplos de cada tipo.
 *   2. Identificación          nombre, categoría, proveedor y para qué se usa.
 *   3. Ubicación y responsable país de alojamiento, responsable interno y, si es un tercero, su rol y contrato.
 *   4. Datos personales        categorías del catálogo común (las sensibles quedan marcadas).
 *   5. Titulares               de quiénes son los datos (y si incluye niños, niñas o adolescentes).
 *   6. Revisión                resumen, lo que conviene completar y los riesgos que se detectarán.
 * Al editar se puede saltar a cualquier paso y guardar en cualquier momento.
 */
import { useId, useMemo, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  contieneContacto, mensajeError, nombreDato, nombreOpcion, nombrePais, nombreSubtipo, nombreTitular,
  type CatalogoMapa, type DatosElemento, type ElementoMapa, type TipoElemento,
} from "@/lib/mapaDatos";
import { Consejo, Dialogo, EncabezadoPaso, IndicadorPasos, SelectorCategorias, type PasoAsistente } from "./Dialogos";
import s from "./mapa.module.css";

const ICONO_TIPO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };
const TIPOS: { tipo: TipoElemento; titulo: string; texto: string; ejemplos: string }[] = [
  {
    tipo: "sistema", titulo: "Sistema o aplicación",
    texto: "Software donde se capturan, consultan o usan datos personales.",
    ejemplos: "ERP, CRM, sitio web, app móvil, sistema de remuneraciones, asistente con IA",
  },
  {
    tipo: "base_datos", titulo: "Base de datos o repositorio",
    texto: "Lugar donde se guardan los datos, aunque no sea un software.",
    ejemplos: "Base de clientes, planillas Excel, carpeta compartida, respaldos, archivo en papel",
  },
  {
    tipo: "tercero", titulo: "Tercero o destinatario",
    texto: "Organización externa que recibe datos de tu empresa o los trata por su cuenta.",
    ejemplos: "Proveedor de nube, courier, pasarela de pagos, banco, autoridad, proveedor de IA",
  },
];

type Errores = Partial<Record<keyof DatosElemento | "general", string>>;

/** En qué paso está cada campo (para llevar al usuario al error que devuelva el servidor). */
const PASO_DE_CAMPO: Partial<Record<keyof DatosElemento, number>> = {
  tipo: 0, nombre: 1, subtipo: 1, proveedor: 1, descripcion: 1, pais: 2, responsable: 2, rol_tercero: 2,
  contrato_firmado: 2, categorias_datos: 3, categorias_titulares: 4, nna_declarado: 4,
};

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
  const [paso, setPaso] = useState(editando ? 1 : 0);
  const [tipo, setTipo] = useState<TipoElemento>(elemento?.tipo ?? tipoInicial);
  const [nombre, setNombre] = useState(elemento?.nombre ?? "");
  const [subtipo, setSubtipo] = useState(elemento?.subtipo ?? "");
  const [proveedor, setProveedor] = useState(elemento?.proveedor ?? "");
  const [pais, setPais] = useState(elemento?.pais ?? (elemento ? "" : tipoInicial === "tercero" ? "" : catalogo.pais_local));
  const [paisTocado, setPaisTocado] = useState(editando);
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

  const esTercero = tipo === "tercero";
  const subtipos = catalogo.subtipos[tipo] ?? [];
  const rolElegido = catalogo.roles_tercero.find((r) => r.codigo === rol);
  const requiereContrato = esTercero && (!rolElegido || Boolean(rolElegido.requiere_contrato));
  const titularNna = titulares.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna);
  const posibleNna = titulares.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.posible_nna);
  const sensibles = useMemo(
    () => datos.filter((c) => catalogo.categorias_datos.find((x) => x.codigo === c)?.sensible),
    [datos, catalogo],
  );
  const fueraDeChile = Boolean(pais) && pais !== catalogo.pais_local;
  const tipoInfo = TIPOS.find((t) => t.tipo === tipo)!;

  const cambiarTipo = (t: TipoElemento) => {
    setTipo(t);
    if (!(catalogo.subtipos[t] ?? []).some((o) => o.codigo === subtipo)) setSubtipo("");
    // El país por defecto (Chile) es para lo interno: a un tercero se le pregunta
    if (!paisTocado) setPais(t === "tercero" ? "" : catalogo.pais_local);
  };

  /* ---------------------------------------------------------------- validación por paso */
  const erroresDe = (i: number): Errores => {
    const e: Errores = {};
    if (i === 1) {
      const n = nombre.trim();
      if (n.length < 2) e.nombre = "Escribe un nombre de al menos 2 caracteres para reconocerlo en el mapa.";
      else if (n.length > 120) e.nombre = "Usa como máximo 120 caracteres.";
      for (const [campo, valor] of [["nombre", nombre], ["proveedor", proveedor], ["descripcion", descripcion]] as const) {
        if (!e[campo] && contieneContacto(valor)) e[campo] = "No escribas correos, RUT ni teléfonos de personas: describe el sistema, no a una persona.";
      }
    }
    if (i === 2 && contieneContacto(responsable)) {
      e.responsable = "Indica el cargo o el área (por ejemplo, «Jefatura de TI»), sin correos, RUT ni teléfonos.";
    }
    return e;
  };
  const todosLosErrores = (): Errores => ({ ...erroresDe(1), ...erroresDe(2) });

  const enfocarError = () =>
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-form="${id}"] [aria-invalid="true"]`)?.focus());

  const ir = (destino: number) => {
    // Al avanzar se valida el paso actual; al retroceder no
    if (destino > paso) {
      const e = erroresDe(paso);
      if (Object.keys(e).length) {
        setErrores(e);
        enfocarError();
        return;
      }
    }
    setErrores({});
    setPaso(destino);
  };

  const guardar = async () => {
    const e = todosLosErrores();
    if (Object.keys(e).length) {
      setErrores(e);
      setPaso(Math.min(...Object.keys(e).map((k) => PASO_DE_CAMPO[k as keyof DatosElemento] ?? 1)));
      enfocarError();
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
      nna_declarado: nna || titularNna,
      rol_tercero: esTercero ? rol || null : null,
      contrato_firmado: esTercero ? (contrato === "si" ? true : contrato === "no" ? false : null) : null,
    };
    setOcupado(true);
    try {
      await onGuardar(salida);
    } catch (err) {
      const campo = err instanceof ErrorBff ? (err.info.campo as keyof DatosElemento | undefined) : undefined;
      setErrores({ [campo ?? "general"]: mensajeError(err, "No pudimos guardar el elemento. Inténtalo de nuevo.") });
      if (campo && PASO_DE_CAMPO[campo] != null) setPaso(PASO_DE_CAMPO[campo]!);
      setOcupado(false);
    }
  };

  /* ---------------------------------------------------------------- pasos */
  const nombreCorto = nombre.trim() || "Sin nombre";
  const pasos: PasoAsistente[] = [
    { titulo: "Tipo", resumen: tipoInfo.titulo, completo: true },
    { titulo: "Identificación", resumen: nombre.trim() ? nombreCorto : "Nombre y uso", completo: nombre.trim().length >= 2, conError: Boolean(errores.nombre || errores.proveedor || errores.descripcion) },
    { titulo: "Ubicación", resumen: pais ? nombrePais(catalogo, pais) : "País y responsable", completo: Boolean(pais && (esTercero ? rol : responsable.trim())), conError: Boolean(errores.responsable || errores.pais) },
    { titulo: "Datos", resumen: datos.length ? `${datos.length} categoría${datos.length === 1 ? "" : "s"}` : "Qué datos trata", completo: datos.length > 0 },
    { titulo: "Titulares", resumen: titulares.length ? `${titulares.length} grupo${titulares.length === 1 ? "" : "s"}` : "De quiénes son", completo: titulares.length > 0 },
    { titulo: "Revisión", resumen: "Confirma y guarda" },
  ];
  const ultimo = pasos.length - 1;

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
        {opciones.obligatorio ? <span className={s.obligatorio} aria-hidden="true">*</span> : <span className={s.opcional}>opcional</span>}
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
      ) : opciones.ayuda ? (
        <p className={s.ayuda} id={`${id}-${campo}-ayuda`}>{opciones.ayuda}</p>
      ) : null}
    </div>
  );

  /* ---------------------------------------------------------------- recomendaciones (revisión) */
  const recomendaciones: { tono: "riesgo" | "mejora"; texto: string; paso: number }[] = [];
  if (!pais) recomendaciones.push({ tono: "riesgo", texto: "Sin país de alojamiento no sabremos si los flujos hacia aquí son transferencias internacionales.", paso: 2 });
  if (!esTercero && !responsable.trim()) recomendaciones.push({ tono: sensibles.length ? "riesgo" : "mejora", texto: "Asigna un responsable interno (cargo o área) que responda por los accesos y la seguridad.", paso: 2 });
  if (esTercero && !rol) recomendaciones.push({ tono: "mejora", texto: "Indica el rol del tercero: define si necesita un contrato de tratamiento.", paso: 2 });
  if (requiereContrato && contrato !== "si") recomendaciones.push({ tono: "riesgo", texto: "Si recibe datos sin un contrato de tratamiento confirmado, aparecerá como un riesgo.", paso: 2 });
  if (!esTercero && !datos.length) recomendaciones.push({ tono: "mejora", texto: "Elige qué datos personales trata: es la base del registro de actividades.", paso: 3 });
  if (!esTercero && !titulares.length) recomendaciones.push({ tono: "mejora", texto: "Indica de quiénes son los datos (clientes, trabajadores…).", paso: 4 });
  if (!subtipo) recomendaciones.push({ tono: "mejora", texto: "Elige una categoría: ayuda a detectar riesgos, por ejemplo, si es un proveedor de IA.", paso: 1 });

  const contenido = () => {
    switch (paso) {
      case 0:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={1} titulo="¿Qué quieres agregar al mapa?">
              Elige el tipo. Si dudas: los sistemas <strong>usan</strong> los datos, las bases los <strong>guardan</strong> y
              los terceros los <strong>reciben</strong> desde fuera de tu empresa.
            </EncabezadoPaso>
            <fieldset className={s.tarjetasTipo}>
              <legend className="sr-only">Tipo de elemento</legend>
              {TIPOS.map((t) => (
                <label key={t.tipo} className={s.tarjetaTipo} data-tipo={t.tipo}>
                  <input type="radio" name={`${id}-tipo`} value={t.tipo} checked={tipo === t.tipo} onChange={() => cambiarTipo(t.tipo)} data-autofoco={tipo === t.tipo || undefined} />
                  <span className={s.tarjetaTipoIcono}><Icon name={ICONO_TIPO[t.tipo]} /></span>
                  <span className={s.tarjetaTipoTitulo}>{t.titulo}</span>
                  <span className={s.tarjetaTipoTexto}>{t.texto}</span>
                  <span className={s.tarjetaTipoEjemplos}><strong>Ejemplos:</strong> {t.ejemplos}.</span>
                  <span className={s.tarjetaTipoCheck} aria-hidden="true"><Icon name="check" /></span>
                </label>
              ))}
            </fieldset>
          </div>
        );
      case 1:
        return (
          <div className={s.pasoConConsejo}>
            <div className={s.pasoCuerpo}>
              <EncabezadoPaso numero={2} titulo={`Identifica ${esTercero ? "al tercero" : tipo === "base_datos" ? "la base de datos" : "el sistema"}`}>
                Un nombre que todos en tu empresa reconozcan y, si quieres, para qué se usa.
              </EncabezadoPaso>
              <div className={s.rejilla}>
                {campoTexto("nombre", "Nombre", nombre, setNombre, {
                  obligatorio: true, autofoco: true,
                  placeholder: esTercero ? "Ej.: Courier de despachos" : tipo === "base_datos" ? "Ej.: Base de clientes" : "Ej.: CRM de ventas",
                  ayuda: "Es el texto que verás en el recuadro del mapa.",
                })}
                <div className={s.campo}>
                  <label htmlFor={`${id}-subtipo`}>Categoría <span className={s.opcional}>recomendado</span></label>
                  <select id={`${id}-subtipo`} className={`select ${s.control}`} value={subtipo} onChange={(e) => setSubtipo(e.target.value)}>
                    <option value="">Elige una categoría</option>
                    {subtipos.map((o) => (
                      <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
                    ))}
                  </select>
                  <p className={s.ayuda}>{subtipo ? subtipos.find((o) => o.codigo === subtipo)?.descripcion ?? "Nos ayuda a detectar riesgos." : "Nos ayuda a detectar riesgos (por ejemplo, un proveedor de IA)."}</p>
                </div>
                {campoTexto("proveedor", esTercero ? "Razón social o marca" : "Proveedor o fabricante", proveedor, setProveedor, {
                  placeholder: esTercero ? "Ej.: nombre comercial del proveedor" : "Ej.: desarrollo propio, o la empresa que lo provee",
                })}
                <div className={`${s.campo} ${s.ancho}`}>
                  <label htmlFor={`${id}-descripcion`}>¿Para qué se usa? <span className={s.opcional}>opcional</span></label>
                  <textarea
                    id={`${id}-descripcion`}
                    className={s.control}
                    value={descripcion}
                    maxLength={500}
                    onChange={(e) => setDescripcion(e.target.value)}
                    placeholder={esTercero ? "Ej.: despacha los pedidos de la tienda en línea" : "Ej.: registra las ventas y el historial de compra de los clientes"}
                    aria-invalid={Boolean(errores.descripcion) || undefined}
                  />
                  {errores.descripcion ? <p className={s.error} role="alert">{errores.descripcion}</p> : <p className={s.ayuda}>{descripcion.length}/500</p>}
                </div>
              </div>
            </div>
            <Consejo>
              El nombre y la categoría permiten reconocerlo en el diagrama, en el inventario y en el registro de
              actividades. No escribas datos de personas: describe {esTercero ? "a la organización" : "el sistema"}.
            </Consejo>
          </div>
        );
      case 2:
        return (
          <div className={s.pasoConConsejo}>
            <div className={s.pasoCuerpo}>
              <EncabezadoPaso numero={3} titulo="¿Dónde están los datos y quién responde?">
                El país define si hay transferencias internacionales; el responsable, quién controla los accesos.
              </EncabezadoPaso>
              <div className={s.rejilla}>
                <div className={s.campo}>
                  <label htmlFor={`${id}-pais`}>País donde se alojan los datos <span className={s.opcional}>recomendado</span></label>
                  <select
                    id={`${id}-pais`}
                    className={`select ${s.control}`}
                    value={pais}
                    onChange={(e) => {
                      setPais(e.target.value);
                      setPaisTocado(true);
                    }}
                    aria-invalid={Boolean(errores.pais) || undefined}
                    data-autofoco
                  >
                    <option value="">Aún no lo sé</option>
                    {catalogo.paises.map((p) => (
                      <option key={p.codigo} value={p.codigo}>{p.nombre}</option>
                    ))}
                  </select>
                  {errores.pais ? <p className={s.error} role="alert">{errores.pais}</p> : (
                    <p className={s.ayuda}>Si es un servicio en la nube, revisa el contrato o la configuración de la cuenta.</p>
                  )}
                </div>
                {campoTexto("responsable", esTercero ? "Responsable interno de la relación" : "Responsable interno", responsable, setResponsable, {
                  placeholder: "Cargo o área, ej.: Jefatura de TI",
                  ayuda: "Un cargo o un área, no el nombre ni los datos de una persona.",
                })}
              </div>
              {fueraDeChile ? (
                <p className={s.alertaInfo} role="status">
                  <Icon name="globo" />
                  <span>
                    Los datos están en <strong>{nombrePais(catalogo, pais)}</strong>: los flujos que lleguen aquí desde Chile
                    serán transferencias internacionales y te pediremos su garantía.
                  </span>
                </p>
              ) : null}
              {esTercero ? (
                <>
                  <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend className={s.etiquetaCampo}>¿Qué rol tiene este tercero?</legend>
                    <div className={s.opcionesRol}>
                      {catalogo.roles_tercero.map((r) => (
                        <label key={r.codigo} className={s.opcionRol}>
                          <input type="radio" name={`${id}-rol`} checked={rol === r.codigo} onChange={() => setRol(r.codigo)} />
                          <span className={s.opcionRolTitulo}>{r.nombre}</span>
                          {r.descripcion ? <span className={s.opcionRolTexto}>{r.descripcion}</span> : null}
                        </label>
                      ))}
                      <label className={s.opcionRol}>
                        <input type="radio" name={`${id}-rol`} checked={!rol} onChange={() => setRol("")} />
                        <span className={s.opcionRolTitulo}>Aún no lo sé</span>
                        <span className={s.opcionRolTexto}>Podrás indicarlo después.</span>
                      </label>
                    </div>
                  </fieldset>
                  {requiereContrato ? (
                    <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
                      <legend className={s.etiquetaCampo}>¿Hay un contrato de tratamiento de datos firmado con este tercero?</legend>
                      <div className={s.segmentado}>
                        {([["si", "Sí, firmado", "check"], ["no", "No", "cerrar"], ["", "No lo sé", "info"]] as const).map(([v, t, ic]) => (
                          <label key={v || "nose"} className={s.segmento}>
                            <input type="radio" name={`${id}-contrato`} checked={contrato === v} onChange={() => setContrato(v)} />
                            <Icon name={ic} />
                            <span>{t}</span>
                          </label>
                        ))}
                      </div>
                      <p className={s.ayuda}>Cuando un tercero trata datos por cuenta de tu empresa, la ley exige un contrato que fije finalidad, seguridad y confidencialidad.</p>
                    </fieldset>
                  ) : null}
                </>
              ) : null}
            </div>
            <Consejo>
              {esTercero
                ? "El rol indica si el tercero trata los datos por encargo de tu empresa (y necesita un contrato) o para sus propios fines. Sin esta información no podemos evaluar el riesgo."
                : "Saber quién responde por cada sistema ayuda a gestionar accesos, incidentes y plazos de conservación. Con datos sensibles, es obligatorio en la práctica."}
            </Consejo>
          </div>
        );
      case 3:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={4} titulo={esTercero ? "¿Qué datos personales recibe o trata?" : "¿Qué datos personales trata?"}>
              Marca todas las categorías que correspondan. Pasa el cursor sobre una para ver ejemplos. Las marcadas como
              <span className={s.marcaSensible}> SENSIBLE </span> requieren un resguardo reforzado.
            </EncabezadoPaso>
            <SelectorCategorias
              catalogo={catalogo}
              modo="datos"
              valor={datos}
              onCambiar={setDatos}
              etiqueta={esTercero ? "Datos que recibe o trata" : "Datos que trata"}
              error={errores.categorias_datos}
              autofoco
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
          </div>
        );
      case 4:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={5} titulo="¿De quiénes son esos datos?">
              Los titulares son las personas a quienes pertenecen los datos: clientes, trabajadores, postulantes…
            </EncabezadoPaso>
            <SelectorCategorias
              catalogo={catalogo}
              modo="titulares"
              valor={titulares}
              onCambiar={(v) => {
                setTitulares(v);
                if (v.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna)) setNna(true);
              }}
              etiqueta="Titulares"
              error={errores.categorias_titulares}
              autofoco
            />
            <label className={s.casillaTarjeta}>
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
          </div>
        );
      default:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={6} titulo="Revisa antes de guardar">
              Así quedará en tu mapa. Puedes volver a cualquier paso con «Cambiar».
            </EncabezadoPaso>
            <div className={s.resumenRevision}>
              <FilaRevision titulo="Tipo" onCambiar={() => setPaso(0)}>
                <Icon name={ICONO_TIPO[tipo]} /> {tipoInfo.titulo}{subtipo ? ` · ${nombreSubtipo(catalogo, tipo, subtipo)}` : ""}
              </FilaRevision>
              <FilaRevision titulo="Nombre" onCambiar={() => setPaso(1)}>
                <strong>{nombreCorto}</strong>{proveedor.trim() ? ` · ${proveedor.trim()}` : ""}
                {descripcion.trim() ? <small>{descripcion.trim()}</small> : null}
              </FilaRevision>
              <FilaRevision titulo="Ubicación" onCambiar={() => setPaso(2)}>
                {pais ? nombrePais(catalogo, pais) : <span className={s.sinDato}>País sin informar</span>}
                {" · "}
                {responsable.trim() || <span className={s.sinDato}>sin responsable</span>}
                {esTercero ? <small>Rol: {rol ? nombreOpcion(catalogo.roles_tercero, rol) : "sin indicar"}{requiereContrato ? ` · contrato: ${contrato === "si" ? "firmado" : contrato === "no" ? "no hay" : "por confirmar"}` : ""}</small> : null}
              </FilaRevision>
              <FilaRevision titulo="Datos" onCambiar={() => setPaso(3)}>
                {datos.length ? datos.map((c) => nombreDato(catalogo, c)).join(", ") : <span className={s.sinDato}>Ninguno elegido</span>}
                {sensibles.length ? <small className={s.marcaSensible}>{sensibles.length} sensible{sensibles.length === 1 ? "" : "s"}</small> : null}
              </FilaRevision>
              <FilaRevision titulo="Titulares" onCambiar={() => setPaso(4)}>
                {titulares.length ? titulares.map((c) => nombreTitular(catalogo, c)).join(", ") : <span className={s.sinDato}>Ninguno elegido</span>}
                {nna || titularNna ? <small className={s.marcaNna}>Incluye niños, niñas o adolescentes</small> : null}
              </FilaRevision>
            </div>
            {recomendaciones.length ? (
              <div className={s.recomendaciones}>
                <h4>Para que tu mapa quede completo</h4>
                <ul>
                  {recomendaciones.map((r) => (
                    <li key={r.texto} data-tono={r.tono}>
                      <Icon name={r.tono === "riesgo" ? "alerta" : "info"} />
                      <span>{r.texto}</span>
                      <button type="button" className="link-btn" onClick={() => setPaso(r.paso)}>Completar</button>
                    </li>
                  ))}
                </ul>
                <p className={s.ayuda}>Puedes guardar igual y completarlo después desde la ficha.</p>
              </div>
            ) : (
              <p className={s.alertaInfo} data-tono="ok" role="status">
                <Icon name="check" />
                <span>Todo listo: tiene la información clave para el mapa y el registro de actividades.</span>
              </p>
            )}
          </div>
        );
    }
  };

  const botonGuardar = (
    <button type="button" className="btn btn-primary" onClick={guardar} disabled={ocupado}>
      <Icon name="check" />
      {ocupado ? "Guardando…" : editando ? "Guardar cambios" : "Agregar al mapa"}
    </button>
  );

  return (
    <Dialogo
      tamano="lg"
      icono={ICONO_TIPO[tipo]}
      antetitulo={editando ? "Editar elemento" : "Nuevo elemento del mapa"}
      titulo={editando ? elemento!.nombre : "Agregar al mapa"}
      descripcion={editando ? "Los cambios quedan registrados como una nueva versión del mapa." : "Te guiamos paso a paso. Solo el nombre es obligatorio: lo demás puedes completarlo después."}
      onCerrar={onCerrar}
      onEnviar={() => (paso < ultimo && !editando ? ir(paso + 1) : void guardar())}
      cabeceraExtra={<IndicadorPasos pasos={pasos} actual={paso} onIr={ir} libre={editando} />}
      pie={
        <>
          <span className={s.pieProgreso}>Paso {paso + 1} de {pasos.length}</span>
          <div className={s.modalAcciones}>
            {paso > 0 ? (
              <button type="button" className="btn btn-ghost" onClick={() => ir(paso - 1)} disabled={ocupado}>
                <Icon name="flechaIzq" />
                Anterior
              </button>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>Cancelar</button>
            )}
            {paso < ultimo ? (
              <button type="button" className={`btn ${editando ? "btn-ghost" : "btn-primary"}`} onClick={() => ir(paso + 1)} disabled={ocupado}>
                Siguiente
                <Icon name="flecha" />
              </button>
            ) : null}
            {editando || paso === ultimo ? botonGuardar : null}
          </div>
        </>
      }
    >
      <div data-form={id} className={s.contenidoPaso} key={paso}>
        {contenido()}
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

function FilaRevision({ titulo, onCambiar, children }: { titulo: string; onCambiar: () => void; children: ReactNode }) {
  return (
    <div className={s.filaRevision}>
      <span className={s.filaRevisionTitulo}>{titulo}</span>
      <span className={s.filaRevisionValor}>{children}</span>
      <button type="button" className="link-btn" onClick={onCambiar}>Cambiar</button>
    </div>
  );
}
