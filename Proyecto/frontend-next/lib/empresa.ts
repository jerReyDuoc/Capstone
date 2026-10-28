/**
 * HU-28 · Espacio de la empresa del usuario definitivo (navegador → /bff/cliente/api/*).
 * Refleja GET /api/cliente/empresa (app/api/routes/cliente.py).
 */
import { pedir } from "@/lib/encuesta/cliente";

export interface EvaluacionEmpresa {
  id: number;
  estado_progreso: string | null;
  completada: boolean;
  fecha_inicio: string | null;
  fecha_migracion: string | null;
  puntaje_general: number | null;
}

export interface EspacioEmpresaApi {
  usuario: { nombre: string; email: string };
  empresa: {
    id: number;
    razon_social: string;
    rut: string;
    rubro: string | null;
    fecha_inicio_contrato: string;
    fecha_termino_contrato: string;
    contrato_vigente: boolean;
    contrato?: ContratoApi;
  };
  evaluaciones: EvaluacionEmpresa[];
}

/** HU-30 · situación del contrato (app/domain/contrato.py). */
export type SituacionContrato = "pendiente" | "vigente" | "suspendido" | "vencido" | "terminado" | "finalizado";

export interface ContratoApi {
  estado: "activo" | "suspendido" | "terminado";
  situacion: SituacionContrato;
  fecha_inicio_contrato: string;
  fecha_termino_contrato: string;
  servicio_habilitado: boolean;
  documentos_disponibles: boolean;
  en_plazo_de_gracia: boolean;
  documentos_disponibles_hasta: string | null;
  mensaje: string;
}

/** HU-30 · GET /api/cliente/contrato: lo que el usuario puede hacer sin servicio pagado. */
export interface ContratoClienteApi {
  empresa: { id: number; razon_social: string };
  contrato: ContratoApi;
  documentos: {
    constancias: { ruta_id: number; modulo: string; fecha_completado: string | null; codigo: string }[];
    evaluaciones: { id: number; completada: boolean }[];
  };
  arcop: { disponible: boolean };
}

export const BASE_CLIENTE = "/bff/cliente/api";

export const cargarEspacioEmpresa = () => pedir<EspacioEmpresaApi>(`${BASE_CLIENTE}/cliente/empresa`);
export const cargarContratoCliente = () => pedir<ContratoClienteApi>(`${BASE_CLIENTE}/cliente/contrato`);

/** HU-30: códigos con que el backend corta el servicio pagado. */
export const SIN_SERVICIO = new Set(["CONTRATO_NO_VIGENTE", "PLAZO_GRACIA_VENCIDO"]);

/** Días que faltan para el término del contrato (negativo si ya terminó). */
export function diasParaTermino(terminoISO: string, hoy = new Date()): number {
  const [a, m, d] = terminoISO.slice(0, 10).split("-").map(Number);
  const fin = Date.UTC(a, m - 1, d);
  const inicioHoy = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((fin - inicioHoy) / 86_400_000);
}

/** "2026-10-27" → "27-10-2026" sin pasar por la zona horaria del navegador. */
export function fechaCorta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}-${m}-${a}` : "—";
}
