"use client";

/**
 * Ficha del elemento o flujo elegido en el mapa, en una ventana centrada: qué datos trata, de quiénes,
 * dónde están, con quién se comparten, qué falta completar y qué riesgos tiene. Desde aquí se edita,
 * se agrega un flujo, se confirma lo que vino de una plantilla o se elimina, y se navega a los flujos y
 * elementos conectados sin cerrar la ventana.
 */
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { fechaHoraChile } from "@/lib/fechas";
import {
  ETIQUETA_ORIGEN, ETIQUETA_TIPO, nombreDato, nombreOpcion, nombrePais, nombreSubtipo, nombreTitular, plural,
  type CatalogoMapa, type ElementoMapa, type FlujoMapa, type HallazgoMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import { Dialogo } from "./Dialogos";
import type { Seleccion } from "./GrafoMapa";
import s from "./mapa.module.css";

export const ICONO_TIPO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };

export function Etiquetas({ catalogo, codigos, modo, vacio = "Sin informar" }: {
  catalogo: CatalogoMapa | null;
  codigos: string[];
  modo: "datos" | "titulares";
  vacio?: string;
}) {
  if (!codigos.length) return <span className={s.sinDato}>{vacio}</span>;
  return (
    <ul className={s.etiquetas}>
      {codigos.map((c) => {
        const sensible = modo === "datos" && catalogo?.categorias_datos.find((x) => x.codigo === c)?.sensible;
        const nna = modo === "titulares" && catalogo?.categorias_titulares.find((x) => x.codigo === c)?.nna;
        return (
          <li key={c} className={s.etiqueta} data-tono={sensible ? "sensible" : nna ? "nna" : undefined}>
            {modo === "datos" ? nombreDato(catalogo, c) : nombreTitular(catalogo, c)}
            {sensible ? <span className="sr-only"> (dato sensible)</span> : null}
          </li>
        );
      })}
    </ul>
  );
}

