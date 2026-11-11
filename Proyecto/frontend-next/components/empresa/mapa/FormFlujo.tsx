"use client";

/**
 * Agregar o editar un flujo de datos entre dos elementos del mapa: qué datos viajan, de
 * quiénes, para qué, con qué frecuencia y por qué medio, si viajan cifrados y, si el destino
 * está en otro país, con qué garantía se protege la transferencia internacional.
 */
import { useId, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  contieneContacto, esInternacional, ETIQUETA_TIPO_PLURAL, mensajeError, nombrePais,
  type CatalogoMapa, type DatosFlujo, type FlujoMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import { Dialogo, SelectorCategorias } from "./Dialogos";
import s from "./mapa.module.css";

type Errores = Partial<Record<keyof DatosFlujo | "general", string>>;

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
    (!eD.rol_tercero || catalogo.roles_tercero.find((r) => r.codigo === eD.rol_tercero)?.requiere_contrato);

  const grupos = (["sistema", "base_datos", "tercero"] as TipoElemento[]).map((t) => ({
    tipo: t,
    items: vista.elementos.filter((e) => e.tipo === t).sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),
  }));

  const copiarDelOrigen = () => {
    if (!eO) return;
    setDatos([...new Set([...datos, ...eO.categorias_datos])]);
    setTitulares([...new Set([...titulares, ...eO.categorias_titulares])]);
    if (eO.incluye_nna) setNna(true);
  };

  const guardar = async () => {
    const e: Errores = {};
    if (!origen) e.origen_id = "Elige de dónde salen los datos.";
    if (!destino) e.destino_id = "Elige hacia dónde van los datos.";
    else if (origen === destino) e.destino_id = "El origen y el destino deben ser distintos.";
    if (contieneContacto(finalidad)) e.finalidad = "No escribas correos, RUT ni teléfonos de personas: describe para qué se envían los datos.";
    setErrores(e);
    if (Object.keys(e).length) return;
    setOcupado(true);
    try {
      await onGuardar({
        origen_id: origen as number,
        destino_id: destino as number,
        finalidad: finalidad.trim() || null,
        categorias_datos: datos,
        categorias_titulares: titulares,
        nna_declarado: nna,
        frecuencia: frecuencia || null,
        medio: medio || null,
        cifrado: cifrado === "si" ? true : cifrado === "no" ? false : null,
        garantia: internacional ? garantia || null : flujo?.garantia ? garantia || null : null,
      });
    } catch (err) {
      const campo = err instanceof ErrorBff ? (err.info.campo as keyof DatosFlujo | undefined) : undefined;
      setErrores({ [campo ?? "general"]: mensajeError(err, "No pudimos guardar el flujo. Inténtalo de nuevo.") });
      setOcupado(false);
    }
  };

  const selector = (campo: "origen_id" | "destino_id", valor: number | "", cambiar: (v: number | "") => void, etiqueta: string) => (
    <div className={s.campo}>
      <label htmlFor={`${id}-${campo}`}>
        {etiqueta}
        <span className={s.obligatorio} aria-hidden="true">*</span>
      </label>
      <select
        id={`${id}-${campo}`}
        className={`select ${s.control}`}
        value={valor}
        onChange={(e) => cambiar(e.target.value ? Number(e.target.value) : "")}
        aria-required
        aria-invalid={Boolean(errores[campo]) || undefined}
        data-autofoco={(campo === "origen_id" && !valor) || (campo === "destino_id" && Boolean(origen) && !valor) || undefined}
      >
        <option value="">Elige un elemento</option>
        {grupos.map((g) =>
          g.items.length ? (
            <optgroup key={g.tipo} label={ETIQUETA_TIPO_PLURAL[g.tipo]}>
              {g.items.map((el) => (
                <option key={el.id} value={el.id} disabled={campo === "destino_id" ? el.id === origen : el.id === destino}>
                  {el.nombre}
                  {el.derivados.pais_efectivo && el.derivados.pais_efectivo !== catalogo.pais_local ? ` (${nombrePais(catalogo, el.derivados.pais_efectivo)})` : ""}
                </option>
              ))}
            </optgroup>
          ) : null,
        )}
      </select>
      {errores[campo] ? <p className={s.error} role="alert">{errores[campo]}</p> : null}
    </div>
  );

  return (
    <Dialogo
      titulo={editando ? "Editar flujo de datos" : "Agregar un flujo de datos"}
      descripcion="Un flujo indica qué datos personales viajan de un elemento a otro: entre tus sistemas, hacia terceros o fuera del país."
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
              {ocupado ? "Guardando…" : editando ? "Guardar cambios" : "Agregar flujo"}
            </button>
          </div>
        </>
      }
    >
      <div className={s.rejilla}>
        {selector("origen_id", origen, setOrigen, "Desde (origen)")}
        {selector("destino_id", destino, setDestino, "Hacia (destino)")}
      </div>

      {internacional ? (
        <div className={s.alertaInfo} role="status">
          <Icon name="globo" />
          <div style={{ display: "grid", gap: 10, flex: 1 }}>
            <span>
              <strong>Es una transferencia internacional</strong> ({nombrePais(catalogo, paisO ?? catalogo.pais_local)} →{" "}
              {nombrePais(catalogo, paisD)}). Registra cómo se protegen los datos en el país de destino.
            </span>
            <div className={s.campo}>
              <label htmlFor={`${id}-garantia`}>Garantía de la transferencia</label>
              <select id={`${id}-garantia`} className={`select ${s.control}`} value={garantia} onChange={(e) => setGarantia(e.target.value)}>
                <option value="">Aún no lo sé</option>
                {catalogo.garantias.map((g) => (
                  <option key={g.codigo} value={g.codigo}>{g.nombre}</option>
                ))}
              </select>
              <p className={s.ayuda}>{garantiaElegida?.descripcion ?? "Sin una garantía, la transferencia aparecerá como un riesgo."}</p>
            </div>
          </div>
        </div>
      ) : sinPais ? (
        <p className={s.alertaInfo} role="status">
          <Icon name="info" />
          <span>«{eD?.nombre}» no tiene país de alojamiento: no podemos saber si este flujo sale de Chile. Complétalo en su ficha.</span>
        </p>
      ) : null}
      {sinContrato ? (
        <p className={s.alertaInfo} role="status">
          <Icon name="alerta" />
          <span>«{eD?.nombre}» no tiene un contrato de tratamiento de datos confirmado.</span>
        </p>
      ) : null}

      <div className={s.campo}>
        <label htmlFor={`${id}-finalidad`}>¿Para qué se envían los datos?</label>
        <textarea
          id={`${id}-finalidad`}
          className={s.control}
          value={finalidad}
          maxLength={300}
          onChange={(e) => setFinalidad(e.target.value)}
          placeholder="Ej.: despachar los pedidos, pagar las remuneraciones, generar respuestas del asistente…"
          aria-invalid={Boolean(errores.finalidad) || undefined}
        />
        {errores.finalidad ? <p className={s.error} role="alert">{errores.finalidad}</p> : <p className={s.ayuda}>{finalidad.length}/300</p>}
      </div>

      <div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={copiarDelOrigen} disabled={!eO}>
          <Icon name="copiar" />
          Copiar las categorías del origen
        </button>
      </div>
      <SelectorCategorias
        catalogo={catalogo}
        modo="datos"
        valor={datos}
        onCambiar={setDatos}
        etiqueta="Datos personales que viajan"
        error={errores.categorias_datos}
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
      />
      <label className={s.casillaLinea}>
        <input type="checkbox" checked={nna || titularNna} disabled={titularNna} onChange={(e) => setNna(e.target.checked)} />
        <span><strong>Incluye datos de niños, niñas o adolescentes</strong></span>
      </label>

      <div className={s.rejilla}>
        <div className={s.campo}>
          <label htmlFor={`${id}-frecuencia`}>Frecuencia</label>
          <select id={`${id}-frecuencia`} className={`select ${s.control}`} value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)}>
            <option value="">Sin informar</option>
            {catalogo.frecuencias.map((o) => (
              <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
            ))}
          </select>
        </div>
        <div className={s.campo}>
          <label htmlFor={`${id}-medio`}>Medio</label>
          <select id={`${id}-medio`} className={`select ${s.control}`} value={medio} onChange={(e) => setMedio(e.target.value)}>
            <option value="">Sin informar</option>
            {catalogo.medios.map((o) => (
              <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
            ))}
          </select>
        </div>
        <fieldset className={`${s.campo} ${s.ancho}`} style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className={s.etiquetaCampo}>¿Los datos viajan cifrados?</legend>
          <div className={s.segmentado}>
            {([["si", "Sí"], ["no", "No"], ["", "No lo sé"]] as const).map(([v, t]) => (
              <label key={v || "nose"} className={s.segmento}>
                <input type="radio" name={`${id}-cifrado`} checked={cifrado === v} onChange={() => setCifrado(v)} />
                <span>{t}</span>
              </label>
            ))}
          </div>
          {sensibles.length && cifrado !== "si" ? (
            <p className={s.ayuda} style={{ color: "var(--critico)" }}>
              Viajan datos sensibles: deberían ir cifrados (por ejemplo, con HTTPS, SFTP o VPN).
            </p>
          ) : null}
        </fieldset>
      </div>

      {errores.general ? (
        <p className="dialogo-error" role="alert">
          <Icon name="alerta" />
          {errores.general}
        </p>
      ) : null}
    </Dialogo>
  );
}
