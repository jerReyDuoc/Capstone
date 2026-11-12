"use client";

/**
 * Agregar o editar un flujo de datos con un asistente por pasos:
 *   1. Recorrido     de qué elemento salen y a cuál llegan, con la vista previa del recorrido y lo que se
 *                    detecta solo (transferencia internacional, tercero sin contrato, país sin informar).
 *   2. Datos         qué datos viajan y de quiénes (con atajos para copiar lo del origen).
 *   3. Cómo y para qué  finalidad, frecuencia, medio, cifrado y, si sale de Chile, la garantía.
 *   4. Revisión      resumen y los riesgos que se detectarán al guardarlo.
 * Al editar se puede saltar a cualquier paso y guardar en cualquier momento.
 */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  contieneContacto, esInternacional, ETIQUETA_TIPO_PLURAL, mensajeError, nombreDato, nombreOpcion, nombrePais, nombreTitular,
  type CatalogoMapa, type DatosFlujo, type ElementoMapa, type FlujoMapa, type Severidad, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import { Consejo, Dialogo, EncabezadoPaso, IndicadorPasos, SelectorCategorias, type PasoAsistente } from "./Dialogos";
import s from "./mapa.module.css";

type Errores = Partial<Record<keyof DatosFlujo | "general", string>>;

const ICONO_TIPO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };
const PASO_DE_CAMPO: Partial<Record<keyof DatosFlujo, number>> = {
  origen_id: 0, destino_id: 0, categorias_datos: 1, categorias_titulares: 1, nna_declarado: 1, finalidad: 2,
  frecuencia: 2, medio: 2, cifrado: 2, garantia: 2,
};
const EJEMPLOS_FINALIDAD = [
  "Despachar los pedidos", "Pagar las remuneraciones", "Cobrar y facturar", "Respaldar la información",
  "Enviar comunicaciones comerciales", "Responder consultas con un asistente de IA",
];

