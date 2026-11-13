"use client";

/**
 * Lista de verificación de la revisión interna: cada actividad del registro y cada elemento y flujo del mapa con
 * sus puntos. La plataforma muestra el resultado de su comprobación; la persona decide si lo verifica, si acepta
 * una advertencia o falla con una justificación, o si deja una observación para corregirlo.
 */
import Link from "next/link";
import { useId, useMemo, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { plural } from "@/lib/mapaDatos";
import {
  accionesPunto, enlaceCorregir, filtrarObjetos, TITULO_PUNTO, TITULO_RESULTADO, TONO_RESULTADO, verificablesDeUnaVez,
  type Criterio, type Decision, type FiltroAvance, type FiltroTipo, type ObjetoRevision, type Punto, type TipoObjeto,
} from "@/lib/revisionInterna";
import s from "./revision.module.css";

const ICONO_TIPO: Record<TipoObjeto, IconName> = { actividad: "lista", elemento: "tabla", flujo: "flujo" };
const TIPOS: { id: FiltroTipo; titulo: string }[] = [
  { id: "todos", titulo: "Todo" },
  { id: "actividad", titulo: "Actividades" },
  { id: "elemento", titulo: "Elementos" },
  { id: "flujo", titulo: "Flujos" },
];
const AVANCES: { id: FiltroAvance; titulo: string }[] = [
  { id: "todos", titulo: "Cualquier avance" },
  { id: "pendientes", titulo: "Por revisar" },
  { id: "con_fallas", titulo: "Con fallas" },
  { id: "completos", titulo: "Revisados" },
];

export function ListaVerificacion({
  objetos,
  criterios,
  abiertasPor,
  soloLectura = false,
  onDecidir,
  onObservar,
}: {
  objetos: ObjetoRevision[];
  criterios: Record<TipoObjeto, Criterio[]>;
  /** Observaciones abiertas por clave de objeto. */
  abiertasPor: Record<string, number>;
  soloLectura?: boolean;
  onDecidir: (clave: string, decision: Decision, criterios?: string[], nota?: string) => Promise<void>;
  onObservar: (o: ObjetoRevision, criterio?: Punto) => void;
}) {
  const id = useId();
  const [tipo, setTipo] = useState<FiltroTipo>("todos");
  const [avance, setAvance] = useState<FiltroAvance>("pendientes");
  const [busqueda, setBusqueda] = useState("");
  const [abiertos, setAbiertos] = useState<Set<string>>(() => new Set());
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [aceptar, setAceptar] = useState<{ o: ObjetoRevision; p: Punto } | null>(null);

  const visibles = useMemo(() => filtrarObjetos(objetos, tipo, avance, busqueda), [objetos, tipo, avance, busqueda]);
  const pregunta = useMemo(() => {
    const m = new Map<string, string>();
    for (const [t, lista] of Object.entries(criterios)) for (const c of lista) m.set(`${t}:${c.codigo}`, c.pregunta);
    return m;
  }, [criterios]);
  const pendientes = objetos.filter((o) => !o.completo).length;

  const alternar = (clave: string) =>
    setAbiertos((prev) => {
      const n = new Set(prev);
      if (n.has(clave)) n.delete(clave);
      else n.add(clave);
      return n;
    });

  const ejecutar = async (marca: string, fn: () => Promise<void>) => {
    setOcupado(marca);
    try {
      await fn();
    } finally {
      setOcupado(null);
    }
  };

  return (
    <section aria-labelledby={`${id}-t`} style={{ display: "grid", gap: "var(--sp-4)" }}>
      <h2 id={`${id}-t`} className="sr-only">Lista de verificación</h2>
      <div className={s.filtros}>
        <div className={s.filtrosGrupo}>
          <div className="chip-group" role="group" aria-label="Qué revisar">
            {TIPOS.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={tipo === t.id} onClick={() => setTipo(t.id)}>
                {t.titulo}
              </button>
            ))}
          </div>
          <select className="select" aria-label="Filtrar por avance" value={avance} onChange={(e) => setAvance(e.target.value as FiltroAvance)}>
            {AVANCES.map((a) => <option key={a.id} value={a.id}>{a.titulo}</option>)}
          </select>
        </div>
        <div className={`input-wrap ${s.buscar}`}>
          <Icon name="buscar" />
          <input className="input" type="search" placeholder="Buscar por nombre" aria-label="Buscar en la lista"
            value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
        </div>
      </div>

      {visibles.length ? (
        <ul className={s.objetos}>
          {visibles.map((o) => {
            const abierto = abiertos.has(o.clave);
            const pct = o.por_revisar ? Math.round((100 * o.revisados) / o.por_revisar) : 100;
            const deUnaVez = verificablesDeUnaVez(o);
            const obs = abiertasPor[o.clave] ?? 0;
            const corregir = enlaceCorregir(o);
            return (
              <li key={o.clave} className={s.objeto} data-completo={o.completo} data-bloqueo={o.bloqueos > 0}>
                <button type="button" className={s.objetoCabeza} aria-expanded={abierto} aria-controls={`${id}-${o.clave}`}
                  onClick={() => alternar(o.clave)}>
                  <span className={s.tipoIcono} aria-hidden="true"><Icon name={ICONO_TIPO[o.tipo]} /></span>
                  <span className={s.objetoNombre}>
                    <strong>{o.nombre}</strong>
                    <small>{o.tipo === "actividad" ? "Actividad" : o.tipo === "elemento" ? "Elemento del mapa" : "Flujo del mapa"} · {o.subtitulo}</small>
                  </span>
                  <span className={s.objetoEstado}>
                    {o.bloqueos ? <span className="badge tone-critico">Impide el registro oficial</span> : null}
                    {o.fallas && !o.bloqueos ? <span className="badge tone-critico">{plural(o.fallas, "falla", "fallas")}</span> : null}
                    {obs ? <span className={ms.etiqueta} data-tono="sensible">{plural(obs, "observación", "observaciones")}</span> : null}
                    {o.completo ? <span className="badge tone-ok">Revisado</span> : (
                      <span className={s.mini}>
                        {o.revisados}/{o.por_revisar}
                        <span className={ms.barra} aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
                      </span>
                    )}
                    <Icon name="flecha" className={s.chevron} />
                  </span>
                </button>
                {abierto ? (
                  <div id={`${id}-${o.clave}`} className={s.objetoCuerpo}>
                    {o.items.map((p) => {
                      const acc = accionesPunto(p);
                      const marca = `${o.clave}:${p.codigo}`;
                      return (
                        <div key={p.codigo} className={s.punto} data-revision={p.revision}>
                          <span>
                            <span className={`badge ${TONO_RESULTADO[p.resultado]}`}>{TITULO_RESULTADO[p.resultado]}</span>
                            {p.bloqueante && p.resultado === "falla" ? <><br /><span className={s.bloqueante}>Bloqueante</span></> : null}
                          </span>
                          <div className={s.puntoTexto}>
                            <strong>{p.titulo}</strong>
                            <p>{p.detalle}</p>
                            {p.resultado !== "no_aplica" ? (
                              <span className={s.pregunta}><Icon name="info" />{pregunta.get(`${o.tipo}:${p.codigo}`)}</span>
                            ) : null}
                            {p.nota ? <span className={s.nota}><strong>Justificación:</strong> {p.nota}</span> : null}
                          </div>
                          <div className={s.puntoAcciones}>
                            {p.resultado !== "no_aplica" ? (
                              <span className={s.estadoPunto} data-revision={p.revision}>
                                <Icon name={p.revision === "verificado" || p.revision === "aceptado" ? "check" : p.revision === "desactualizado" ? "refrescar" : "reloj"} />
                                {TITULO_PUNTO[p.revision]}
                              </span>
                            ) : null}
                            {!soloLectura && acc.verificar ? (
                              <button type="button" className="btn btn-primary btn-sm" disabled={ocupado !== null}
                                onClick={() => void ejecutar(marca, () => onDecidir(o.clave, "verificado", [p.codigo]))}>
                                <Icon name="check" />{ocupado === marca ? "Guardando…" : "Verificar"}
                              </button>
                            ) : null}
                            {!soloLectura && acc.aceptar ? (
                              <button type="button" className="btn btn-ghost btn-sm" disabled={ocupado !== null} onClick={() => setAceptar({ o, p })}>
                                Aceptar…
                              </button>
                            ) : null}
                            {!soloLectura && p.resultado === "falla" ? (
                              <Link className="btn btn-ghost btn-sm" href={enlaceCorregir(o, p.codigo).href}>
                                <Icon name="editar" />Corregir
                              </Link>
                            ) : null}
                            {!soloLectura && p.resultado !== "no_aplica" ? (
                              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onObservar(o, p)}>
                                <Icon name="mensaje" />Observar
                              </button>
                            ) : null}
                            {!soloLectura && acc.deshacer ? (
                              <button type="button" className="link-btn" disabled={ocupado !== null}
                                onClick={() => void ejecutar(marca, () => onDecidir(o.clave, "pendiente", [p.codigo]))}>
                                Deshacer
                              </button>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                    {!soloLectura ? (
                      <div className={s.objetoAcciones}>
                        <Link className="btn btn-ghost btn-sm" href={corregir.href}><Icon name="editar" />{corregir.texto}</Link>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onObservar(o)}>
                          <Icon name="mensaje" />Observación general
                        </button>
                        {deUnaVez > 1 ? (
                          <button type="button" className="btn btn-primary btn-sm" disabled={ocupado !== null}
                            onClick={() => void ejecutar(o.clave, () => onDecidir(o.clave, "verificado"))}>
                            <Icon name="check" />{ocupado === o.clave ? "Guardando…" : `Verificar los ${deUnaVez} puntos que revisé`}
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="callout" role="status">
          <Icon name={avance === "pendientes" && !pendientes ? "check" : "info"} />
          <span>
            {avance === "pendientes" && !pendientes
              ? "Revisaste todos los elementos de la lista. Cierra las observaciones abiertas y marca la versión como revisada."
              : "No hay elementos con ese filtro."}
          </span>
        </p>
      )}

      {aceptar ? (
        <DialogoAceptar
          objeto={aceptar.o}
          punto={aceptar.p}
          onCerrar={() => setAceptar(null)}
          onAceptar={async (nota) => {
            await onDecidir(aceptar.o.clave, "aceptado", [aceptar.p.codigo], nota);
            setAceptar(null);
          }}
        />
      ) : null}
    </section>
  );
}

function DialogoAceptar({ objeto, punto, onCerrar, onAceptar }: {
  objeto: ObjetoRevision;
  punto: Punto;
  onCerrar: () => void;
  onAceptar: (nota: string) => Promise<void>;
}) {
  const id = useId();
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const enviar = async () => {
    if (nota.trim().length < 10) {
      setError("Escribe por qué lo aceptas (al menos 10 caracteres).");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      await onAceptar(nota);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "No pudimos guardar. Inténtalo de nuevo.");
      setOcupado(false);
    }
  };
  return (
    <Dialogo tamano="sm" icono="alerta" tonoIcono="aviso" antetitulo={objeto.nombre}
      titulo={`Aceptar «${punto.titulo}»`}
      descripcion="Úsalo cuando el resultado refleja la realidad y tu empresa lo asume (por ejemplo, un contrato en firma). La justificación queda en la constancia y en el paquete de evidencia."
      onCerrar={onCerrar} onEnviar={() => void enviar()}
      pie={<>
        <button type="button" className="btn btn-ghost" onClick={onCerrar}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={ocupado}>{ocupado ? "Guardando…" : "Aceptar con justificación"}</button>
      </>}>
      <p className={ms.alertaInfo}><Icon name="info" /><span>{punto.detalle}</span></p>
      <div className={ms.campo}>
        <label htmlFor={`${id}-n`}>Justificación</label>
        <textarea id={`${id}-n`} className={ms.control} rows={4} maxLength={1000} value={nota} data-autofoco
          aria-invalid={Boolean(error)} onChange={(e) => setNota(e.target.value)}
          placeholder="Ej.: el contrato con el proveedor está en revisión legal y se firma este mes." />
        <p className={ms.ayuda}>Describe la situación de la empresa, no a personas (sin correos, RUT ni teléfonos). {nota.trim().length}/1000</p>
        {error ? <p className="dialogo-error" role="alert">{error}</p> : null}
      </div>
    </Dialogo>
  );
}
