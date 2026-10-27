/**
 * HU-28 · Inicio y cierre de sesión con email y contraseña, y recuperación de contraseña
 * (lógica pura, compartida por el navegador y el BFF; probada en tests/).
 *
 * Dos tipos de cuenta usan contraseña:
 *   - "cliente": usuario definitivo de una empresa cliente → /ingresar, entra a /empresa;
 *   - "admin":   administrador de Therion Labs             → /admin/login, entra a /admin.
 */
export type TipoCuenta = "cliente" | "admin";

export const LOGIN_DE: Record<TipoCuenta, string> = { cliente: "/ingresar", admin: "/admin/login" };
export const INICIO_DE: Record<TipoCuenta, string> = { cliente: "/empresa", admin: "/admin/clientes" };

export function tipoCuenta(valor: unknown): TipoCuenta {
  return valor === "admin" ? "admin" : "cliente";
}

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;

export function emailValido(valor: string): boolean {
  return valor.length <= 200 && EMAIL.test(valor.trim());
}

/** Motivos que una página de login puede recibir en ?motivo= (cualquier otro se ignora). */
export type MotivoLogin = "sesion" | "salida" | "restablecida" | "activada";

export function motivoLogin(valor: unknown): MotivoLogin | undefined {
  return valor === "sesion" || valor === "salida" || valor === "restablecida" || valor === "activada" ? valor : undefined;
}

export const TEXTO_MOTIVO: Record<MotivoLogin, string> = {
  sesion: "Tu sesión terminó o no existe. Inicia sesión para continuar.",
  salida: "Cerraste tu sesión.",
  restablecida: "Tu contraseña quedó actualizada. Inicia sesión con la nueva.",
  activada: "Tu cuenta quedó activa. Inicia sesión con tu correo y tu contraseña.",
};

/**
 * Mensaje del formulario de login según el código del BFF. Nunca distingue "el correo no
 * existe" de "la contraseña es incorrecta" (HU-28 criterio 3).
 */
export function mensajeLogin(codigo: string, reintentarEnS?: number): string {
  switch (codigo) {
    case "CREDENCIALES_INVALIDAS":
      return "Correo o contraseña incorrectos.";
    case "DEMASIADOS_INTENTOS": {
      const min = reintentarEnS ? Math.max(1, Math.ceil(reintentarEnS / 60)) : null;
      return min
        ? `Demasiados intentos fallidos. Por seguridad, espera ${min} ${min === 1 ? "minuto" : "minutos"} antes de volver a intentarlo.`
        : "Demasiados intentos fallidos. Espera unos minutos antes de volver a intentarlo.";
    }
    case "CONTRATO_NO_VIGENTE":
      return "El contrato de tu empresa no está vigente. Contacta a Therion Labs.";
    case "SIN_CONEXION":
    case "LIMITADOR_NO_DISPONIBLE":
      return "No pudimos conectar con el servidor. Inténtalo de nuevo en unos minutos.";
    case "DATOS_INVALIDOS":
      return "Ingresa tu correo y tu contraseña.";
    default:
      return "No pudimos iniciar tu sesión. Inténtalo de nuevo.";
  }
}
