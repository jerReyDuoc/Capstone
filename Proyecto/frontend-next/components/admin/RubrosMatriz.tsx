"use client";

/**
 * Correcciones 05-11 · "Matriz normativa → Rubros": el admin agrega rubros y corrige sus
 * nombres. A diferencia de controles, brechas y rutas, el rubro no pasa por el borrador: el
 * cambio rige de inmediato (lo elige quien empieza el autodiagnóstico y define con quién se
 * compara en el sector). No se borran: los ya usados sostienen evaluaciones y comparaciones.
 */
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { comoErrorAdmin, type ErrorAdmin } from "@/lib/admin/api";
import { apiRubros, errorRubro, normalizarRubro, RUBRO_MAX, type RubroAdmin } from "@/lib/admin/rubros";
import a from "./admin.module.css";
import s from "./matriz.module.css";

export function RubrosMatriz({
  recarga,
  onAviso,
  onError,
}: {
  /** Cambia cuando se pulsa "Actualizar" en la barra. */
  recarga: number;
  onAviso: (texto: string) => void;
  onError: (e: ErrorAdmin) => void;
}) {
  const id = useId();
  const [rubros, setRubros] = useState<RubroAdmin[] | null>(null);
  const [nombre, setNombre] = useState("");
  const [tocado, setTocado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [editando, setEditando] = useState<{ id: number; nombre: string } | null>(null);

  // El padre puede pasar onError como función nueva en cada render: se lee desde una ref
  // para que la carga no se repita en bucle.
  const alError = useRef(onError);
  alError.current = onError;
  const cargar = useCallback(async () => {
    try {
      setRubros((await apiRubros.listar()).items);
    } catch (e) {
      alError.current(comoErrorAdmin(e));
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar, recarga]);

  const err = tocado ? errorRubro(nombre, rubros ?? []) : null;

  async function agregar(e: FormEvent) {
    e.preventDefault();
    setTocado(true);
    if (errorRubro(nombre, rubros ?? [])) return;
    setEnviando(true);
    try {
      const r = await apiRubros.crear(normalizarRubro(nombre));
      onAviso(`Rubro «${r.nombre}» agregado. Ya aparece para quienes empiezan el autodiagnóstico.`);
      setNombre("");
      setTocado(false);
      await cargar();
    } catch (e2) {
      onError(comoErrorAdmin(e2));
    } finally {
      setEnviando(false);
    }
  }

  async function guardarNombre(e: FormEvent) {
    e.preventDefault();
    if (!editando) return;
    const problema = errorRubro(editando.nombre, rubros ?? [], editando.id);
    if (problema) {
      onError({ status: 422, codigo: "RUBRO_INVALIDO", mensaje: problema });
      return;
    }
    setEnviando(true);
    try {
      const r = await apiRubros.renombrar(editando.id, normalizarRubro(editando.nombre));
      onAviso(`Rubro renombrado a «${r.nombre}».`);
      setEditando(null);
      await cargar();
    } catch (e2) {
      onError(comoErrorAdmin(e2));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--sp-5)" }}>
      <section className="card" aria-labelledby={`${id}-t`}>
        <div className="card-head">
          <div>
            <h2 id={`${id}-t`} className="card-title">Agregar rubro</h2>
            <p className="card-sub">
              Los rubros no pasan por el borrador: el nuevo aparece de inmediato en el autodiagnóstico y en el alta de
              empresas, y se usa para comparar con el sector.
            </p>
          </div>
        </div>
        <form onSubmit={agregar} noValidate className={s.formRubro}>
          <div className={a.campo}>
            <label htmlFor={`${id}-nombre`}>Nombre del rubro</label>
            <input
              id={`${id}-nombre`}
              className={a.control}
              value={nombre}
              maxLength={RUBRO_MAX + 10}
              placeholder="Ej.: Minería"
              onChange={(e) => setNombre(e.target.value)}
              onBlur={() => nombre && setTocado(true)}
              aria-invalid={err ? true : undefined}
              aria-describedby={err ? `${id}-err` : undefined}
            />
            {err ? <p id={`${id}-err`} className={a.errorCampo} role="alert">{err}</p> : null}
          </div>
          <button type="submit" className="btn btn-primary" disabled={enviando} aria-busy={enviando}>
            Agregar rubro
          </button>
        </form>
      </section>

      <section className="card" aria-labelledby={`${id}-l`}>
        <div className="card-head">
          <div>
            <h2 id={`${id}-l`} className="card-title">Rubros{rubros ? ` (${rubros.length})` : ""}</h2>
            <p className="card-sub">No se eliminan: los que ya se usaron sostienen evaluaciones y la comparación del sector.</p>
          </div>
        </div>
        {!rubros ? (
          <p className={a.vacio}>Cargando…</p>
        ) : !rubros.length ? (
          <p className={a.vacio}>Aún no hay rubros. Agrega el primero arriba.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Rubros</caption>
              <thead>
                <tr>
                  <th scope="col">Rubro</th>
                  <th scope="col" className="num">Evaluaciones</th>
                  <th scope="col" className="num">Empresas cliente</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {rubros.map((r) => (
                  <tr key={r.id}>
                    <th scope="row">
                      {editando?.id === r.id ? (
                        <form onSubmit={guardarNombre} className={s.formRubroFila}>
                          <label className="sr-only" htmlFor={`${id}-r${r.id}`}>Nuevo nombre de {r.nombre}</label>
                          <input
                            id={`${id}-r${r.id}`}
                            className={a.control}
                            value={editando.nombre}
                            maxLength={RUBRO_MAX + 10}
                            autoFocus
                            onChange={(e) => setEditando({ id: r.id, nombre: e.target.value })}
                            onKeyDown={(e) => e.key === "Escape" && setEditando(null)}
                          />
                          <button type="submit" className="btn btn-primary btn-sm" disabled={enviando}>Guardar</button>
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditando(null)}>Cancelar</button>
                        </form>
                      ) : (
                        r.nombre
                      )}
                    </th>
                    <td className="num">{r.evaluaciones}</td>
                    <td className="num">{r.empresas}</td>
                    <td>
                      {editando?.id === r.id ? null : (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditando({ id: r.id, nombre: r.nombre })}>
                          Renombrar<span className="sr-only"> {r.nombre}</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
