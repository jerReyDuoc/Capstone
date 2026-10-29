"use client";

/**
 * HU-29 criterio 3 · /empresa/documentos — "Mis documentos" en su propia página
 * (correcciones 29-10). Por ahora muestra lo mismo que tenía la sección del espacio de la
 * empresa; su funcionalidad completa (p. ej. los borradores de la HU-16) llega después.
 *
 * HU-30: sin contrato vigente solo se muestra durante el plazo de gracia.
 */
import { MisDocumentos } from "./MisDocumentos";
import { useEspacioEmpresa } from "./EspacioEmpresaContexto";
import s from "@/components/admin/admin.module.css";

export function PaginaDocumentos() {
  const estado = useEspacioEmpresa();
  const disponible = estado.tipo === "listo" || (estado.tipo === "sin_servicio" && estado.contrato.contrato.documentos_disponibles);

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Mi empresa</span>
          <h1 className="page-title">Mis documentos</h1>
          <p className="page-sub">Informes, borradores, evidencias y constancias de tu empresa. Eliminar un documento es definitivo.</p>
        </div>
      </header>

      {estado.tipo === "cargando" ? (
        <div className="skeleton" style={{ height: 200 }} role="status" aria-label="Cargando tus documentos" />
      ) : estado.tipo === "error" ? (
        <div className={s.alerta} role="alert"><strong>{estado.mensaje}</strong></div>
      ) : disponible ? (
        <MisDocumentos encabezado={false} />
      ) : (
        <p className="callout" role="status">
          Terminó el plazo para descargar los documentos de tu empresa. Para renovar el servicio, contacta a Therion Labs.
        </p>
      )}
    </>
  );
}
