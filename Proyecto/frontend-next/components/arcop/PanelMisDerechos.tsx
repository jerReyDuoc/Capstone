"use client";

/**
 * HU-32 · /panel/mis-derechos según quién mira (lo detecta PanelProvider por las cookies):
 *   - usuario temporal con sesión (N.º de evaluación + clave) → sus derechos ARCOP;
 *   - usuario definitivo → su página en el espacio de la empresa (/empresa/mis-derechos);
 *   - sin sesión → explica cómo entrar (no hay datos que mostrar).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { usePanel } from "@/hooks/usePanel";
import { Icon } from "@/components/ui/Icon";
import { DerechosTitular } from "./DerechosTitular";

export function PanelMisDerechos() {
  const { modo, evaluacionId } = usePanel();
  const router = useRouter();

  useEffect(() => {
    if (modo === "cliente") router.replace("/empresa/mis-derechos");
  }, [modo, router]);

  if (modo === "encuestado") return <DerechosTitular perfil="encuestado" evaluacionId={evaluacionId} />;
  if (modo === "detectando" || modo === "cliente") {
    return <div className="skeleton" style={{ height: 320 }} role="status" aria-label="Cargando tus derechos" />;
  }
  return (
    <div className="state" role="status">
      <Icon name="escudo" width={32} height={32} style={{ color: "var(--accent)" }} />
      <h2>Ingresa para ejercer tus derechos</h2>
      <p>
        Usa el número de evaluación y la clave que recibiste al comenzar el autodiagnóstico. Si tienes una cuenta de
        empresa, ingresa con tu correo y contraseña.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "center" }}>
        <Link href="/mis-derechos" className="btn btn-primary" prefetch={false}>
          Ingresar con mi clave
          <Icon name="flecha" />
        </Link>
        <Link href="/ingresar" className="btn btn-ghost" prefetch={false}>
          Soy cliente
        </Link>
      </div>
    </div>
  );
}
