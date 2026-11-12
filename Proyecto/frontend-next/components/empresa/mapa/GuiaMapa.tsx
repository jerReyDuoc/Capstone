"use client";

/**
 * Guía para armar el mapa: los pasos recomendados, cuáles ya están listos (se calculan con el mapa
 * actual) y un botón para hacer el siguiente. Se puede ocultar; la preferencia se recuerda en este
 * navegador.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { siguientePaso, type AccionGuia, type PasoGuia } from "@/lib/guiaMapa";
import s from "./mapa.module.css";

const CLAVE = "complianceia.mapa.guia_oculta";
const ICONO: Record<PasoGuia["id"], IconName> = {
  internos: "sistemaApp", terceros: "empresa", flujos: "flujo", completar: "lista", confirmar: "check", riesgos: "brechas", rat: "libro",
};

export function GuiaMapa({ pasos, onAccion }: { pasos: PasoGuia[]; onAccion: (a: AccionGuia) => void }) {
  const evaluables = pasos.filter((p) => p.id !== "rat");
  const listos = evaluables.filter((p) => p.listo).length;
  const [oculta, setOculta] = useState(true);

  useEffect(() => {
    // Compacta (una línea) para que el mapa quede arriba; abierta si recién empiezas o si la abriste antes
    try {
      const guardada = window.localStorage.getItem(CLAVE);
      setOculta(listos >= 2 && guardada !== "0");
    } catch {
      setOculta(listos >= 2);
    }
    // Solo al montar: después manda lo que elija el usuario
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const alternar = () => {
    setOculta((v) => {
      try {
        window.localStorage.setItem(CLAVE, v ? "0" : "1");
      } catch {
        /* sin almacenamiento */
      }
      return !v;
    });
  };
  const siguiente = siguientePaso(pasos);

  return (
    <section className={s.guia} aria-labelledby="titulo-guia" data-oculta={oculta || undefined}>
      <div className={s.guiaCabeza}>
        <span className={s.guiaIcono} aria-hidden="true"><Icon name="diana" /></span>
        <div className={s.guiaTitulos}>
          <h2 id="titulo-guia">Cómo armar tu mapa</h2>
          <p>
            {listos === evaluables.length
              ? "¡Tu mapa está completo! Mantenlo al día cuando cambien tus sistemas o proveedores."
              : <>Siguiente paso: <strong>{siguiente.titulo.toLowerCase()}</strong>.</>}
          </p>
        </div>
        <div className={s.guiaProgreso} aria-label={`${listos} de ${evaluables.length} pasos listos`}>
          <span>{listos}/{evaluables.length}</span>
          <div className={s.barra} aria-hidden="true"><span style={{ width: `${(listos / evaluables.length) * 100}%` }} /></div>
        </div>
        {oculta && siguiente.accion && siguiente.accion.tipo !== "ir_registro" && !siguiente.listo ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onAccion(siguiente.accion!.tipo)}>
            {siguiente.accion.texto}
          </button>
        ) : null}
        <button type="button" className="btn btn-ghost btn-sm" onClick={alternar} aria-expanded={!oculta} aria-controls="pasos-guia">
          {oculta ? "Ver todos los pasos" : "Ocultar"}
          <Icon name={oculta ? "flechaAbajo" : "flechaArriba"} />
        </button>
      </div>
      {!oculta ? (
        <ol id="pasos-guia" className={s.guiaPasos}>
          {pasos.map((p, i) => (
            <li key={p.id} className={s.guiaPaso} data-listo={p.listo || undefined} data-siguiente={p.id === siguiente.id || undefined}>
              <span className={s.guiaNumero} aria-hidden="true">{p.listo ? <Icon name="check" /> : <Icon name={ICONO[p.id]} />}</span>
              <span className="sr-only">Paso {i + 1}.</span>
              <div className={s.guiaPasoTexto}>
                <strong>{p.titulo}</strong>
                <span>{p.texto}</span>
              </div>
              {p.accion ? (
                p.accion.tipo === "ir_registro" ? (
                  <Link href="/empresa/registro-actividades" className="btn btn-ghost btn-sm">{p.accion.texto}<Icon name="flecha" /></Link>
                ) : (
                  <button type="button" className={`btn btn-sm ${p.id === siguiente.id ? "btn-primary" : "btn-ghost"}`} onClick={() => onAccion(p.accion!.tipo)}>
                    {p.accion.texto}
                  </button>
                )
              ) : null}
              <span className="sr-only">{p.listo ? "Listo" : "Pendiente"}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
