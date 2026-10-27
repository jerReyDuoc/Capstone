"use client";

/**
 * HU-28 criterio 2 · Espacio de la empresa del usuario definitivo (puerta de entrada tras el login).
 *
 * Muestra su empresa, el contrato y las evaluaciones migradas desde el autodiagnóstico. Cada
 * evaluación se abre en el panel de resultados (/panel en modo "cliente", que lee por
 * /bff/cliente/api). HU-29 agrega aquí los cursos y el tutor IA.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { BrandMark } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { cargarEspacioEmpresa, diasParaTermino, fechaCorta, type EspacioEmpresaApi } from "@/lib/empresa";
import s from "@/components/admin/admin.module.css";

type Estado = { tipo: "cargando" } | { tipo: "listo"; datos: EspacioEmpresaApi } | { tipo: "error"; mensaje: string };

export function EspacioEmpresa() {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });

  useEffect(() => {
    cargarEspacioEmpresa()
      .then((datos) => setEstado({ tipo: "listo", datos }))
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
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
            <span className={s.marcaSub}>{datos ? datos.empresa.razon_social : "Espacio de tu empresa"}</span>
          </span>
        </div>
        <BotonCerrarSesion tipo="cliente" />
      </header>

      <main id="contenido" className={s.contenido} tabIndex={-1}>
        {estado.tipo === "cargando" ? <p className={s.vacio} role="status">Cargando…</p> : null}
        {estado.tipo === "error" ? (
          <div className={s.alerta} role="alert"><strong>{estado.mensaje}</strong></div>
        ) : null}

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