function Dato({ etiqueta, children, ancho = false }: { etiqueta: string; children: ReactNode; ancho?: boolean }) {
  return (
    <div className={s.fichaDato} data-ancho={ancho || undefined}>
      <dt>{etiqueta}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function SinDato({ texto = "Sin informar" }: { texto?: string }) {
  return <span className={s.sinDato}>{texto}</span>;
}

export function FichaDetalle({
  catalogo,
  vista,
  seleccion,
  onSeleccionar,
  onCerrar,
  onEditarElemento,
  onEditarFlujo,
  onNuevoFlujo,
  onEliminarElemento,
  onEliminarFlujo,
  onConfirmar,
  ocupado,
}: {
  catalogo: CatalogoMapa;
  vista: VistaMapa;
  seleccion: Seleccion;
  onSeleccionar: (s: Seleccion | null) => void;
  onCerrar: () => void;
  onEditarElemento: (e: ElementoMapa) => void;
  onEditarFlujo: (f: FlujoMapa) => void;
  onNuevoFlujo: (origenId: number | null, destinoId?: number | null) => void;
  onEliminarElemento: (e: ElementoMapa) => void;
  onEliminarFlujo: (f: FlujoMapa) => void;
  onConfirmar: (sel: Seleccion) => void;
  ocupado: boolean;
}) {
  const porId = new Map(vista.elementos.map((e) => [e.id, e]));
  const riesgos: HallazgoMapa[] = vista.hallazgos.filter((h) =>
    seleccion.tipo === "elemento" ? h.elementos.includes(seleccion.id) : h.flujos.includes(seleccion.id));
  const pendiente = vista.completitud.pendientes.find((p) => p.tipo === seleccion.tipo && p.id === seleccion.id);

  const avisos = (porConfirmar: boolean, editar: () => void) => (
    <>
      {porConfirmar ? (
        <div className={s.fichaAviso} data-tono="pendiente">
          <Icon name="info" />
          <div>
            <strong>Por confirmar.</strong> Vino de una plantilla o de tu evaluación. Revisa que corresponda a tu empresa
            y confírmalo; si no aplica, elimínalo.
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onConfirmar(seleccion)} disabled={ocupado}>
            <Icon name="check" />
            Confirmar
          </button>
        </div>
      ) : null}
      {pendiente?.faltan.length ? (
        <div className={s.fichaAviso} data-tono="falta">
          <Icon name="alerta" />
          <div>
            <strong>Falta completar:</strong> {pendiente.faltan.join(", ")}. Con esta información los riesgos y tu
            registro de actividades quedan más precisos.
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={editar} disabled={ocupado}>
            <Icon name="editar" />
            Completar
          </button>
        </div>
      ) : null}
    </>
  );

  /* ---------------------------------------------------------------- elemento */
  if (seleccion.tipo === "elemento") {
    const e = porId.get(seleccion.id);
    if (!e) return null;
    const salientes = vista.flujos.filter((f) => f.origen_id === e.id);
    const entrantes = vista.flujos.filter((f) => f.destino_id === e.id);
    const esTercero = e.tipo === "tercero";
    const requiereContrato = esTercero && (!e.rol_tercero || catalogo.roles_tercero.find((r) => r.codigo === e.rol_tercero)?.requiere_contrato);
    return (
      <Dialogo
        tamano="lg"
        icono={ICONO_TIPO[e.tipo]}
        antetitulo={`${ETIQUETA_TIPO[e.tipo]}${e.subtipo ? ` · ${nombreSubtipo(catalogo, e.tipo, e.subtipo)}` : ""}`}
        titulo={e.nombre}
        descripcion={e.descripcion ?? undefined}
        onCerrar={onCerrar}
        cerrarAlHacerClicFuera
        etiquetaCerrar="Cerrar la ficha"
        cabeceraExtra={
          <div className={s.fichaBarra}>
            <ul className={s.etiquetas} aria-label="Características">
              {e.derivados.sensibles.length ? <li className={s.etiqueta} data-tono="sensible">Datos sensibles</li> : null}
              {e.incluye_nna ? <li className={s.etiqueta} data-tono="nna">Niños, niñas y adolescentes</li> : null}
              {e.derivados.fuera_de_chile ? <li className={s.etiqueta} data-tono="internacional">Fuera de Chile</li> : null}
              {e.pendiente_revision ? <li className={s.etiqueta} data-tono="pendiente">Por confirmar</li> : null}
              {!e.derivados.sensibles.length && !e.incluye_nna && !e.derivados.fuera_de_chile && !e.pendiente_revision ? (
                <li className={s.etiqueta} data-tono="ok">Sin alertas especiales</li>
              ) : null}
            </ul>
            <div className={s.fichaAcciones}>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => onEditarElemento(e)} disabled={ocupado}>
                <Icon name="editar" />
                Editar
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNuevoFlujo(e.id)} disabled={ocupado || vista.elementos.length < 2}>
                <Icon name="flujo" />
                Agregar flujo
              </button>
              <button type="button" className={`btn btn-ghost btn-sm ${s.botonEliminar}`} onClick={() => onEliminarElemento(e)} disabled={ocupado}>
                <Icon name="basura" />
                Eliminar
              </button>
            </div>
          </div>
        }
      >
        {avisos(e.pendiente_revision, () => onEditarElemento(e))}
        <div className={s.fichaRejilla}>
          <section className={s.fichaTarjeta} aria-labelledby="ficha-general">
            <h3 id="ficha-general" className={s.fichaSubtitulo}><Icon name="lista" />Información general</h3>
            <dl className={s.fichaDatos}>
              <Dato etiqueta="País de alojamiento">
                {e.derivados.pais_efectivo ? (
                  <>
                    {nombrePais(catalogo, e.derivados.pais_efectivo)}
                    {!e.pais ? <span className={s.sinDato}> (se asume)</span> : null}
                  </>
                ) : <SinDato />}
              </Dato>
              <Dato etiqueta={esTercero ? "Razón social o marca" : "Proveedor"}>{e.proveedor ?? <SinDato />}</Dato>
              <Dato etiqueta={esTercero ? "Responsable de la relación" : "Responsable interno"}>{e.responsable ?? <SinDato texto="Sin asignar" />}</Dato>
              {esTercero ? (
                <>
                  <Dato etiqueta="Rol del tercero">{e.rol_tercero ? nombreOpcion(catalogo.roles_tercero, e.rol_tercero) : <SinDato />}</Dato>
                  <Dato etiqueta="Contrato de tratamiento">
                    {!requiereContrato ? "No requiere" : (
                      <span className={s.etiqueta} data-tono={e.contrato_firmado ? "ok" : "sensible"}>
                        {e.contrato_firmado === true ? "Firmado" : e.contrato_firmado === false ? "Sin contrato" : "Por confirmar"}
                      </span>
                    )}
                  </Dato>
                </>
              ) : null}
              <Dato etiqueta="Registro" ancho>
                {ETIQUETA_ORIGEN[e.origen]} · actualizado {fechaHoraChile(e.fecha_actualizacion)}
              </Dato>
            </dl>
          </section>
          <section className={s.fichaTarjeta} aria-labelledby="ficha-datos">
            <h3 id="ficha-datos" className={s.fichaSubtitulo}><Icon name="candado" />Datos personales</h3>
            <dl className={s.fichaDatos}>
              <Dato etiqueta={esTercero ? "Datos que recibe o trata" : "Categorías de datos"} ancho>
                <Etiquetas catalogo={catalogo} codigos={e.categorias_datos} modo="datos" />
              </Dato>
              <Dato etiqueta="¿De quiénes son?" ancho>
                <Etiquetas catalogo={catalogo} codigos={e.categorias_titulares} modo="titulares" />
                {e.incluye_nna && !e.categorias_titulares.includes("nna") ? (
                  <span className={s.etiqueta} data-tono="nna" style={{ marginTop: 6 }}>Incluye niños, niñas o adolescentes</span>
                ) : null}
              </Dato>
            </dl>
          </section>
        </div>

        <section className={s.fichaTarjeta} aria-labelledby="ficha-conexiones">
          <h3 id="ficha-conexiones" className={s.fichaSubtitulo}>
            <Icon name="flujo" />Conexiones
            <span className={s.fichaContador}>{plural(salientes.length + entrantes.length, "flujo", "flujos")}</span>
          </h3>
          {salientes.length + entrantes.length === 0 ? (
            <div className={s.fichaVacio}>
              <p>Este elemento aún no envía ni recibe datos. Agrega los flujos para saber con quién comparte información.</p>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNuevoFlujo(e.id)} disabled={ocupado || vista.elementos.length < 2}>
                <Icon name="mas" />
                Agregar el primer flujo
              </button>
            </div>
          ) : (
            <div className={s.fichaConexiones}>
              <Vinculos titulo="Envía datos a" flujos={salientes} campo="destino_id" porId={porId} onElegir={onSeleccionar} />
              <Vinculos titulo="Recibe datos de" flujos={entrantes} campo="origen_id" porId={porId} onElegir={onSeleccionar} />
            </div>
          )}
        </section>
        <Riesgos lista={riesgos} />
      </Dialogo>
    );
  }

  /* ---------------------------------------------------------------- flujo */
  const f = vista.flujos.find((x) => x.id === seleccion.id);
  if (!f) return null;
  const o = porId.get(f.origen_id);
  const d = porId.get(f.destino_id);
  return (
    <Dialogo
      tamano="lg"
      icono={f.derivados.internacional ? "globo" : "flujo"}
      tonoIcono={f.derivados.internacional ? "aviso" : "acento"}
      antetitulo="Flujo de datos"
      titulo={`${o?.nombre ?? "?"} → ${d?.nombre ?? "?"}`}
      descripcion={f.finalidad ?? undefined}
      onCerrar={onCerrar}
      cerrarAlHacerClicFuera
      etiquetaCerrar="Cerrar la ficha"
      cabeceraExtra={
        <div className={s.fichaBarra}>
          <ul className={s.etiquetas} aria-label="Características">
            {f.derivados.internacional ? <li className={s.etiqueta} data-tono="internacional">Transferencia internacional</li> : null}
            {f.derivados.hacia_tercero ? <li className={s.etiqueta}>Hacia un tercero</li> : null}
            {f.derivados.sensibles.length ? <li className={s.etiqueta} data-tono="sensible">Datos sensibles</li> : null}
            {f.incluye_nna ? <li className={s.etiqueta} data-tono="nna">Niños, niñas y adolescentes</li> : null}
            {f.pendiente_revision ? <li className={s.etiqueta} data-tono="pendiente">Por confirmar</li> : null}
          </ul>
          <div className={s.fichaAcciones}>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onEditarFlujo(f)} disabled={ocupado}>
              <Icon name="editar" />
              Editar
            </button>
            <button type="button" className={`btn btn-ghost btn-sm ${s.botonEliminar}`} onClick={() => onEliminarFlujo(f)} disabled={ocupado}>
              <Icon name="basura" />
              Eliminar
            </button>
          </div>
        </div>
      }
    >
      {avisos(f.pendiente_revision, () => onEditarFlujo(f))}
      <div className={s.recorrido} aria-label="Recorrido de los datos">
        {[o, d].map((x, i) =>
          x ? (
            <button key={`${x.id}-${i}`} type="button" className={s.recorridoNodo} data-tipo={x.tipo} onClick={() => onSeleccionar({ tipo: "elemento", id: x.id })}>
              <span className={s.recorridoRol}>{i === 0 ? "Desde" : "Hacia"}</span>
              <span className={s.recorridoNombre}><Icon name={ICONO_TIPO[x.tipo]} />{x.nombre}</span>
              <span className={s.recorridoPais} data-fuera={x.derivados.fuera_de_chile || undefined}>
                <Icon name="globo" />{x.derivados.pais_efectivo ? nombrePais(catalogo, x.derivados.pais_efectivo) : "País sin informar"}
              </span>
            </button>
          ) : <span key={i} />,
        )}
        <span className={s.recorridoFlecha} data-internacional={f.derivados.internacional || undefined} aria-hidden="true">
          <Icon name="flecha" />
        </span>
      </div>
      <div className={s.fichaRejilla}>
        <section className={s.fichaTarjeta} aria-labelledby="ficha-flujo-como">
          <h3 id="ficha-flujo-como" className={s.fichaSubtitulo}><Icon name="lista" />Cómo viajan</h3>
          <dl className={s.fichaDatos}>
            <Dato etiqueta="Finalidad" ancho>{f.finalidad ?? <SinDato />}</Dato>
            <Dato etiqueta="Frecuencia">{f.frecuencia ? nombreOpcion(catalogo.frecuencias, f.frecuencia) : <SinDato />}</Dato>
            <Dato etiqueta="Medio">{f.medio ? nombreOpcion(catalogo.medios, f.medio) : <SinDato />}</Dato>
            <Dato etiqueta="¿Viajan cifrados?">
              {f.cifrado === true ? <span className={s.etiqueta} data-tono="ok">Sí</span>
                : f.cifrado === false ? <span className={s.etiqueta} data-tono="sensible">No</span> : <SinDato texto="No se sabe" />}
            </Dato>
            {f.derivados.internacional ? (
              <Dato etiqueta="Garantía de la transferencia">
                {f.garantia ? (
                  <span className={s.etiqueta} data-tono={f.derivados.garantia_valida ? "ok" : "sensible"}>
                    {nombreOpcion(catalogo.garantias, f.garantia)}
                  </span>
                ) : <span className={s.etiqueta} data-tono="sensible">Sin garantía</span>}
              </Dato>
            ) : null}
            <Dato etiqueta="Registro" ancho>{ETIQUETA_ORIGEN[f.origen]} · actualizado {fechaHoraChile(f.fecha_actualizacion)}</Dato>
          </dl>
        </section>
        <section className={s.fichaTarjeta} aria-labelledby="ficha-flujo-datos">
          <h3 id="ficha-flujo-datos" className={s.fichaSubtitulo}><Icon name="candado" />Qué datos viajan</h3>
          <dl className={s.fichaDatos}>
            <Dato etiqueta="Categorías de datos" ancho><Etiquetas catalogo={catalogo} codigos={f.categorias_datos} modo="datos" /></Dato>
            <Dato etiqueta="¿De quiénes son?" ancho><Etiquetas catalogo={catalogo} codigos={f.categorias_titulares} modo="titulares" /></Dato>
          </dl>
        </section>
      </div>
      <Riesgos lista={riesgos} />
    </Dialogo>
  );
}

