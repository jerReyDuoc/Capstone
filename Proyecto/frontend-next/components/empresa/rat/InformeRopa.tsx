"use client";

/**
 * Informe RoPA del registro de actividades (ventana de una sola pantalla, con scroll):
 *
 *   Incluir             como responsable / como encargado (según el rol marcado en cada actividad vigente).
 *   Datos de la empresa contacto y delegado de protección de datos (lo que el registro no tiene). Se guardan
 *                       para la próxima vez, al generar o al cerrar la ventana.
 *   Organizaciones      contacto de cada organización por cuenta de la cual la empresa actúa como encargada.
 *   Vista previa        lo que dirá el informe, por parte y por actividad, más las transferencias.
 *   Informes emitidos   historial con sus descargas.
 *
 * El botón «Generar PDF y Excel» queda fijo en el pie: se bloquea con el motivo si falta algo y, al generar,
 * el resultado (código y descargas) aparece en el mismo pie. Las explicaciones van en el ícono de información.
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { tamanoLegible } from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import { fechaHoraChile } from "@/lib/fechas";
import {
  cambiosDatos, cargarRopa, descargarRopa, emitirRopa, erroresFormato, faltantes, guardarDatosRopa, NOMBRE_PARTE, PARTES,
  textoFaltantes, textoPartes,
  type ActividadRopa, type DatosRopa, type EmisionRopa, type FormatoRopa, type GrupoEncargado,
  type ListaRopa, type MandanteDatos, type ParteRopa,
} from "@/lib/informeRopa";
import { mensajeError, plural } from "@/lib/mapaDatos";
import s from "./rat.module.css";

type Pestana = ParteRopa | "transferencias";
type Ocupado = null | "generar" | `${number}-${FormatoRopa}`;

export function InformeRopa({ onCerrar, onSesionVencida }: { onCerrar: () => void; onSesionVencida: (e: unknown) => boolean }) {
  const id = useId();
  const [lista, setLista] = useState<ListaRopa | null>(null);
  const [error, setError] = useState("");
  const [guardados, setGuardados] = useState<DatosRopa | null>(null);
  const [datos, setDatos] = useState<DatosRopa | null>(null);
  const [partes, setPartes] = useState<ParteRopa[]>([]);
  const [intento, setIntento] = useState(false);
  const [ocupado, setOcupado] = useState<Ocupado>(null);
  const [falloPie, setFalloPie] = useState("");
  const [emitida, setEmitida] = useState<{ informe: EmisionRopa; mensaje: string } | null>(null);
  const [info, setInfo] = useState(false);
  const [pestana, setPestana] = useState<Pestana>("responsable");
  const [elegida, setElegida] = useState<Record<string, number>>({});
  const infoRef = useRef<HTMLSpanElement>(null);

  const recargar = useCallback(async (primeraVez = false) => {
    try {
      const l = await cargarRopa();
      setLista(l);
      setGuardados(l.datos);
      if (primeraVez) {
        setDatos(l.datos);
        setPartes(l.previa.disponibles);
        setPestana(l.previa.disponibles[0] ?? "transferencias");
      }
      setError("");
    } catch (e) {
      if (!onSesionVencida(e)) setError(mensajeError(e, "No pudimos preparar el informe RoPA. Inténtalo de nuevo."));
    }
  }, [onSesionVencida]);

  useEffect(() => {
    void recargar(true);
  }, [recargar]);

  // La ayuda se cierra al hacer clic fuera o con Escape (Escape cierra solo la ayuda, no la ventana)
  useEffect(() => {
    if (!info) return;
    const clic = (e: MouseEvent) => {
      if (!infoRef.current?.contains(e.target as Node)) setInfo(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      setInfo(false);
    };
    document.addEventListener("mousedown", clic);
    document.addEventListener("keydown", tecla, true);
    return () => {
      document.removeEventListener("mousedown", clic);
      document.removeEventListener("keydown", tecla, true);
    };
  }, [info]);

  const previa = lista?.previa;
  const falta = useMemo(() => (datos ? faltantes(datos, partes) : []), [datos, partes]);
  const formato = useMemo(() => (datos ? erroresFormato(datos, partes) : []), [datos, partes]);
  const motivo = !partes.length ? "Elige qué incluir." : datos ? textoFaltantes([...falta, ...formato], datos) : "";
  const pestanas: Pestana[] = [...PARTES.filter((p) => partes.includes(p)), "transferencias"];
  const pestanaActiva: Pestana = pestanas.includes(pestana) ? pestana : pestanas[0];

  const cambiar = (cambio: Partial<DatosRopa>) => {
    setDatos((d) => (d ? { ...d, ...cambio } : d));
    setEmitida(null);
    setFalloPie("");
  };
  const cambiarMandante = (clave: string, cambio: Partial<MandanteDatos>) =>
    cambiar({ mandantes: (datos?.mandantes ?? []).map((m) => (m.clave === clave ? { ...m, ...cambio } : m)) });

  const invalido = (grupo: string, campo: string) =>
    formato.some((f) => f.grupo === grupo && f.campo === campo) || (intento && falta.some((f) => f.grupo === grupo && f.campo === campo));
  const mensajeCampo = (grupo: string, campo: string): string | null =>
    formato.find((f) => f.grupo === grupo && f.campo === campo)?.mensaje ??
    (intento ? falta.find((f) => f.grupo === grupo && f.campo === campo)?.mensaje ?? null : null);

  const guardarSiCambio = async () => {
    if (!datos || !guardados) return;
    const cambios = cambiosDatos(guardados, datos);
    if (!cambios) return;
    const r = await guardarDatosRopa(cambios);
    setGuardados(r.datos);
  };

  const generar = async () => {
    setIntento(true);
    if (motivo || !datos) return;
    setOcupado("generar");
    setFalloPie("");
    setEmitida(null);
    try {
      await guardarSiCambio();
      const r = await emitirRopa(partes);
      setEmitida({ informe: r.informe, mensaje: r.mensaje });
      await recargar();
    } catch (e) {
      if (!onSesionVencida(e)) setFalloPie(mensajeError(e, "No pudimos generar el informe. Inténtalo de nuevo."));
    } finally {
      setOcupado(null);
    }
  };

  const descargar = async (em: EmisionRopa, f: FormatoRopa) => {
    setOcupado(`${em.id}-${f}`);
    try {
      const { blob, nombre } = await descargarRopa(em.id, f);
      descargarBlob(blob, nombre);
    } catch (e) {
      if (!onSesionVencida(e)) setFalloPie(mensajeError(e, "No pudimos descargar el informe."));
    } finally {
      setOcupado(null);
    }
  };

  /** Al cerrar, lo escrito queda guardado para la próxima vez (si está bien escrito). */
  const cerrar = async () => {
    if (ocupado) return;
    if (datos && guardados && !formato.length && cambiosDatos(guardados, datos)) {
      try {
        await guardarSiCambio();
      } catch {
        /* no se bloquea el cierre */
      }
    }
    onCerrar();
  };

  /* ---------------------------------------------------------------- piezas */
  const campoTexto = (o: {
    grupo: string; campo: string; etiqueta: string; valor: string | null; onCambio: (v: string) => void;
    tipo?: "text" | "email" | "tel"; opcional?: boolean; ancho?: boolean; placeholder?: string; max: number; autoComplete?: string;
  }) => {
    const idCampo = `${id}-${o.grupo}-${o.campo}`.replace(/[^\w-]/g, "_");
    const msg = mensajeCampo(o.grupo, o.campo);
    return (
      <div className={`${ms.campo} ${o.ancho ? s.ropaAncho : ""}`}>
        <label htmlFor={idCampo}>
          {o.etiqueta}
          {o.opcional ? <span className={s.ropaOpcional}>opcional</span> : null}
        </label>
        <input
          id={idCampo}
          className={ms.control}
          type={o.tipo ?? "text"}
          value={o.valor ?? ""}
          maxLength={o.max}
          placeholder={o.placeholder}
          autoComplete={o.autoComplete ?? "off"}
          aria-invalid={invalido(o.grupo, o.campo) || undefined}
          aria-describedby={msg ? `${idCampo}-msg` : undefined}
          onChange={(e) => o.onCambio(e.target.value)}
        />
        {msg ? <p id={`${idCampo}-msg`} className={ms.error}>{msg}</p> : null}
      </div>
    );
  };

  const estadoGrupo = (grupo: string) => {
    const incompleto = [...falta, ...formato].some((f) => f.grupo === grupo);
    return <span className={`badge ${incompleto ? "tone-medio" : "tone-ok"}`}>{incompleto ? "Falta completar" : "Completo"}</span>;
  };

  /* ---------------------------------------------------------------- vista previa */
  const contactoEmpresa = (): string[] => {
    if (!lista || !datos) return [];
    const l = [lista.empresa.razon_social + (lista.empresa.rut ? ` (RUT ${lista.empresa.rut})` : "")];
    if (datos.direccion?.trim()) l.push(datos.direccion.trim());
    const c = [datos.correo?.trim(), datos.telefono?.trim()].filter(Boolean).join(" · ");
    if (c) l.push(c);
    l.push(`Delegado de protección de datos: ${datos.tiene_dpo === true
      ? [datos.dpo_cargo?.trim(), datos.dpo_correo?.trim()].filter(Boolean).join(" · ") || "designado"
      : datos.tiene_dpo === false ? "no designado" : "sin indicar"}`);
    return l;
  };

  const contactoMandante = (g: GrupoEncargado): string[] => {
    const m = datos?.mandantes.find((x) => x.clave === g.clave);
    return [g.nombre, m?.direccion?.trim(), m?.correo?.trim(),
      m?.dpo?.trim() ? `Delegado de protección de datos: ${m.dpo.trim()}` : null].filter((x): x is string => Boolean(x));
  };

  const transferencias = (a: ActividadRopa) =>
    a.transferencias.length
      ? a.transferencias.map((t) => `${t.pais} · ${t.destino} · ${t.garantia}`)
      : ["No hay transferencias internacionales."];
  const medidas = (a: ActividadRopa) => Object.entries(a.medidas).map(([g, v]) => `${g}: ${v.join(", ")}`);

  const filas = (a: ActividadRopa, g: GrupoEncargado | null): [string, string[]][] =>
    g
      ? [
          ["Encargado", contactoEmpresa()],
          ["Por cuenta de", contactoMandante(g)],
          ["Tratamientos", [a.descripcion, ...a.finalidades].filter((x): x is string => Boolean(x))],
          ["Transferencias internacionales", transferencias(a)],
          ["Medidas de seguridad", medidas(a)],
        ]
      : [
          ["Responsable", contactoEmpresa()],
          ["Finalidades", a.finalidades],
          ["Titulares", a.titulares],
          ["Categorías de datos", a.datos],
          ["Destinatarios", a.destinatarios],
          ["Transferencias internacionales", transferencias(a)],
          ["Plazos de supresión", a.plazos],
          ["Medidas de seguridad", medidas(a)],
        ];

  const tablaActividad = (a: ActividadRopa, g: GrupoEncargado | null) => (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{`Vista previa de ${a.nombre}`}</caption>
        <tbody>
          {filas(a, g).map(([campo, lineas]) => (
            <tr key={campo}>
              <th scope="row" className={s.ropaCampo}>{campo}</th>
              <td>
                {lineas.length > 1 ? (
                  <ul className={s.ropaLista}>{lineas.map((x) => <li key={x}><TextoMarcado texto={x} /></li>)}</ul>
                ) : <TextoMarcado texto={lineas[0] ?? "Sin indicar"} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const panelParte = (parte: ParteRopa) => {
    if (!previa) return null;
    const items: { a: ActividadRopa; g: GrupoEncargado | null }[] = parte === "responsable"
      ? previa.responsable.map((a) => ({ a, g: null }))
      : previa.encargado.flatMap((g) => g.actividades.map((a) => ({ a, g })));
    const i = Math.min(elegida[parte] ?? 0, Math.max(0, items.length - 1));
    const actual = items[i];
    return (
      <div role="tabpanel" id={`${id}-panel-${parte}`} aria-labelledby={`${id}-tab-${parte}`} className={s.ropaPanel}>
        {items.length > 1 ? (
          <div className="chip-group" role="group" aria-label="Actividad">
            {items.map(({ a }, k) => (
              <button key={a.id} type="button" className="chip" aria-pressed={k === i} onClick={() => setElegida({ ...elegida, [parte]: k })}>
                {a.nombre}
              </button>
            ))}
          </div>
        ) : null}
        {actual ? tablaActividad(actual.a, actual.g) : null}
      </div>
    );
  };

  /* ---------------------------------------------------------------- contenido */
  const cuerpo = () => {
    if (error) {
      return <div className="callout" role="alert"><Icon name="alerta" /><span>{error}</span></div>;
    }
    if (!lista || !previa || !datos) {
      return (
        <div style={{ display: "grid", gap: 12 }} role="status" aria-label="Preparando el informe RoPA">
          <div className="skeleton" style={{ height: 72 }} />
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      );
    }
    if (!previa.disponibles.length) {
      return (
        <div className={s.informeVacio}>
          <Icon name="tabla" />
          <div>
            <h3>Aún no hay actividades vigentes</h3>
            <p>Deja vigente al menos una actividad del registro para generar el informe.</p>
          </div>
        </div>
      );
    }
    const r = previa.resumen;
    const conteo: Record<ParteRopa, string> = {
      responsable: plural(r.responsable, "actividad", "actividades"),
      encargado: `${plural(r.encargado, "actividad", "actividades")} · ${plural(r.organizaciones, "organización", "organizaciones")}`,
    };
    return (
      <>
        {/* -------------------------------------------- incluir */}
        <section className={s.ropaSeccion} aria-labelledby={`${id}-incluir`}>
          <h3 id={`${id}-incluir`} className={s.ropaTitulo}>Incluir</h3>
          <div className={s.ropaPartes}>
            {PARTES.map((p) => {
              const hay = previa.disponibles.includes(p);
              return (
                <label key={p} className={s.ropaParte} data-sin={!hay || undefined}>
                  <input
                    type="checkbox"
                    checked={partes.includes(p)}
                    disabled={!hay}
                    onChange={(e) => {
                      setPartes(e.target.checked ? PARTES.filter((x) => x === p || partes.includes(x)) : partes.filter((x) => x !== p));
                      setEmitida(null);
                    }}
                  />
                  <span className={s.ropaParteNombre}>{NOMBRE_PARTE[p]}</span>
                  <span className={`badge ${hay ? (p === "encargado" ? "tone-info" : "tone-ok") : "tone-info"}`}>
                    {hay ? conteo[p] : "Sin actividades"}
                  </span>
                </label>
              );
            })}
          </div>
        </section>

        {/* -------------------------------------------- empresa */}
        <section className={s.ropaSeccion} aria-labelledby={`${id}-empresa`}>
          <div className={s.ropaCabeza}>
            <h3 id={`${id}-empresa`} className={s.ropaTitulo}>Datos de la empresa</h3>
            {estadoGrupo("empresa")}
          </div>
          <div className={s.ropaGrilla}>
            <div className={ms.campo}>
              <label htmlFor={`${id}-razon`}>Razón social</label>
              <input id={`${id}-razon`} className={`${ms.control} ${s.ropaFijo}`} value={lista.empresa.razon_social} readOnly />
            </div>
            <div className={ms.campo}>
              <label htmlFor={`${id}-rut`}>RUT</label>
              <input id={`${id}-rut`} className={`${ms.control} ${s.ropaFijo}`} value={lista.empresa.rut ?? "—"} readOnly />
            </div>
            {campoTexto({ grupo: "empresa", campo: "direccion", etiqueta: "Dirección", valor: datos.direccion, max: 200, ancho: true,
              autoComplete: "street-address", onCambio: (v) => cambiar({ direccion: v }) })}
            {campoTexto({ grupo: "empresa", campo: "correo", etiqueta: "Correo de contacto", valor: datos.correo, max: 100, tipo: "email",
              placeholder: "privacidad@tuempresa.cl", onCambio: (v) => cambiar({ correo: v }) })}
            {campoTexto({ grupo: "empresa", campo: "telefono", etiqueta: "Teléfono", valor: datos.telefono, max: 25, tipo: "tel",
              opcional: true, placeholder: "+56 2 2345 6789", onCambio: (v) => cambiar({ telefono: v }) })}
          </div>
          <fieldset className={s.ropaDpo} aria-invalid={invalido("empresa", "tiene_dpo") || undefined}>
            <legend className={ms.etiquetaCampo}>Delegado de protección de datos</legend>
            <div className={`${ms.segmentado} ${ms.dos} ${s.ropaSiNo}`}>
              {([[true, "Sí"], [false, "No"]] as const).map(([v, t]) => (
                <label key={t} className={ms.segmento}>
                  <input type="radio" name={`${id}-dpo`} checked={datos.tiene_dpo === v} onChange={() => cambiar({ tiene_dpo: v })} />
                  <span>{t}</span>
                </label>
              ))}
            </div>
            {mensajeCampo("empresa", "tiene_dpo") ? <p className={ms.error}>{mensajeCampo("empresa", "tiene_dpo")}</p> : null}
          </fieldset>
          {datos.tiene_dpo ? (
            <div className={s.ropaGrilla}>
              {campoTexto({ grupo: "empresa", campo: "dpo_cargo", etiqueta: "Cargo o área", valor: datos.dpo_cargo, max: 120,
                placeholder: "Oficial de Protección de Datos", onCambio: (v) => cambiar({ dpo_cargo: v }) })}
              {campoTexto({ grupo: "empresa", campo: "dpo_correo", etiqueta: "Correo", valor: datos.dpo_correo, max: 100, tipo: "email",
                placeholder: "dpo@tuempresa.cl", onCambio: (v) => cambiar({ dpo_correo: v }) })}
            </div>
          ) : null}
        </section>

        {/* -------------------------------------------- organizaciones */}
        {partes.includes("encargado") && datos.mandantes.length ? (
          <section className={s.ropaSeccion} aria-labelledby={`${id}-mandantes`}>
            <h3 id={`${id}-mandantes`} className={s.ropaTitulo}>Organizaciones para las que actúas como encargado</h3>
            {datos.mandantes.map((m) => (
              <div key={m.clave} className={s.ropaMandante}>
                <h4>{m.nombre} {estadoGrupo(m.clave)}</h4>
                <div className={s.ropaGrilla}>
                  {campoTexto({ grupo: m.clave, campo: "direccion", etiqueta: "Dirección", valor: m.direccion, max: 200, ancho: true,
                    placeholder: "Dirección de la organización", onCambio: (v) => cambiarMandante(m.clave, { direccion: v }) })}
                  {campoTexto({ grupo: m.clave, campo: "correo", etiqueta: "Correo de contacto", valor: m.correo, max: 100, tipo: "email",
                    placeholder: "contacto@organizacion.cl", onCambio: (v) => cambiarMandante(m.clave, { correo: v }) })}
                  {campoTexto({ grupo: m.clave, campo: "dpo", etiqueta: "Delegado de protección de datos", valor: m.dpo, max: 150,
                    opcional: true, onCambio: (v) => cambiarMandante(m.clave, { dpo: v }) })}
                </div>
              </div>
            ))}
          </section>
        ) : null}

        {/* -------------------------------------------- vista previa */}
        <section className={s.ropaSeccion} aria-labelledby={`${id}-previa`}>
          <h3 id={`${id}-previa`} className={s.ropaTitulo}>Vista previa</h3>
          <div className={s.ropaPestanas} role="tablist" aria-label="Partes del informe">
            {pestanas.map((p) => (
              <button
                key={p}
                type="button"
                role="tab"
                id={`${id}-tab-${p}`}
                aria-selected={pestanaActiva === p}
                aria-controls={`${id}-panel-${p}`}
                className={s.ropaPestana}
                onClick={() => setPestana(p)}
              >
                {p === "transferencias" ? "Transferencias" : NOMBRE_PARTE[p]}
              </button>
            ))}
          </div>
          {pestanaActiva === "transferencias" ? (
            <div role="tabpanel" id={`${id}-panel-transferencias`} aria-labelledby={`${id}-tab-transferencias`}>
              {previa.transferencias.filter((t) => partes.includes(t.rol)).length ? (
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Transferencias internacionales</caption>
                    <thead><tr><th scope="col">Actividad</th><th scope="col">Destino</th><th scope="col">País</th><th scope="col">Garantía</th></tr></thead>
                    <tbody>
                      {previa.transferencias.filter((t) => partes.includes(t.rol)).map((t, k) => (
                        <tr key={`${t.actividad}-${t.destino}-${k}`}>
                          <td>{t.actividad}</td>
                          <td>{t.destino}</td>
                          <td>{t.pais}</td>
                          <td>{t.con_garantia ? t.garantia : <span className="badge tone-alto">Sin garantía</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className={ms.ayuda}>Los datos de las actividades incluidas no salen de Chile.</p>}
            </div>
          ) : panelParte(pestanaActiva)}
        </section>

        {/* -------------------------------------------- emitidos */}
        <section className={s.ropaSeccion} aria-labelledby={`${id}-emitidos`}>
          <h3 id={`${id}-emitidos`} className={s.ropaTitulo}>Informes emitidos</h3>
          {lista.emisiones.length ? (
            <div className="table-wrap">
              <table className="table">
                <caption className="sr-only">Informes RoPA emitidos</caption>
                <thead>
                  <tr><th scope="col">Emitido</th><th scope="col">Código</th><th scope="col">Versión</th><th scope="col">Incluye</th><th scope="col">Descargar</th></tr>
                </thead>
                <tbody>
                  {lista.emisiones.map((em) => (
                    <tr key={em.id}>
                      <td>{fechaHoraChile(em.fecha)}</td>
                      <td className="code">{em.codigo}</td>
                      <td>N.º {em.version}</td>
                      <td>{textoPartes(em.partes)}</td>
                      <td><Descargas em={em} ocupado={ocupado} onDescargar={descargar} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className={ms.ayuda}>Aún no hay informes RoPA.</p>}
        </section>
      </>
    );
  };

  const listo = Boolean(lista && previa?.disponibles.length && datos && !error);

  return (
    <Dialogo
      tamano="lg"
      icono="tabla"
      titulo={
        <span className={s.ropaTituloDialogo}>
          Informe RoPA
          {lista ? <span className={s.versionInforme}>Versión N.º {lista.version_siguiente}</span> : null}
          <span className={s.ropaInfo} ref={infoRef}>
            <button type="button" className={s.ropaInfoBoton} aria-label="Más información" aria-expanded={info}
              aria-controls={`${id}-info`} onClick={() => setInfo(!info)}>
              <Icon name="info" />
            </button>
            {info ? (
              <span id={`${id}-info`} role="note" className={s.ropaInfoTexto}>
                <span>Se arma con las actividades vigentes de tu registro, sin volver a ingresarlas.</span>
                <span>Los datos que el registro no tiene se guardan y vienen listos la próxima vez.</span>
                <span>El PDF y el Excel quedan en Mis documentos.</span>
              </span>
            ) : null}
          </span>
        </span>
      }
      onCerrar={() => void cerrar()}
      pie={
        <>
          <div className={s.ropaPieEstado} role="status">
            {emitida ? (
              <>
                <span className={s.ropaOk}><Icon name="check" /></span>
                <span className={s.ropaPieTexto}>
                  <strong>Informe N.º {emitida.informe.version} guardado en Mis documentos</strong>
                  <span className={s.codigo}>{emitida.informe.codigo}</span>
                </span>
                <Descargas em={emitida.informe} ocupado={ocupado} onDescargar={descargar} />
              </>
            ) : falloPie ? (
              <span className={s.ropaAviso} data-tono="error"><Icon name="alerta" />{falloPie}</span>
            ) : listo && motivo ? (
              <span className={s.ropaAviso}><Icon name="alerta" />{motivo}</span>
            ) : listo ? (
              <Link href="/empresa/documentos" className="link-btn">Mis documentos</Link>
            ) : null}
          </div>
          <div className={ms.modalAcciones}>
            {listo ? (
              <button type="button" className="btn btn-primary" onClick={() => void generar()} disabled={ocupado !== null || Boolean(motivo)}>
                <Icon name="descargar" />
                {ocupado === "generar" ? "Generando…" : "Generar PDF y Excel"}
              </button>
            ) : (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void cerrar()}>Cerrar</button>
            )}
          </div>
        </>
      }
    >
      {cuerpo()}
    </Dialogo>
  );
}

/* ============================================================ piezas */

function Descargas({ em, ocupado, onDescargar }: { em: EmisionRopa; ocupado: Ocupado; onDescargar: (em: EmisionRopa, f: FormatoRopa) => void }) {
  return (
    <span className={s.descargasFila}>
      {(["pdf", "xlsx"] as FormatoRopa[]).map((f) => em.documentos[f] ? (
        <button key={f} type="button" className="btn btn-ghost btn-sm" onClick={() => onDescargar(em, f)} disabled={ocupado !== null}
          title={tamanoLegible(em.documentos[f]!.tamano_bytes)}>
          <Icon name={f === "pdf" ? "pdf" : "tabla"} />
          {ocupado === `${em.id}-${f}` ? "…" : f === "pdf" ? "PDF" : "Excel"}
        </button>
      ) : (
        <span key={f} className={ms.ayuda} title="Se eliminó de Mis documentos">{f === "pdf" ? "PDF" : "Excel"} eliminado</span>
      ))}
    </span>
  );
}

/** Marca «(sensible)» y «(NNA)» como en el informe. */
function TextoMarcado({ texto }: { texto: string }) {
  const partes = texto.split(/(\(sensible\)|\(NNA\))/);
  return (
    <>
      {partes.map((p, i) =>
        p === "(sensible)" ? <span key={i} className="badge tone-alto">sensible</span>
          : p === "(NNA)" ? <span key={i} className="badge tone-info">NNA</span>
          : <span key={i}>{p}</span>,
      )}
    </>
  );
}

