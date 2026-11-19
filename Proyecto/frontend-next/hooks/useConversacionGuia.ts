"use client";

/**
 * Corrección 18-11 · Estado de la conversación con el asistente de registro, de UNA cuenta.
 *
 * Lo usan el panel flotante (mapa de datos y registro) y la sección propia /empresa/asistente. Comparten la
 * conversación a través del sessionStorage, siempre bajo la clave del usuario con sesión:
 *   1. al montarse pregunta al BFF quién es la cuenta (`usuarioClienteActual`);
 *   2. recién entonces lee SU conversación; mientras no se sabe, no se lee, no se guarda ni se envía;
 *   3. si la respuesta de una pregunta llega cuando la cuenta ya cambió, se descarta (no se mezcla).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cargarResumenGuia, guardarConversacion, leerConversacion, MAX_CARACTERES_GUIA, mensajeGuia, nuevoId,
  preguntarGuia, validarPregunta, type CuotaGuia, type MensajeGuia, type ResumenGuia, type VistaGuia,
} from "@/lib/guiaRegistro";
import { usuarioClienteActual } from "@/lib/sesionNavegador";

const almacen = () => (typeof window === "undefined" ? null : window.sessionStorage);

export function useConversacionGuia(vista: VistaGuia) {
  const router = useRouter();
  const [usuarioId, setUsuarioId] = useState<number | null>(null);
  const dueno = useRef<number | null>(null);
  const [resumen, setResumen] = useState<ResumenGuia | null>(null);
  const [errorCarga, setErrorCarga] = useState("");
  const [mensajes, setMensajes] = useState<MensajeGuia[]>([]);
  const [cuota, setCuota] = useState<CuotaGuia | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  const aLogin = useCallback(() => router.replace("/ingresar?motivo=sesion"), [router]);

  const cargar = useCallback(async () => {
    setErrorCarga("");
    try {
      const r = await cargarResumenGuia();
      setResumen(r);
      setCuota(r.ia.cuota);
    } catch (e) {
      if (e instanceof ErrorBff && e.status === 401) return aLogin();
      setErrorCarga(mensajeGuia(e));
    }
  }, [aLogin]);

  // Quién es la cuenta → su conversación (y nada de otra)
  useEffect(() => {
    const ctrl = new AbortController();
    void usuarioClienteActual(ctrl.signal).then((id) => {
      if (ctrl.signal.aborted) return;
      if (id == null) return aLogin();
      dueno.current = id;
      setMensajes(leerConversacion(almacen(), id));
      setUsuarioId(id);
    });
    void cargar();
    return () => ctrl.abort();
  }, [cargar, aLogin]);

  useEffect(() => {
    guardarConversacion(almacen(), usuarioId, mensajes);
  }, [usuarioId, mensajes]);

  const listo = usuarioId != null;

  /** Devuelve true si se envió (el composer se limpia). */
  const enviar = async (texto: string): Promise<boolean> => {
    if (enviando || !listo) return false;
    const v = validarPregunta(texto, resumen?.limites.max_caracteres ?? MAX_CARACTERES_GUIA);
    if (!v.ok) {
      setError(v.motivo);
      return false;
    }
    setError("");
    setEnviando(true);
    const de = usuarioId;
    const anteriores = mensajes;
    const propio: MensajeGuia = { id: nuevoId(), rol: "usuario", texto: v.texto };
    setMensajes([...anteriores, propio]);
    try {
      const r = await preguntarGuia(v.texto, vista, anteriores);
      if (dueno.current !== de) return false; // cambió la cuenta mientras se respondía
      setCuota(r.cuota);
      setMensajes((m) => [
        ...m.map((x) => (x.id === propio.id && r.bloqueado ? { ...x, bloqueado: true } : x)),
        { id: nuevoId(), rol: "guia", texto: r.respuesta, sugerencias: r.sugerencias },
      ]);
      return true;
    } catch (e) {
      if (e instanceof ErrorBff && e.status === 401) {
        aLogin();
        return false;
      }
      if (e instanceof ErrorBff && e.info.codigo === "ASISTENTE_RAFAGA") {
        // TEMPORAL (verificación del falso 429, 18-11): quitar cuando se confirme el arreglo en staging.
        console.debug("[RAFAGA-DEBUG] 429 ASISTENTE_RAFAGA", {
          usuarioId: de, mensajesEnPantalla: anteriores.length, reintentarEnS: e.info.reintentarEnS ?? null,
        });
      }
      setMensajes((m) => m.filter((x) => x.id !== propio.id));
      setError(mensajeGuia(e));
      return false;
    } finally {
      setEnviando(false);
    }
  };

  const nuevaConversacion = () => {
    setMensajes([]);
    setError("");
  };

  return {
    listo, resumen, errorCarga, cargar, mensajes, cuota, enviando, error, enviar, nuevaConversacion,
    limpiarError: () => setError(""),
  };
}

export type ConversacionGuia = ReturnType<typeof useConversacionGuia>;
