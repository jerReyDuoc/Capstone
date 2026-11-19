"use client";

/**
 * Corrección 18-11 · Selector de tema (Claro · Oscuro · Azul).
 *
 *   variante "grupo":  [☀ Claro][☾ Oscuro][💧 Azul]   grupo de radios: ←/→ cambian, Tab sale del grupo
 *   variante "ciclo":  [☾]                            un botón que pasa al tema siguiente (pantallas angostas)
 *
 * `cuenta="cliente"`: pregunta al BFF quién es la cuenta y guarda/lee su tema (`tema:<usuarioId>`).
 * `cuenta="ninguna"` (portada y páginas públicas, encuestado, panel interno): el tema de este navegador.
 * `compacto`: en el grupo, solo íconos; el nombre queda para lectores de pantalla y en el title.
 * Varios selectores en la misma página se mantienen iguales (EVENTO_TEMA).
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import { usuarioClienteActual } from "@/lib/sesionNavegador";
import { aplicarTema, EVENTO_TEMA, esTema, guardarTema, leerTema, TEMAS, temaSiguiente, type Tema } from "@/lib/tema";

const almacen = () => (typeof window === "undefined" ? null : window.localStorage);

export function SelectorTema({
  cuenta = "ninguna",
  compacto = false,
  variante = "grupo",
}: {
  cuenta?: "cliente" | "ninguna";
  compacto?: boolean;
  variante?: "grupo" | "ciclo";
}) {
  const [tema, setTema] = useState<Tema | null>(null);
  const usuario = useRef<number | null>(null);
  const grupo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTema(leerTema(almacen()));
    const alCambiar = (e: Event) => {
      const t = (e as CustomEvent<unknown>).detail;
      if (esTema(t)) setTema(t);
    };
    window.addEventListener(EVENTO_TEMA, alCambiar);
    const ctrl = new AbortController();
    if (cuenta === "cliente") {
      void usuarioClienteActual(ctrl.signal).then((id) => {
        if (ctrl.signal.aborted || id == null) return;
        usuario.current = id;
        const propio = leerTema(almacen(), id);
        guardarTema(almacen(), propio, id); // la última elección del navegador pasa a ser la de esta cuenta
        aplicarTema(propio);
      });
    }
    return () => {
      ctrl.abort();
      window.removeEventListener(EVENTO_TEMA, alCambiar);
    };
  }, [cuenta]);

  const elegir = (t: Tema) => {
    setTema(t);
    guardarTema(almacen(), t, usuario.current);
    aplicarTema(t);
  };

  const actual = tema ?? "dark";
  const info = TEMAS.find((t) => t.id === actual) ?? TEMAS[1];

  if (variante === "ciclo") {
    const sig = TEMAS.find((t) => t.id === temaSiguiente(actual)) ?? TEMAS[0];
    return (
      <button type="button" className="icon-btn selector-tema-ciclo" onClick={() => elegir(sig.id)}
        aria-label={`Tema ${info.texto.toLowerCase()}. Cambiar a ${sig.texto.toLowerCase()}`}
        title={`Tema ${info.texto.toLowerCase()} · cambiar a ${sig.texto.toLowerCase()}`}>
        <Icon name={info.icono} />
      </button>
    );
  }

  const alTeclear = (e: KeyboardEvent) => {
    const paso = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!paso) return;
    e.preventDefault();
    const i = TEMAS.findIndex((x) => x.id === actual);
    const sig = TEMAS[(i + paso + TEMAS.length) % TEMAS.length];
    elegir(sig.id);
    grupo.current?.querySelector<HTMLElement>(`[data-tema="${sig.id}"]`)?.focus();
  };

  return (
    <div ref={grupo} className={`selector-tema${compacto ? " selector-tema-compacto" : ""}`} role="radiogroup"
      aria-label="Tema de la pantalla" onKeyDown={alTeclear}>
      {TEMAS.map((t) => (
        <button key={t.id} type="button" role="radio" data-tema={t.id} aria-checked={actual === t.id}
          tabIndex={actual === t.id ? 0 : -1} onClick={() => elegir(t.id)} title={`Tema ${t.texto.toLowerCase()}`}>
          <Icon name={t.icono} width={16} height={16} />
          <span className={compacto ? "sr-only" : undefined}>{t.texto}</span>
        </button>
      ))}
    </div>
  );
}