export function FormFlujo({
  catalogo,
  vista,
  flujo,
  origenInicial,
  destinoInicial,
  onGuardar,
  onCerrar,
}: {
  catalogo: CatalogoMapa;
  vista: VistaMapa;
  flujo?: FlujoMapa | null;
  origenInicial?: number | null;
  destinoInicial?: number | null;
  onGuardar: (datos: DatosFlujo) => Promise<void>;
  onCerrar: () => void;
}) {
  const id = useId();
  const editando = Boolean(flujo);
  const [paso, setPaso] = useState(0);
  const [origen, setOrigen] = useState<number | "">(flujo?.origen_id ?? origenInicial ?? "");
  const [destino, setDestino] = useState<number | "">(flujo?.destino_id ?? destinoInicial ?? "");
  const [finalidad, setFinalidad] = useState(flujo?.finalidad ?? "");
  const [datos, setDatos] = useState<string[]>(flujo?.categorias_datos ?? []);
  const [titulares, setTitulares] = useState<string[]>(flujo?.categorias_titulares ?? []);
  const [nna, setNna] = useState(flujo?.nna_declarado ?? false);
  const [frecuencia, setFrecuencia] = useState(flujo?.frecuencia ?? "");
  const [medio, setMedio] = useState(flujo?.medio ?? "");
  const [cifrado, setCifrado] = useState<"si" | "no" | "">(flujo?.cifrado === true ? "si" : flujo?.cifrado === false ? "no" : "");
  const [garantia, setGarantia] = useState(flujo?.garantia ?? "");
  const [errores, setErrores] = useState<Errores>({});
  const [ocupado, setOcupado] = useState(false);

  const porId = useMemo(() => new Map(vista.elementos.map((e) => [e.id, e])), [vista.elementos]);
  const eO = origen ? porId.get(origen) : undefined;
  const eD = destino ? porId.get(destino) : undefined;
  const paisO = eO?.derivados.pais_efectivo ?? null;
  const paisD = eD?.derivados.pais_efectivo ?? null;
  const internacional = Boolean(eO && eD) && esInternacional(paisO, paisD, catalogo.pais_local);
  const sinPais = Boolean(eD) && !paisD;
  const sensibles = datos.filter((c) => catalogo.categorias_datos.find((x) => x.codigo === c)?.sensible);
  const titularNna = titulares.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna);
  const garantiaElegida = catalogo.garantias.find((g) => g.codigo === garantia);
  const sinContrato = eD?.tipo === "tercero" && eD.contrato_firmado !== true &&
    Boolean(!eD.rol_tercero || catalogo.roles_tercero.find((r) => r.codigo === eD.rol_tercero)?.requiere_contrato);
  const yaExiste = !editando && Boolean(origen && destino) &&
    vista.flujos.some((f) => f.origen_id === origen && f.destino_id === destino);
  const enComun = eO && eD ? eO.categorias_datos.filter((c) => eD.categorias_datos.includes(c)) : [];

  /* ---------------------------------------------------------------- validación */
  const erroresDe = (i: number): Errores => {
    const e: Errores = {};
    if (i === 0) {
      if (!origen) e.origen_id = "Elige de dónde salen los datos.";
      if (!destino) e.destino_id = "Elige hacia dónde van los datos.";
      else if (origen === destino) e.destino_id = "El origen y el destino deben ser distintos.";
    }
    if (i === 2 && contieneContacto(finalidad)) {
      e.finalidad = "No escribas correos, RUT ni teléfonos de personas: describe para qué se envían los datos.";
    }
    return e;
  };

  const ir = (dest: number) => {
    if (dest > paso) {
      for (let i = paso; i < dest; i++) {
        const e = erroresDe(i);
        if (Object.keys(e).length) {
          setErrores(e);
          setPaso(i);
          return;
        }
      }
    }
    setErrores({});
    setPaso(dest);
  };

  const guardar = async () => {
    const e = { ...erroresDe(0), ...erroresDe(2) };
    if (Object.keys(e).length) {
      setErrores(e);
      setPaso(Math.min(...Object.keys(e).map((k) => PASO_DE_CAMPO[k as keyof DatosFlujo] ?? 0)));
      return;
    }
    setOcupado(true);
    try {
      await onGuardar({
        origen_id: origen as number,
        destino_id: destino as number,
        finalidad: finalidad.trim() || null,
        categorias_datos: datos,
        categorias_titulares: titulares,
        nna_declarado: nna || titularNna,
        frecuencia: frecuencia || null,
        medio: medio || null,
        cifrado: cifrado === "si" ? true : cifrado === "no" ? false : null,
        garantia: internacional ? garantia || null : flujo?.garantia ? garantia || null : null,
      });
    } catch (err) {
      const campo = err instanceof ErrorBff ? (err.info.campo as keyof DatosFlujo | undefined) : undefined;
      setErrores({ [campo ?? "general"]: mensajeError(err, "No pudimos guardar el flujo. Inténtalo de nuevo.") });
      if (campo && PASO_DE_CAMPO[campo] != null) setPaso(PASO_DE_CAMPO[campo]!);
      setOcupado(false);
    }
  };

  /* ---------------------------------------------------------------- riesgos que se detectarán */
  const riesgos: { sev: Severidad; texto: string }[] = [];
  if (internacional && !garantiaElegida?.valida) {
    riesgos.push({ sev: sensibles.length || nna || titularNna ? "Crítica" : "Alta", texto: "Transferencia internacional sin una garantía válida registrada." });
  }
  if (eD?.tipo === "tercero" && eD.subtipo === "proveedor_ia" && (sensibles.length || nna || titularNna)) {
    riesgos.push({ sev: "Crítica", texto: "Un proveedor de IA externo recibiría datos sensibles o de menores." });
  }
  if (sinContrato) riesgos.push({ sev: sensibles.length ? "Crítica" : "Alta", texto: `«${eD?.nombre}» recibe datos sin un contrato de tratamiento confirmado.` });
  if (sensibles.length && cifrado === "no") riesgos.push({ sev: "Alta", texto: "Viajan datos sensibles sin cifrar." });
  if (sensibles.length && cifrado === "") riesgos.push({ sev: "Media", texto: "No se sabe si los datos sensibles viajan cifrados." });
  if (sinPais) riesgos.push({ sev: "Media", texto: `«${eD?.nombre}» no tiene país: no se puede saber si es una transferencia internacional.` });
  if (!datos.length) riesgos.push({ sev: "Baja", texto: "No indica qué datos personales viajan." });

  /* ---------------------------------------------------------------- pasos */
  const pasos: PasoAsistente[] = [
    { titulo: "Recorrido", resumen: eO && eD ? `${eO.nombre} → ${eD.nombre}` : "Desde y hacia", completo: Boolean(eO && eD && origen !== destino), conError: Boolean(errores.origen_id || errores.destino_id) },
    { titulo: "Datos", resumen: datos.length ? `${datos.length} categoría${datos.length === 1 ? "" : "s"}` : "Qué viaja", completo: datos.length > 0 && titulares.length > 0 },
    { titulo: "Cómo y para qué", resumen: finalidad.trim() ? finalidad.trim() : "Finalidad y cifrado", completo: Boolean(finalidad.trim() && cifrado && (!internacional || garantia)), conError: Boolean(errores.finalidad) },
    { titulo: "Revisión", resumen: "Confirma y guarda" },
  ];
  const ultimo = pasos.length - 1;

  const recorrido = (
    <VistaRecorrido catalogo={catalogo} origen={eO} destino={eD} internacional={internacional} sensibles={sensibles.length > 0}
      onIntercambiar={() => { const o = origen; setOrigen(destino); setDestino(o); }} />
  );

  const contenido = () => {
    switch (paso) {
      case 0:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={1} titulo="¿De dónde salen y hacia dónde van los datos?">
              Un flujo es un envío de datos personales entre dos elementos del mapa: de un sistema a una base de datos, a
              un proveedor o fuera del país. Elige primero el origen y luego el destino.
            </EncabezadoPaso>
            {recorrido}
            <div className={s.rejillaSelectores}>
              <SelectorElemento
                etiqueta="Desde (origen)"
                ayuda="Donde están los datos antes de enviarse."
                catalogo={catalogo}
                elementos={vista.elementos}
                valor={origen}
                excluir={destino || null}
                onCambiar={(v) => { setOrigen(v); setErrores({}); }}
                error={errores.origen_id}
                autofoco={!origen}
              />
              <SelectorElemento
                etiqueta="Hacia (destino)"
                ayuda="Quién recibe los datos."
                catalogo={catalogo}
                elementos={vista.elementos}
                valor={destino}
                excluir={origen || null}
                onCambiar={(v) => { setDestino(v); setErrores({}); }}
                error={errores.destino_id}
                autofoco={Boolean(origen) && !destino}
              />
            </div>
            {yaExiste ? (
              <p className={s.alertaInfo} data-tono="nna" role="status">
                <Icon name="info" />
                <span>Ya hay un flujo de «{eO?.nombre}» a «{eD?.nombre}». Puedes agregar otro si los datos o la finalidad son distintos.</span>
              </p>
            ) : null}
            {internacional ? (
              <p className={s.alertaInfo} role="status">
                <Icon name="globo" />
                <span>
                  <strong>Es una transferencia internacional</strong> ({nombrePais(catalogo, paisO ?? catalogo.pais_local)} →{" "}
                  {nombrePais(catalogo, paisD)}). En el paso 3 te pediremos cómo se protegen los datos en el destino.
                </span>
              </p>
            ) : null}
            {sinPais ? (
              <p className={s.alertaInfo} data-tono="nna" role="status">
                <Icon name="info" />
                <span>«{eD?.nombre}» no tiene país de alojamiento: no podemos saber si este flujo sale de Chile. Complétalo en su ficha.</span>
              </p>
            ) : null}
            {sinContrato ? (
              <p className={s.alertaInfo} role="status">
                <Icon name="alerta" />
                <span>«{eD?.nombre}» no tiene un contrato de tratamiento de datos confirmado: el flujo aparecerá como un riesgo hasta que lo confirmes en su ficha.</span>
              </p>
            ) : null}
          </div>
        );
      case 1:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={2} titulo="¿Qué datos viajan y de quiénes son?">
              Elige solo lo que realmente se envía. Te sugerimos lo que ya registraste en «{eO?.nombre ?? "el origen"}».
            </EncabezadoPaso>
            {eO && (eO.categorias_datos.length || eO.categorias_titulares.length) ? (
              <div className={s.atajos}>
                <span className={s.atajosTitulo}><Icon name="chispa" />Atajos</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
                  setDatos([...new Set([...datos, ...eO.categorias_datos])]);
                  setTitulares([...new Set([...titulares, ...eO.categorias_titulares])]);
                  if (eO.incluye_nna) setNna(true);
                }}>
                  <Icon name="copiar" />
                  Usar todo lo de «{eO.nombre}»
                </button>
                {enComun.length ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDatos([...new Set([...datos, ...enComun])])}>
                    <Icon name="filtro" />
                    Solo lo que ambos tienen ({enComun.length})
                  </button>
                ) : null}
              </div>
            ) : null}
            <SelectorCategorias
              catalogo={catalogo}
              modo="datos"
              valor={datos}
              onCambiar={setDatos}
              etiqueta="Datos personales que viajan"
              error={errores.categorias_datos}
              destacadas={eO?.categorias_datos}
            />
            <SelectorCategorias
              catalogo={catalogo}
              modo="titulares"
              valor={titulares}
              onCambiar={(v) => {
                setTitulares(v);
                if (v.some((c) => catalogo.categorias_titulares.find((x) => x.codigo === c)?.nna)) setNna(true);
              }}
              etiqueta="¿De quiénes son?"
              error={errores.categorias_titulares}
              destacadas={eO?.categorias_titulares}
            />
            <label className={s.casillaTarjeta}>
              <input type="checkbox" checked={nna || titularNna} disabled={titularNna} onChange={(e) => setNna(e.target.checked)} />
              <span><strong>Incluye datos de niños, niñas o adolescentes</strong></span>
            </label>
          </div>
        );
      case 2:
        return (
          <div className={s.pasoConConsejo}>
            <div className={s.pasoCuerpo}>
              <EncabezadoPaso numero={3} titulo="¿Para qué y cómo se envían?">
                La finalidad explica por qué viajan los datos; el cifrado y la garantía, cómo se protegen.
              </EncabezadoPaso>
              <div className={s.campo}>
                <label htmlFor={`${id}-finalidad`}>¿Para qué se envían los datos? <span className={s.opcional}>recomendado</span></label>
                <textarea
                  id={`${id}-finalidad`}
                  className={s.control}
                  value={finalidad}
                  maxLength={300}
                  onChange={(e) => setFinalidad(e.target.value)}
                  placeholder="Ej.: despachar los pedidos a domicilio"
                  aria-invalid={Boolean(errores.finalidad) || undefined}
                  data-autofoco
                />
                <div className={s.ejemplos} aria-label="Ejemplos de finalidad">
                  {EJEMPLOS_FINALIDAD.map((x) => (
                    <button key={x} type="button" className={s.ejemplo} onClick={() => setFinalidad(x)}>{x}</button>
                  ))}
                </div>
                {errores.finalidad ? <p className={s.error} role="alert">{errores.finalidad}</p> : <p className={s.ayuda}>{finalidad.length}/300 · Toca un ejemplo para usarlo y ajústalo.</p>}
              </div>
              <div className={s.rejilla}>
                <div className={s.campo}>
                  <label htmlFor={`${id}-frecuencia`}>¿Cada cuánto?</label>
                  <select id={`${id}-frecuencia`} className={`select ${s.control}`} value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)}>
                    <option value="">Sin informar</option>
                    {catalogo.frecuencias.map((o) => (
                      <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
                    ))}
                  </select>
                </div>
                <div className={s.campo}>
                  <label htmlFor={`${id}-medio`}>¿Por qué medio?</label>
                  <select id={`${id}-medio`} className={`select ${s.control}`} value={medio} onChange={(e) => setMedio(e.target.value)}>
                    <option value="">Sin informar</option>
                    {catalogo.medios.map((o) => (
                      <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
                    ))}
                  </select>
                </div>
              </div>
              <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
                <legend className={s.etiquetaCampo}>¿Los datos viajan cifrados?</legend>
                <div className={s.segmentado}>
                  {([["si", "Sí", "candado"], ["no", "No", "cerrar"], ["", "No lo sé", "info"]] as const).map(([v, t, ic]) => (
                    <label key={v || "nose"} className={s.segmento}>
                      <input type="radio" name={`${id}-cifrado`} checked={cifrado === v} onChange={() => setCifrado(v)} />
                      <Icon name={ic} />
                      <span>{t}</span>
                    </label>
                  ))}
                </div>
                <p className={s.ayuda} style={sensibles.length && cifrado !== "si" ? { color: "var(--critico)" } : undefined}>
                  {sensibles.length && cifrado !== "si"
                    ? "Viajan datos sensibles: deberían ir cifrados (por ejemplo, con HTTPS, SFTP o VPN)."
                    : "Por ejemplo: un sitio con HTTPS, una conexión SFTP o VPN, o archivos protegidos con contraseña."}
                </p>
              </fieldset>
              {internacional ? (
                <fieldset className={s.campo} style={{ border: 0, padding: 0, margin: 0 }}>
                  <legend className={s.etiquetaCampo}>
                    <Icon name="globo" width={16} height={16} style={{ verticalAlign: "-3px", marginRight: 6, color: "var(--medio)" }} />
                    ¿Con qué garantía se protege la transferencia a {nombrePais(catalogo, paisD)}?
                  </legend>
                  <div className={s.opcionesRol}>
                    {catalogo.garantias.map((g) => (
                      <label key={g.codigo} className={s.opcionRol} data-valida={g.valida || undefined}>
                        <input type="radio" name={`${id}-garantia`} checked={garantia === g.codigo} onChange={() => setGarantia(g.codigo)} />
                        <span className={s.opcionRolTitulo}>{g.nombre}</span>
                        {g.descripcion ? <span className={s.opcionRolTexto}>{g.descripcion}</span> : null}
                      </label>
                    ))}
                    <label className={s.opcionRol}>
                      <input type="radio" name={`${id}-garantia`} checked={!garantia} onChange={() => setGarantia("")} />
                      <span className={s.opcionRolTitulo}>Aún no lo sé</span>
                      <span className={s.opcionRolTexto}>La transferencia aparecerá como un riesgo hasta que la registres.</span>
                    </label>
                  </div>
                </fieldset>
              ) : null}
            </div>
            <Consejo>
              Cada flujo alimenta el registro de actividades: su finalidad, sus destinatarios y sus transferencias. Si no
              sabes un dato, déjalo «sin informar» y complétalo después: el mapa te avisará qué falta.
            </Consejo>
          </div>
        );
      default:
        return (
          <div className={s.pasoCuerpo}>
            <EncabezadoPaso numero={4} titulo="Revisa antes de guardar">
              Así quedará el flujo en tu mapa. Puedes volver a cualquier paso con «Cambiar».
            </EncabezadoPaso>
            {recorrido}
            <div className={s.resumenRevision}>
              <FilaRevision titulo="Datos" onCambiar={() => setPaso(1)}>
                {datos.length ? datos.map((c) => nombreDato(catalogo, c)).join(", ") : <span className={s.sinDato}>Ninguno elegido</span>}
                {sensibles.length ? <small className={s.marcaSensible}>{sensibles.length} sensible{sensibles.length === 1 ? "" : "s"}</small> : null}
              </FilaRevision>
              <FilaRevision titulo="Titulares" onCambiar={() => setPaso(1)}>
                {titulares.length ? titulares.map((c) => nombreTitular(catalogo, c)).join(", ") : <span className={s.sinDato}>Ninguno elegido</span>}
                {nna || titularNna ? <small className={s.marcaNna}>Incluye niños, niñas o adolescentes</small> : null}
              </FilaRevision>
              <FilaRevision titulo="Finalidad" onCambiar={() => setPaso(2)}>
                {finalidad.trim() || <span className={s.sinDato}>Sin informar</span>}
                <small>
                  {frecuencia ? nombreOpcion(catalogo.frecuencias, frecuencia) : "Frecuencia sin informar"} ·{" "}
                  {medio ? nombreOpcion(catalogo.medios, medio) : "medio sin informar"} ·{" "}
                  {cifrado === "si" ? "cifrado" : cifrado === "no" ? "sin cifrar" : "cifrado sin confirmar"}
                </small>
              </FilaRevision>
              {internacional ? (
                <FilaRevision titulo="Garantía" onCambiar={() => setPaso(2)}>
                  {garantiaElegida ? garantiaElegida.nombre : <span className={s.sinDato}>Sin garantía registrada</span>}
                </FilaRevision>
              ) : null}
            </div>
            {riesgos.length ? (
              <div className={s.recomendaciones}>
                <h4>Al guardarlo, el mapa detectará</h4>
                <ul>
                  {riesgos.map((r) => (
                    <li key={r.texto} data-tono={r.sev === "Crítica" || r.sev === "Alta" ? "riesgo" : "mejora"}>
                      <span className={s.sev} data-sev={r.sev}>{r.sev}</span>
                      <span>{r.texto}</span>
                    </li>
                  ))}
                </ul>
                <p className={s.ayuda}>Puedes guardarlo igual: los riesgos quedan en la pestaña Riesgos con lo que conviene hacer.</p>
              </div>
            ) : (
              <p className={s.alertaInfo} data-tono="ok" role="status">
                <Icon name="check" />
                <span>Sin riesgos a la vista con la información registrada.</span>
              </p>
            )}
          </div>
        );
    }
  };

  const botonGuardar = (
    <button type="button" className="btn btn-primary" onClick={guardar} disabled={ocupado}>
      <Icon name="check" />
      {ocupado ? "Guardando…" : editando ? "Guardar cambios" : "Agregar flujo"}
    </button>
  );

  return (
    <Dialogo
      tamano="lg"
      icono={internacional ? "globo" : "flujo"}
      tonoIcono={internacional ? "aviso" : "acento"}
      antetitulo={editando ? "Editar flujo" : "Nuevo flujo de datos"}
      titulo={editando && eO && eD ? `${eO.nombre} → ${eD.nombre}` : "Agregar un flujo de datos"}
      descripcion={editando ? "Los cambios quedan registrados como una nueva versión del mapa." : "Indica qué datos personales viajan de un elemento a otro, para qué y cómo se protegen."}
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
      <div className={s.contenidoPaso} key={paso}>
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

/* ============================================================ piezas */

function SelectorElemento({
  etiqueta,
  ayuda,
  catalogo,
  elementos,
  valor,
  excluir,
  onCambiar,
  error,
  autofoco,
}: {
  etiqueta: string;
  ayuda: string;
  catalogo: CatalogoMapa;
  elementos: ElementoMapa[];
  valor: number | "";
  excluir: number | null;
  onCambiar: (v: number | "") => void;
  error?: string;
  autofoco?: boolean;
}) {
  const id = useId();
  const lista = useRef<HTMLDivElement>(null);
  const [busqueda, setBusqueda] = useState("");
  const q = busqueda.trim().toLowerCase();
  // La opción elegida queda a la vista dentro de la lista (sin mover la ventana)
  useEffect(() => {
    // Después de que la ventana se abre y se dibuja (antes no hay medidas)
    const t = requestAnimationFrame(() => {
      const caja = lista.current;
      const marcada = caja?.querySelector<HTMLElement>("input:checked")?.closest("label");
      if (caja && marcada) {
        const arriba = marcada.offsetTop;   // la lista es position: relative
        if (arriba < caja.scrollTop || arriba + marcada.offsetHeight > caja.scrollTop + caja.clientHeight) {
          caja.scrollTop = arriba - caja.clientHeight / 2 + marcada.offsetHeight / 2;
        }
      }
    });
    return () => cancelAnimationFrame(t);
  }, [valor]);
  const grupos = (["sistema", "base_datos", "tercero"] as TipoElemento[]).map((t) => ({
    tipo: t,
    items: elementos
      .filter((e) => e.tipo === t && (!q || e.nombre.toLowerCase().includes(q)))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),
  })).filter((g) => g.items.length);
  const elegido = elementos.find((e) => e.id === valor);

  return (
    <fieldset className={s.selectorElemento} data-error={Boolean(error) || undefined}>
      <legend className={s.etiquetaCampo}>{etiqueta}<span className={s.obligatorio} aria-hidden="true">*</span></legend>
      <p className={s.ayuda}>{ayuda}</p>
      <div className="input-wrap">
        <Icon name="buscar" />
        <input
          type="search"
          className="input"
          placeholder="Buscar por nombre"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          aria-label={`Buscar en ${etiqueta.toLowerCase()}`}
          data-autofoco={autofoco || undefined}
        />
      </div>
      <div className={s.listaElementos} role="radiogroup" aria-label={etiqueta} ref={lista}>
        {grupos.length === 0 ? <p className={s.ayuda} style={{ padding: 8 }}>Sin coincidencias.</p> : null}
        {grupos.map((g) => (
          <div key={g.tipo} className={s.grupoElementos}>
            <span className={s.grupoElementosTitulo}>{ETIQUETA_TIPO_PLURAL[g.tipo]}</span>
            {g.items.map((e) => {
              const pais = e.derivados.pais_efectivo;
              return (
                <label key={e.id} className={s.opcionElemento} data-tipo={e.tipo} data-deshabilitado={e.id === excluir || undefined}>
                  <input type="radio" name={`${id}-elemento`} checked={valor === e.id} disabled={e.id === excluir} onChange={() => onCambiar(e.id)} />
                  <Icon name={ICONO_TIPO[e.tipo]} />
                  <span className={s.opcionElementoNombre}>{e.nombre}</span>
                  <span className={s.opcionElementoPais} data-fuera={e.derivados.fuera_de_chile || undefined}>
                    {pais ? nombrePais(catalogo, pais) : "¿país?"}
                  </span>
                </label>
              );
            })}
          </div>
        ))}
      </div>
      {error ? <p className={s.error} role="alert">{error}</p> : elegido ? <p className={s.ayuda}>Elegiste: <strong>{elegido.nombre}</strong></p> : null}
    </fieldset>
  );
}

