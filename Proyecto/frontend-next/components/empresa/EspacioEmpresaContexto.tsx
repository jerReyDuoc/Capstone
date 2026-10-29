"use client";

/**
 * HU-28/29/30 · Datos del espacio de la empresa compartidos por sus páginas
 * (/empresa, /empresa/evaluaciones y /empresa/documentos).
 *
 * Correcciones 29-10: el espacio se separó en tres páginas con la barra lateral del panel; la
 * carga de la empresa y del contrato (antes en EspacioEmpresa) vive aquí para hacerse una vez.
 *
 * HU-30: sin contrato vigente el backend responde 403 CONTRATO_NO_VIGENTE; entonces se carga
 * la situación del contrato (GET /api/cliente/contrato) para mostrar lo que sigue disponible.
 */
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarContratoCliente, cargarEspacioEmpresa, SIN_SERVICIO,
  type ContratoClienteApi, type EspacioEmpresaApi,
} from "@/lib/empresa";

export type EstadoEspacio =
  | { tipo: "cargando" }
  | { tipo: "listo"; datos: EspacioEmpresaApi }
  | { tipo: "sin_servicio"; contrato: ContratoClienteApi }
  | { tipo: "error"; mensaje: string };

const Ctx = createContext<EstadoEspacio>({ tipo: "cargando" });

export function EspacioEmpresaProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [estado, setEstado] = useState<EstadoEspacio>({ tipo: "cargando" });

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

  return <Ctx.Provider value={estado}>{children}</Ctx.Provider>;
}

export const useEspacioEmpresa = () => useContext(Ctx);
