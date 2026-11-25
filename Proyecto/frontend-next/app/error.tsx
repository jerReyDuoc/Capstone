"use client";

/** Error inesperado de una página: mensaje en español y reintento, sin mostrar detalles técnicos. */
export default function ErrorPagina({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main style={{ maxWidth: 520, margin: "15vh auto", padding: "0 var(--sp-4, 16px)", textAlign: "center" }}>
      <h1 style={{ fontSize: "var(--fs-xl, 1.5rem)", marginBottom: 12 }}>Algo salió mal</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 20 }}>
        No pudimos cargar esta página. Puedes intentarlo de nuevo; si el problema sigue, vuelve al inicio.
      </p>
      <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
        <button type="button" className="btn btn-primary" onClick={() => reset()}>Reintentar</button>
        <a href="/" className="btn btn-ghost">Ir al inicio</a>
      </div>
    </main>
  );
}