function VistaRecorrido({
  catalogo,
  origen,
  destino,
  internacional,
  sensibles,
  onIntercambiar,
}: {
  catalogo: CatalogoMapa;
  origen?: ElementoMapa;
  destino?: ElementoMapa;
  internacional: boolean;
  sensibles: boolean;
  onIntercambiar?: () => void;
}) {
  const nodo = (e: ElementoMapa | undefined, rol: string) => (
    <div className={s.recorridoNodo} data-tipo={e?.tipo} data-vacio={!e || undefined}>
      <span className={s.recorridoRol}>{rol}</span>
      {e ? (
        <>
          <span className={s.recorridoNombre}><Icon name={ICONO_TIPO[e.tipo]} />{e.nombre}</span>
          <span className={s.recorridoPais} data-fuera={e.derivados.fuera_de_chile || undefined}>
            <Icon name="globo" />{e.derivados.pais_efectivo ? nombrePais(catalogo, e.derivados.pais_efectivo) : "País sin informar"}
          </span>
        </>
      ) : (
        <span className={s.sinDato}>Elige un elemento</span>
      )}
    </div>
  );
  return (
    <div className={s.recorrido} aria-label="Vista previa del recorrido">
      {nodo(origen, "Desde")}
      {nodo(destino, "Hacia")}
      <span className={s.recorridoFlecha} data-internacional={internacional || undefined} data-sensible={sensibles || undefined} aria-hidden="true">
        <Icon name="flecha" />
      </span>
      {onIntercambiar && origen && destino ? (
        <button type="button" className={s.recorridoIntercambiar} onClick={onIntercambiar} title="Intercambiar origen y destino" aria-label="Intercambiar origen y destino">
          <Icon name="ordenar" />
        </button>
      ) : null}
    </div>
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
