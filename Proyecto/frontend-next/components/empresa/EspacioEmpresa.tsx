"use client";

/**
 * HU-28 criterio 2 · Espacio de la empresa del usuario definitivo (puerta de entrada tras el login).
 *
 * Muestra su empresa, el contrato y las evaluaciones migradas desde el autodiagnóstico. Cada
 * evaluación se abre en el panel de resultados (/panel en modo "cliente", que lee por
 * /bff/cliente/api). HU-29 agrega aquí los cursos y el tutor IA.
 *
 * HU-30: sin contrato vigente el backend responde 403 CONTRATO_NO_VIGENTE en este espacio.
 * Entonces se muestra la situación del contrato (GET /api/cliente/contrato) con lo que sigue
 * disponible: los resultados e informes (gratuitos) y, durante el plazo de gracia, las constancias.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { BrandMark } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarContratoCliente, cargarEspacioEmpresa, diasParaTermino, fechaCorta, SIN_SERVICIO,
  type ContratoClienteApi, type EspacioEmpresaApi,
} from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import { descargarConstancia } from "@/lib/formacion";
import s from "@/components/admin/admin.module.css";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; datos: EspacioEmpresaApi }
  | { tipo: "sin_servicio"; contrato: ContratoClienteApi }
  | { tipo: "error"; mensaje: string };

export function EspacioEmpresa() {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });

  useEffect(() => {
    cargarEspacioEmpresa()
      .then((datos) => setEstado({ tipo: "listo", datos }))
      .catch(async (e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
        }
        if (e instanceof ErrorBff && e.status === 403 && SIN_SERVICIO.has(e.info.codigo)) {
          try {
            setEstado({ tipo: "sin_servicio", contrato: await cargarContratoCliente() });
            return;
          } catch {
            /* cae al mensaje genérico */
          }
        }
        setEstado({ tipo: "error", mensaje: "No pudimos cargar el espacio de tu empresa. Inténtalo de nuevo." });
      });
  }, [router]);

  const datos = estado.tipo === "listo" ? estado.datos : null;
  const dias = datos ? diasParaTermino(datos.empresa.fecha_termino_contrato) : null;

  return (
    <div className={s.pagina}>
      <a href="#contenido" className="skip-link">Saltar al contenido</a>
      <header className={s.barra}>
        <div className={s.marca}>
          <BrandMark aria-hidden="true" />
          <span>
            ComplianceAI
            <span className={s.marcaSub}>
              {datos ? datos.empresa.razon_social
                : estado.tipo === "sin_servicio" ? estado.contrato.empresa.razon_social : "Espacio de tu empresa"}
            </span>
          </span>
        </div>
        <BotonCerrarSesion tipo="cliente" />
      </header>

      <main id="contenido" className={s.contenido} tabIndex={-1}>
        {estado.tipo === "cargando" ? <p className={s.vacio} role="status">Cargando…</p> : null}
        {estado.tipo === "error" ? (
          <div className={s.alerta} role="alert"><strong>{estado.mensaje}</strong></div>
        ) : null}
        {estado.tipo === "sin_servicio" ? <SinServicio datos={estado.contrato} /> : null}

        {datos ? (
          <>
            <div>
              <h1 className="page-title">Hola, {datos.usuario.nombre.split(" ")[0]}</h1>
              <p className="page-sub">
                Este es el espacio de <strong>{datos.empresa.razon_social}</strong> en ComplianceAI. Aquí está el
                historial de su autodiagnóstico y, pronto, los cursos y el tutor IA del servicio contratado.
              </p>
            </div>

            {dias != null && dias <= 30 ? (
              <p className="callout" role="status">
                {dias >= 0
                  ? `El contrato de tu empresa termina en ${dias} ${dias === 1 ? "día" : "días"} (${fechaCorta(datos.empresa.fecha_termino_contrato)}). Contacta a Therion Labs para renovarlo.`
                  : "El contrato de tu empresa terminó. Contacta a Therion Labs."}
              </p>
            ) : null}

            <section className="card" aria-labelledby="titulo-evaluaciones">
              <div className="card-head">
                <div>
                  <h2 id="titulo-evaluaciones" className="card-title">Evaluaciones de tu empresa</h2>
                  <p className="card-sub">
                    Las que se traspasaron desde el autodiagnóstico, con sus resultados, brechas, plan formativo e
                    informe PDF.
                  </p>
                </div>
              </div>
              {!datos.evaluaciones.length ? (
                <p className={s.vacio}>Tu empresa aún no tiene evaluaciones asociadas. Therion Labs las traspasará pronto.</p>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Evaluaciones de la empresa</caption>
                    <thead>
                      <tr>
                        <th scope="col">Evaluación</th>
                        <th scope="col">Estado</th>
                        <th scope="col">Puntaje general</th>
                        <th scope="col">Traspasada</th>
                        <th scope="col"><span className="sr-only">Acciones</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {datos.evaluaciones.map((ev) => (
                        <tr key={ev.id}>
                          <td>N.º {ev.id}<span className={s.sub}>Iniciada {fechaCorta(ev.fecha_inicio)}</span></td>
                          <td>
                            <span className={`badge tone-${ev.completada ? "ok" : "medio"}`}>
                              {ev.completada ? "Completada" : "En curso"}
                            </span>
                          </td>
                          <td>{ev.puntaje_general != null ? `${ev.puntaje_general} / 100` : "—"}</td>
                          <td>{fechaCorta(ev.fecha_migracion)}</td>
                          <td>
                            <Link className="btn btn-primary btn-sm" href={`/panel?evaluacion=${ev.id}`} prefetch={false}>
                              Ver resultados
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="card" aria-labelledby="titulo-contrato">
              <div className="card-head">
                <div>
                  <h2 id="titulo-contrato" className="card-title">Tu empresa</h2>
                </div>
              </div>
              <dl style={{ display: "grid", gap: 8, margin: 0 }}>
                <div><dt className={s.sub}>Razón social</dt><dd style={{ margin: 0 }}>{datos.empresa.razon_social}</dd></div>
                <div><dt className={s.sub}>RUT</dt><dd style={{ margin: 0 }}>{datos.empresa.rut}</dd></div>
                <div><dt className={s.sub}>Rubro</dt><dd style={{ margin: 0 }}>{datos.empresa.rubro ?? "—"}</dd></div>
                <div>
                  <dt className={s.sub}>Contrato</dt>
                  <dd style={{ margin: 0 }}>
                    {fechaCorta(datos.empresa.fecha_inicio_contrato)} al {fechaCorta(datos.empresa.fecha_termino_contrato)}
                  </dd>
                </div>
                <div><dt className={s.sub}>Usuario</dt><dd style={{ margin: 0 }}>{datos.usuario.email}</dd></div>
              </dl>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}


/** HU-30 · Lo que ve el usuario cuando el servicio pagado de su empresa no está activo. */
function SinServicio({ datos }: { datos: ContratoClienteApi }) {
  const [aviso, setAviso] = useState("");
  const [bajando, setBajando] = useState<number | null>(null);
  const { contrato, documentos } = datos;

  return (
    <>
      <div>
        <h1 className="page-title">Servicio no disponible</h1>
        <p className="callout" role="status">{contrato.mensaje}</p>
      </div>

      <section className="card" aria-labelledby="titulo-gratis">
        <div className="card-head">
          <div>
            <h2 id="titulo-gratis" className="card-title">Resultados de tus evaluaciones</h2>
            <p className="card-sub">Los resultados, el informe PDF y el plan formativo siguen disponibles.</p>
          </div>
        </div>
        {!documentos.evaluaciones.length ? (
          <p className={s.vacio}>Tu empresa no tiene evaluaciones asociadas.</p>
        ) : (
          <ul style={{ display: "grid", gap: 8, margin: 0, paddingLeft: 0, listStyle: "none" }}>
            {documentos.evaluaciones.map((ev) => (
              <li key={ev.id}>
                <Link className="btn btn-sm" href={`/panel?evaluacion=${ev.id}`} prefetch={false}>
                  Ver resultados de la evaluación N.º {ev.id}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {contrato.documentos_disponibles ? (
        <section className="card" aria-labelledby="titulo-documentos">
          <div className="card-head">
            <div>
              <h2 id="titulo-documentos" className="card-title">Tus documentos</h2>
              <p className="card-sub">
                {contrato.documentos_disponibles_hasta
                  ? `Puedes descargarlos hasta el ${fechaCorta(contrato.documentos_disponibles_hasta)}.`
                  : "Puedes descargarlos mientras se resuelve la situación del contrato."}
              </p>
            </div>
          </div>
          {!documentos.constancias.length ? (
            <p className={s.vacio}>No hay constancias de módulos completados.</p>
          ) : (
            <ul style={{ display: "grid", gap: 8, margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {documentos.constancias.map((k) => (
                <li key={k.ruta_id}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={bajando !== null}
                    aria-busy={bajando === k.ruta_id}
                    onClick={async () => {
                      setBajando(k.ruta_id);
                      try {
                        const { blob, nombre } = await descargarConstancia(k.ruta_id);
                        descargarBlob(blob, nombre);
                        setAviso(`Descargamos ${nombre}.`);
                      } catch {
                        setAviso("No pudimos descargar la constancia. Inténtalo de nuevo.");
                      } finally {
                        setBajando(null);
                      }
                    }}
                  >
                    Constancia: {k.modulo} ({fechaCorta(k.fecha_completado)})
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
        </section>
      ) : null}

      <p className="card-sub">
        Tus derechos sobre tus datos personales (acceso, rectificación, supresión, oposición, portabilidad y
        bloqueo) siguen disponibles en todo momento. Para renovar el servicio, contacta a Therion Labs.
      </p>
    </>
  );
}
