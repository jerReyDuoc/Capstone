/**
 * Auditoría UX 16-11 · Fase 6.3: sigla con su nombre completo accesible.
 *  - Con el mouse o el FOCO de teclado se ve un globo con el nombre completo (no solo `title`).
 *  - Los lectores de pantalla leen el nombre completo (texto oculto a la vista).
 *  - `primera`: muestra "Nombre completo (SIGLA)", para la primera aparición en una pantalla.
 */
import { SIGLAS, conNombreCompleto, type CodigoSigla } from "@/lib/siglas";

export function Sigla({ s, primera = false }: { s: CodigoSigla; primera?: boolean }) {
  if (primera) return <>{conNombreCompleto(s)}</>;
  return (
    <span className="sigla" tabIndex={0}>
      <abbr title={SIGLAS[s]} aria-hidden="true">{s}</abbr>
      <span className="sr-only">{s} ({SIGLAS[s]})</span>
      <span className="sigla-globo" aria-hidden="true">{SIGLAS[s]}</span>
    </span>
  );
}
