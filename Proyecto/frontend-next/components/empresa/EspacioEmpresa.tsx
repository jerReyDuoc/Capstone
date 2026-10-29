"use client";

/**
 * HU-28 criterio 2 · "Mi empresa": puerta de entrada del usuario definitivo tras el login.
 *
 * Correcciones 29-10: el espacio se separó en tres páginas con la barra lateral del panel.
 * Aquí quedan la empresa, su contrato y accesos directos; el historial vive en
 * /empresa/evaluaciones y los documentos en /empresa/documentos.
 *
 * HU-30: sin contrato vigente se muestra la situación del contrato con lo que sigue disponible:
 * el historial y los resultados (gratuitos) y, durante el plazo de gracia, Mis documentos.
 */
import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";
import { diasParaTermino, fechaCorta, type ContratoClienteApi } from "@/lib/empresa";
import { useEspacioEmpresa } from "./EspacioEmpresaContexto";
import s from "@/components/admin/admin.module.css";

export function EspacioEmpresa() {
  const estado = useEspacioEmpresa();

  if (estado.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 220 }} role="status" aria-label="Cargando el espacio de tu empresa" />;
  }
  if (estado.tipo === "error") {
    return <div className={s.alerta} role="alert"><strong>{estado.mensaje}</strong></div>;
  }
  if (estado.tipo === "sin_servicio") return <SinServicio datos={estado.contrato} />;

  const { datos } = estado;
  const dias = diasParaTermino(datos.empresa.fecha_termino_contrato);

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Mi empresa</span>
          <h1 className="page-title">Hola, {datos.usuario.nombre.split(" ")[0]}</h1>
          <p className="page-sub">
            Este es el espacio de <strong>{datos.empresa.razon_social}</strong> en ComplianceAI.
          </p>
        </div>
      </header>

      {dias <= 30 ? (
        <p className="callout" role="status">
          {dias >= 0
            ? `El contrato de tu empresa termina en ${dias} ${dias === 1 ? "día" : "días"} (${fechaCorta(datos.empresa.fecha_termino_contrato)}). Contacta a Therion Labs para renovarlo.`
            : "El contrato de tu empresa terminó. Contacta a Therion Labs."}
        </p>
      ) : null}

      <nav aria-label="Accesos directos" className={s.rejilla}>
        <Acceso href="/empresa/evaluaciones" icono="historial" titulo="Mis evaluaciones">
          Tu historial, cómo evoluciona la madurez y las reevaluaciones.
        </Acceso>
        <Acceso href="/panel" icono="diagnostico" titulo="Resultados">
          Diagnóstico, dominios y brechas de la evaluación más reciente.
        </Acceso>
        <Acceso href="/empresa/documentos" icono="carpeta" titulo="Mis documentos">
          Informes, borradores, evidencias y constancias.
        </Acceso>
      </nav>

      <section className="card" aria-labelledby="titulo-empresa">
        <div className="card-head">
          <h2 id="titulo-empresa" className="card-title">Tu empresa</h2>
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
  );
}

function Acceso({ href, icono, titulo, children }: { href: string; icono: IconName; titulo: string; children: string }) {
  return (
    <Link href={href} className="card acceso-empresa" prefetch={false}>
      <Icon name={icono} />
      <span>
        <strong>{titulo}</strong>
        <span className={s.sub}>{children}</span>
      </span>
    </Link>
  );
}

/** HU-30 · Lo que ve el usuario cuando el servicio pagado de su empresa no está activo. */
function SinServicio({ datos }: { datos: ContratoClienteApi }) {
  const { contrato } = datos;

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">{datos.empresa.razon_social}</span>
          <h1 className="page-title">Servicio no disponible</h1>
        </div>
      </header>
      <p className="callout" role="status">{contrato.mensaje}</p>

      {/* HU-29: los resultados son gratuitos (el historial se ve igual); reevaluar exige el servicio */}
      <nav aria-label="Lo que sigue disponible" className={s.rejilla}>
        <Acceso href="/empresa/evaluaciones" icono="historial" titulo="Mis evaluaciones">
          Tu historial y los resultados siguen disponibles.
        </Acceso>
        {contrato.documentos_disponibles ? (
          <Acceso href="/empresa/documentos" icono="carpeta" titulo="Mis documentos">
            Descarga tus documentos mientras dure el plazo de gracia.
          </Acceso>
        ) : null}
      </nav>

      <p className="card-sub">
        Tus derechos sobre tus datos personales (acceso, rectificación, supresión, oposición, portabilidad y
        bloqueo) siguen disponibles en todo momento. Para renovar el servicio, contacta a Therion Labs.
      </p>
    </>
  );
}
