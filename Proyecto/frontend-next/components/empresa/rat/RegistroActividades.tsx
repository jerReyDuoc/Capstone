"use client";

/**
 * /empresa/registro-actividades — Registro de actividades de tratamiento de la empresa.
 *
 *   Lista        las actividades con su estado, avance y lo que hay que revisar, más el avance
 *                global del registro.
 *   Detalle      el formulario por pasos de una actividad, sus estados y su historial de versiones
 *                (components/empresa/rat/DetalleActividad.tsx).
 *
 * Los sistemas, bases de datos, terceros y flujos se eligen del mapa de datos: lo que cambie en el
 * mapa se refleja aquí y devuelve a revisión las actividades que lo usan.
 * Es parte del servicio contratado: sin contrato vigente, la página lo explica.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { useEspacioEmpresa } from "@/components/empresa/EspacioEmpresaContexto";
import { Dialogo } from "@/components/empresa/mapa/Dialogos";
import ms from "@/components/empresa/mapa/mapa.module.css";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { fechaHoraChile } from "@/lib/fechas";
import { cargarCatalogoMapa, cargarMapa, mensajeError, plural, type CatalogoMapa, type VistaMapa } from "@/lib/mapaDatos";
import {
  cargarCatalogoRat, cargarRegistro, crearActividad, ETIQUETA_ESTADO, filtrarActividades, textoVersion, TONO_ESTADO,
  type Actividad, type CatalogoRat, type FiltroEstado, type ListaRegistro,
} from "@/lib/registroActividades";
import { DetalleActividad } from "./DetalleActividad";
import { InformeRat } from "./InformeRat";
import s from "./rat.module.css";

type Aviso = { tono: "ok" | "error"; texto: string } | null;

const FILTROS: { id: FiltroEstado; titulo: string }[] = [
  { id: "activas", titulo: "Todas" },
  { id: "borrador", titulo: "Borradores" },
  { id: "en_revision", titulo: "En revisión" },
  { id: "vigente", titulo: "Vigentes" },
  { id: "archivada", titulo: "Archivadas" },
];

export function RegistroActividades() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const [catalogo, setCatalogo] = useState<CatalogoRat | null>(null);
  const [catalogoMapa, setCatalogoMapa] = useState<CatalogoMapa | null>(null);
  const [registro, setRegistro] = useState<ListaRegistro | null>(null);
  const [mapa, setMapa] = useState<VistaMapa | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<number | null>(null);
  const [filtro, setFiltro] = useState<FiltroEstado>("activas");
  const [busqueda, setBusqueda] = useState("");
  const [creando, setCreando] = useState(false);
  const [informe, setInforme] = useState(false);
  const [aviso, setAviso] = useState<Aviso>(null);

  const listo = espacio.tipo === "listo";

  const sesionVencida = useCallback(
    (e: unknown) => {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace("/ingresar?motivo=sesion");
        return true;
      }
      return false;
    },
    [router],
  );

  const recargar = useCallback(async () => {
    try {
      const [r, m] = await Promise.all([cargarRegistro(), cargarMapa()]);
      setRegistro(r);
      setMapa(m);
    } catch (e) {
      if (!sesionVencida(e)) setError(mensajeError(e, "No pudimos cargar el registro de actividades. Inténtalo de nuevo."));
    }
  }, [sesionVencida]);

  useEffect(() => {
    if (!listo) return;
    Promise.all([cargarCatalogoRat(), cargarCatalogoMapa()])
      .then(([c, cm]) => {
        setCatalogo(c);
        setCatalogoMapa(cm);
      })
      .catch((e) => {
        if (!sesionVencida(e)) setError(mensajeError(e, "No pudimos cargar el registro de actividades. Inténtalo de nuevo."));
      });
    void recargar();
  }, [listo, recargar, sesionVencida]);

  // Los avisos se van solos
  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), aviso.tono === "error" ? 9000 : 5000);
    return () => clearTimeout(t);
  }, [aviso]);

  // Al abrir o cerrar una actividad, la página vuelve arriba
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [abierta]);

  const visibles = useMemo(
    () => (registro ? filtrarActividades(registro.actividades, filtro, busqueda) : []),
    [registro, filtro, busqueda],
  );

  const encabezado = (
    <header className="page-head">
      <div>
        <span className="eyebrow">Privacidad</span>
        <h1 className="page-title">Registro de actividades de tratamiento</h1>
        <p className="page-sub">
          Las actividades en que tu empresa usa datos personales, con la información que exige la Ley 21.719. Se arma
          sobre tu <Link href="/empresa/mapa-datos">mapa de datos</Link>, así no escribes dos veces lo mismo.
        </p>
      </div>
      {registro && abierta === null ? (
        <div className={s.acciones}>
          <button type="button" className="btn btn-ghost" onClick={() => setInforme(true)} title="Descarga el informe en PDF o Excel">
            <Icon name="documento" />
            Informe del registro
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setCreando(true)}>
            <Icon name="mas" />
            Nueva actividad
          </button>
        </div>
      ) : null}
    </header>
  );

  /* ---------------------------------------------------- estados de la página */
  if (espacio.tipo === "cargando" || (listo && (!registro || !catalogo || !mapa) && !error)) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="skeleton" style={{ height: 120 }} role="status" aria-label="Cargando el registro de actividades" />
        <div className="skeleton" style={{ height: 320 }} />
      </div>
    );
  }
  if (espacio.tipo === "error" || error) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <div className="callout" role="alert">
          <Icon name="alerta" />
          <span>{espacio.tipo === "error" ? espacio.mensaje : error}</span>
        </div>
      </div>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <div className={s.pagina}>
        {encabezado}
        <p className="callout" role="status">
          <Icon name="candado" />
          <span>
            El registro de actividades es parte del servicio contratado y el de tu empresa no está activo.{" "}
            {espacio.contrato.contrato.documentos_disponibles ? (
              <>Tus documentos siguen disponibles en <Link href="/empresa/documentos">Mis documentos</Link>.</>
            ) : (
              "Contacta a Therion Labs para renovarlo."
            )}
          </span>
        </p>
      </div>
    );
  }
  if (!registro || !catalogo || !mapa) return null;

  const avisoFlotante = aviso ? (
    <div className={ms.aviso} data-tono={aviso.tono} role={aviso.tono === "error" ? "alert" : "status"}>
      <Icon name={aviso.tono === "error" ? "alerta" : "check"} />
      <span>{aviso.texto}</span>
      <button type="button" className="icon-btn" onClick={() => setAviso(null)} aria-label="Cerrar aviso">
        <Icon name="cerrar" />
      </button>
    </div>
  ) : null;

  /* ---------------------------------------------------- detalle */
  if (abierta !== null) {
    return (
      <div className={s.pagina}>
        {encabezado}
        <DetalleActividad
          key={abierta}
          id={abierta}
          catalogo={catalogo}
          catalogoMapa={catalogoMapa}
          mapa={mapa}
          onVolver={() => {
            setAbierta(null);
            void recargar();
          }}
          onAviso={setAviso}
          onSesionVencida={sesionVencida}
          onMapaDesactualizado={async () => {
            try {
              setMapa(await cargarMapa());
            } catch {
              /* el detalle avisa igual */
            }
          }}
        />
        {avisoFlotante}
      </div>
    );
  }

  /* ---------------------------------------------------- lista */
  const g = registro.global;
  const kpis = [
    { etiqueta: "Vigentes", valor: g.por_estado.vigente, icono: "check" as const },
    { etiqueta: "En revisión", valor: g.por_estado.en_revision, icono: "reloj" as const, tono: g.por_revisar ? "aviso" : undefined },
    { etiqueta: "Borradores", valor: g.por_estado.borrador, icono: "editar" as const },
    { etiqueta: "Archivadas", valor: g.por_estado.archivada, icono: "carpeta" as const },
  ];

  return (
    <div className={s.pagina}>
      {encabezado}

      {!registro.mapa.iniciado ? (
        <p className="callout callout-aviso" role="status">
          <Icon name="mapa" />
          <span>
            <strong>Primero arma tu mapa de datos.</strong> Las actividades toman de allí los sistemas, bases de datos,
            terceros y flujos. <Link href="/empresa/mapa-datos">Ir al mapa de datos</Link>
          </span>
        </p>
      ) : null}

      {registro.actividades.length === 0 ? (
        <section className={s.vacio} aria-labelledby="titulo-vacio">
          <h2 id="titulo-vacio" className="card-title">Aún no registras actividades</h2>
          <p className="card-sub">
            Una actividad de tratamiento es cada uso que tu empresa da a los datos personales: pagar remuneraciones,
            vender en línea, seleccionar personal, enviar comunicaciones comerciales…
          </p>
          <ol>
            <li>Ponle un nombre y escribe para qué se usan los datos.</li>
            <li>Elige del mapa los sistemas y flujos que participan.</li>
            <li>Completa la base de licitud, plazos de conservación y medidas de seguridad.</li>
            <li>Revísala y déjala vigente: queda una versión fija para demostrar cumplimiento.</li>
          </ol>
          <button type="button" className="btn btn-primary" onClick={() => setCreando(true)}>
            <Icon name="mas" />
            Registrar la primera actividad
          </button>
        </section>
      ) : (
        <>
          <section className={s.resumen} aria-label="Resumen del registro">
            <div className={s.global}>
              <span className={ms.kpiEtiqueta}><Icon name="diana" />Avance del registro</span>
              <span className={s.globalValor}>{g.porcentaje} %</span>
              <div className={ms.barra} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={g.porcentaje} aria-label="Avance del registro">
                <span style={{ width: `${g.porcentaje}%` }} />
              </div>
              <span className={ms.kpiPie}>
                {g.actividades ? `${plural(g.completas, "actividad completa", "actividades completas")} de ${g.actividades}` : "Sin actividades activas"}
              </span>
            </div>
            {kpis.map((k) => (
              <div key={k.etiqueta} className={ms.kpi} data-tono={k.tono}>
                <span className={ms.kpiEtiqueta}><Icon name={k.icono} />{k.etiqueta}</span>
                <span className={ms.kpiValor}>{k.valor}</span>
              </div>
            ))}
          </section>

          {g.por_revisar ? (
            <p className="callout callout-aviso" role="status">
              <Icon name="alerta" />
              <span>
                <strong>{plural(g.por_revisar, "actividad volvió", "actividades volvieron")} a revisión</strong> porque
                cambió algo del mapa de datos que usan. Revísalas y déjalas vigentes otra vez.
              </span>
            </p>
          ) : null}

          <div className={s.filtros}>
            <div className="chip-group" role="group" aria-label="Filtrar por estado">
              {FILTROS.map((f) => {
                const n = f.id === "activas" ? g.actividades : g.por_estado[f.id];
                return (
                  <button key={f.id} type="button" className="chip" aria-pressed={filtro === f.id} onClick={() => setFiltro(f.id)}>
                    {f.titulo} <span aria-hidden>· {n}</span>
                  </button>
                );
              })}
            </div>
            <div className={`input-wrap ${s.buscar}`}>
              <Icon name="buscar" />
              <input
                className="input"
                type="search"
                placeholder="Buscar por nombre o área"
                aria-label="Buscar actividades"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />
            </div>
          </div>

          {visibles.length ? (
            <ul className={s.lista} aria-label="Actividades del registro">
              {visibles.map((a) => (
                <li key={a.id}>
                  <FilaActividad actividad={a} onAbrir={() => setAbierta(a.id)} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="callout"><Icon name="info" /><span>No hay actividades con ese filtro.</span></p>
          )}
        </>
      )}

      {informe ? (
        <InformeRat
          correoUsuario={espacio.tipo === "listo" ? espacio.datos.usuario.email : null}
          onCerrar={() => setInforme(false)}
          onSesionVencida={sesionVencida}
          onVerPendientes={() => {
            setInforme(false);
            setFiltro(g.por_estado.en_revision ? "en_revision" : "borrador");
          }}
        />
      ) : null}
      {creando ? (
        <DialogoNueva
          onCerrar={() => setCreando(false)}
          onCrear={async (nombre) => {
            const r = await crearActividad({ nombre });
            setCreando(false);
            setAviso({ tono: "ok", texto: "Creamos la actividad en borrador. Complétala paso a paso." });
            setAbierta(r.actividad.id);
          }}
          onSesionVencida={sesionVencida}
        />
      ) : null}
      {avisoFlotante}
    </div>
  );
}

function FilaActividad({ actividad: a, onAbrir }: { actividad: Actividad; onAbrir: () => void }) {
  const revisar = a.estado === "en_revision" && a.motivos_revision.length > 0;
  return (
    <button type="button" className={s.fila} onClick={onAbrir} data-revisar={revisar || undefined}>
      <span className={s.filaNombre}>
        <span className={s.filaMeta}>
          <span className={`badge ${TONO_ESTADO[a.estado]}`}>{ETIQUETA_ESTADO[a.estado]}</span>
          {revisar ? <span className={ms.etiqueta} data-tono="internacional">Cambió el mapa</span> : null}
          {a.resumen.hay_sensibles ? <span className={ms.etiqueta} data-tono="sensible">Datos sensibles</span> : null}
          {a.resumen.incluye_nna ? <span className={ms.etiqueta} data-tono="nna">Niños, niñas o adolescentes</span> : null}
          {a.resumen.transferencias ? (
            <span className={ms.etiqueta} data-tono="internacional">
              {plural(a.resumen.transferencias, "transferencia internacional", "transferencias internacionales")}
            </span>
          ) : null}
        </span>
        <strong>{a.nombre}</strong>
        <span className={s.filaMeta}>
          {a.area ? <span>{a.area}</span> : null}
          <span>{textoVersion(a)}</span>
          {a.fecha_actualizacion ? <span>Actualizada {fechaHoraChile(a.fecha_actualizacion)}</span> : null}
        </span>
      </span>
      <span className={s.filaAvance}>
        <span>
          {a.completitud.porcentaje} % completa
          {a.completitud.faltantes.length ? ` · faltan ${a.completitud.faltantes.length}` : ""}
        </span>
        <span className={ms.barra} aria-hidden>
          <span style={{ width: `${a.completitud.porcentaje}%` }} />
        </span>
      </span>
      <span className={s.filaIr} aria-hidden><Icon name="flecha" /></span>
    </button>
  );
}

function DialogoNueva({
  onCerrar,
  onCrear,
  onSesionVencida,
}: {
  onCerrar: () => void;
  onCrear: (nombre: string) => Promise<void>;
  onSesionVencida: (e: unknown) => boolean;
}) {
  const [nombre, setNombre] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const crear = async () => {
    const valor = nombre.trim();
    if (valor.length < 3) {
      setError("Escribe un nombre de al menos 3 caracteres.");
      return;
    }
    setOcupado(true);
    setError("");
    try {
      await onCrear(valor);
    } catch (e) {
      if (!onSesionVencida(e)) setError(mensajeError(e, "No pudimos crear la actividad. Inténtalo de nuevo."));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <Dialogo
      titulo="Nueva actividad de tratamiento"
      descripcion="Ponle un nombre que la identifique. Después la completas paso a paso."
      estrecho
      onCerrar={onCerrar}
      onEnviar={crear}
      pie={
        <div>
          <button type="button" className="btn btn-ghost" onClick={onCerrar} disabled={ocupado}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={ocupado}>{ocupado ? "Creando…" : "Crear actividad"}</button>
        </div>
      }
    >
      <div className={ms.campo}>
        <label htmlFor="rat-nombre-nueva">Nombre de la actividad<span className={ms.obligatorio} aria-hidden>*</span></label>
        <input
          id="rat-nombre-nueva"
          className={ms.control}
          value={nombre}
          maxLength={150}
          onChange={(e) => setNombre(e.target.value)}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby="rat-nombre-nueva-ayuda"
          data-autofoco
        />
        <span id="rat-nombre-nueva-ayuda" className={ms.ayuda}>Por ejemplo: «Pago de remuneraciones» o «Ventas en la tienda en línea».</span>
        {error ? <span className={ms.error} role="alert">{error}</span> : null}
      </div>
    </Dialogo>
  );
}
