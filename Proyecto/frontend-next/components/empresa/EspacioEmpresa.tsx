"use client";

/**
 * HU-28 criterio 2 · Espacio de la empresa del usuario definitivo (puerta de entrada tras el login).
 *
 * Muestra su empresa y el contrato. HU-29: "Mis evaluaciones" (historial con gráfico de
 * evolución global y por dimensión, y reevaluación desde la cuenta) y "Mis documentos"
 * (informes PDF, borradores, evidencias y constancias, con descarga y eliminación). Cada
 * evaluación se abre en el panel de resultados (/panel en modo "cliente", por /bff/cliente/api).
 *
 * HU-30: sin contrato vigente el backend responde 403 CONTRATO_NO_VIGENTE en este espacio.
 * Entonces se muestra la situación del contrato (GET /api/cliente/contrato) con lo que sigue
 * disponible: el historial y los resultados (gratuitos) y, durante el plazo de gracia, Mis documentos.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BotonCerrarSesion } from "@/components/acceso/BotonCerrarSesion";
import { BrandMark } from "@/components/ui/Icon";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarContratoCliente, cargarEspacioEmpresa, diasParaTermino, fechaCorta, SIN_SERVICIO,
  type ContratoClienteApi, type EspacioEmpresaApi,
} from "@/lib/empresa";
import { MisDocumentos } from "./MisDocumentos";
import { MisEvaluaciones } from "./MisEvaluaciones";
import s from "@/components/admin/admin.module.css";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; datos: EspacioEmpresaApi }
  | { tipo: "sin_servicio"; contrato: ContratoClienteApi }
  | { tipo: "error"; mensaje: string };

export function EspacioEmpresa() {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [recargaDocumentos, setRecargaDocumentos] = useState(0);

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
                Este es el espacio de <strong>{datos.empresa.razon_social}</strong> en ComplianceAI: el historial de
                sus evaluaciones y cómo evoluciona su madurez, las reevaluaciones y los documentos de cumplimiento.
              </p>
            </div>

            {dias != null && dias <= 30 ? (
              <p className="callout" role="status">
                {dias >= 0
                  ? `El contrato de tu empresa termina en ${dias} ${dias === 1 ? "día" : "días"} (${fechaCorta(datos.empresa.fecha_termino_contrato)}). Contacta a Therion Labs para renovarlo.`
                  : "El contrato de tu empresa terminó. Contacta a Therion Labs."}
              </p>
            ) : null}

            {/* HU-29: historial con su evolución y reevaluación, y los documentos de la empresa */}
            <MisEvaluaciones onDocumentoGuardado={() => setRecargaDocumentos((n) => n + 1)} />
            <MisDocumentos recarga={recargaDocumentos} />

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
  const { contrato } = datos;

  return (
    <>
      <div>
        <h1 className="page-title">Servicio no disponible</h1>
        <p className="callout" role="status">{contrato.mensaje}</p>
      </div>

      {/* HU-29: los resultados son gratuitos (el historial se ve igual); reevaluar exige el servicio */}
      <MisEvaluaciones />
      {contrato.documentos_disponibles ? <MisDocumentos /> : null}

      <p className="card-sub">
        Tus derechos sobre tus datos personales (acceso, rectificación, supresión, oposición, portabilidad y
        bloqueo) siguen disponibles en todo momento. Para renovar el servicio, contacta a Therion Labs.
      </p>
    </>
  );
}