function Vinculos({ titulo, flujos, campo, porId, onElegir }: {
  titulo: string;
  flujos: FlujoMapa[];
  campo: "origen_id" | "destino_id";
  porId: Map<number, ElementoMapa>;
  onElegir: (s: Seleccion) => void;
}) {
  return (
    <div className={s.vinculosColumna}>
      <h4 className={s.vinculosTitulo}>{titulo} <span>({flujos.length})</span></h4>
      {flujos.length ? (
        <ul className={s.vinculos}>
          {flujos.map((f) => {
            const otro = porId.get(f[campo]);
            return (
              <li key={f.id}>
                <button type="button" className={s.vinculo} onClick={() => onElegir({ tipo: "flujo", id: f.id })} title="Ver la ficha del flujo">
                  <Icon name={f.derivados.internacional ? "globo" : otro ? ICONO_TIPO[otro.tipo] : "flujo"} />
                  <span>
                    <strong>{otro?.nombre ?? "?"}</strong>
                    {f.finalidad ? <small>{f.finalidad}</small> : null}
                  </span>
                  {f.derivados.sensibles.length ? <i className={s.puntoSensible} title="Con datos sensibles" /> : null}
                  <Icon name="flecha" />
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className={s.sinDato}>Ninguno</p>
      )}
    </div>
  );
}

function Riesgos({ lista }: { lista: HallazgoMapa[] }) {
  if (!lista.length) return null;
  return (
    <section className={s.fichaTarjeta} aria-labelledby="ficha-riesgos">
      <h3 id="ficha-riesgos" className={s.fichaSubtitulo}>
        <Icon name="brechas" />Riesgos detectados<span className={s.fichaContador}>{lista.length}</span>
      </h3>
      <ul className={s.hallazgos}>
        {lista.map((h) => (
          <li key={h.codigo} className={s.hallazgo} data-sev={h.severidad} style={{ padding: "10px 12px 10px 16px" }}>
            <div className={s.hallazgoCabeza}>
              <strong style={{ fontSize: "var(--fs-sm)" }}>{h.titulo}</strong>
              <span className={s.sev} data-sev={h.severidad}>{h.severidad}</span>
            </div>
            <p className={s.queHacer}><strong>Qué hacer:</strong> {h.recomendacion}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
