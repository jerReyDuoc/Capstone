/**
 * /empresa/asistente — Ya no es una página propia: el asistente de registro vive dentro del mapa de datos y del
 * registro de actividades. Los enlaces antiguos llevan al mapa con el asistente abierto.
 */
import { redirect } from "next/navigation";

export default function PaginaAsistente() {
  redirect("/empresa/mapa-datos?asistente=1");
}
