"""
HU-38 · El registro de actividades conectado con la evaluación, las brechas y los borradores.

Como Oficial de Cumplimiento, quiero que las actividades de mayor riesgo del RAT se identifiquen solas
y se conecten con mi evaluación, mis brechas y mis borradores, para que el registro no sea un documento
aislado y alimente el resto de mi cumplimiento.

  C1  Cada actividad recibe un nivel de riesgo con reglas explicables (app/domain/rat/riesgos.py); las de
      mayor riesgo forman la matriz de riesgos (Decreto 662, art. 3 letra e) y se recomienda una
      evaluación de impacto. Aquí: `matriz()` (la misma que el informe, con la versión vigente).
  C2  La PIA y el aviso de privacidad de los borradores (HU-16) toman las actividades de alto riesgo y las
      finalidades y bases de licitud del registro: `contexto_borradores()` → borradores/registro.py.
  C3  Un registro VIGENTE Y COMPLETO cuenta como evidencia de los controles de protección de datos de la
      evaluación más reciente de la empresa (app/domain/rat/cumplimiento.py: aportes) y actualiza el
      estado, la brecha y el puntaje igual que una evidencia de remediación (HU-17): una fila en
      `evidencias` (origen "rat", sin archivo), la brecha sincronizada y el resumen recalculado
      control por control (la evolución del puntaje lo muestra). NUNCA baja un control. Se aplica solo al
      dejar vigente una actividad y a pedido (`aplicar`).
  C4  `resumen()`: estado del mapa y del registro, la matriz de mayor riesgo, las brechas que genera el
      registro (sin base de licitud, sin plazo, transferencia sin garantía, envío sin actividad) con su
      ruta de remediación (módulo formativo del plan con su avance, HU-12/HU-26, y el control a
      re-evaluar, HU-17) y lo que el registro aporta a la evaluación.

Solo el usuario definitivo con contrato vigente (las rutas usan empresa_con_servicio). Todo cambio de un
control queda en el audit_log (rat.evidencia_aplicada) sin nombres ni textos del registro.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import ORIGEN_RAT, EstadoValidacion, Evidencia
from app.domain.models.formacion import AvanceFormativo
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.rat import RatActividad
from app.domain.models.respuesta import FuenteClasificacion, Respuesta
from app.domain.rat import analisis, cobertura, riesgos
from app.domain.rat import catalogo as cat
from app.domain.rat import cumplimiento as cu
from app.domain.rat.modelo import completar
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

NOMBRE_EVIDENCIA = "Registro de actividades de tratamiento (vigente)"
MIME_EVIDENCIA = "application/json"
ETIQUETA_ESTADO = {"cumplido": "Cumplido", "parcialmente_cumplido": "Parcialmente cumplido",
                   "no_cumplido": "No cumplido", "requiere_revision": "En revisión", "no_aplica": "No aplica"}
CONTROLES_REGISTRO = ("DAT-001", "DAT-003", "DAT-005", "DAT-007", "DAT-008", "DAT-009")


def huella_registro(actividades: list[cu.ActividadRegistro]) -> str:
    """Qué afirmaba el registro cuando se usó como evidencia (ids, estados y contenido; sin fecha)."""
    partes = [[a.id, a.estado, a.contenido, {k: a.derivados.get(k) for k in ("tipos_datos", "terceros",
                                                                            "transferencias")}]
              for a in sorted(actividades, key=lambda x: x.id)]
    texto = json.dumps(partes, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class CumplimientoRegistro:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.bitacora = BitacoraRepository(db)

    # ================================================================ lectura
    async def _registro(self):
        from app.application.use_cases.registro_actividades import RegistroActividadesCasos

        version_mapa, elementos, flujos = await RegistroActividadesCasos(self.db, self.cliente)._mapa()
        filas = list((await self.db.execute(
            select(RatActividad).where(RatActividad.empresa_id == self.empresa_id, RatActividad.estado != cat.ARCHIVADA)
            .order_by(RatActividad.nombre, RatActividad.id))).scalars().all())
        actividades = []
        for f in filas:
            deriv = analisis.derivados(f.contenido, elementos, flujos)
            actividades.append(cu.ActividadRegistro(
                id=f.id, nombre=f.nombre, estado=f.estado, contenido=completar(f.contenido), derivados=deriv,
                completitud=analisis.completitud(f.contenido, deriv), motivos_revision=tuple(f.motivos_revision or [])))
        sin_actividad = cobertura.flujos_sin_actividad(
            flujos, [{"estado": f.estado, "contenido": f.contenido} for f in filas])
        por_id = {e.id: e for e in elementos}
        flujos_libres = [{"id": x.id, "nombre": analisis.nombre_flujo(x, por_id)} for x in sin_actividad]
        estado = cu.estado_registro(actividades, len(flujos_libres), bool(elementos))
        return version_mapa, elementos, flujos, actividades, flujos_libres, estado

    async def _evaluacion(self) -> Evaluacion | None:
        """La evaluación COMPLETADA más reciente de la empresa (la misma regla del panel y la formación)."""
        from app.application.use_cases.historial_empresa import evaluacion_mas_reciente

        ev_id = await evaluacion_mas_reciente(self.db, self.empresa_id)
        ev = await self.db.get(Evaluacion, ev_id) if ev_id else None
        return ev if ev is not None and ev.esta_cerrada and ev.empresa_id == self.empresa_id else None

    async def _controles(self, codigos) -> dict[str, MatrizControl]:
        filas = (await self.db.execute(
            select(MatrizControl).where(MatrizControl.codigo_control.in_(sorted(set(codigos))))
            .order_by(MatrizControl.id_control))).scalars().all()
        salida: dict[str, MatrizControl] = {}
        for c in filas:
            # Con la matriz versionada puede haber más de una fila con el código: manda la activa con brecha
            previo = salida.get(c.codigo_control)
            if previo is None or (not previo.catalogo_brechas_id_brecha and c.catalogo_brechas_id_brecha):
                salida[c.codigo_control] = c
        return salida

    async def _respuestas(self, evaluacion_id: int, codigos) -> dict[str, tuple[Respuesta, MatrizControl]]:
        filas = (await self.db.execute(
            select(Respuesta, MatrizControl)
            .join(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .where(Respuesta.evaluacion_id == evaluacion_id, MatrizControl.codigo_control.in_(sorted(set(codigos))))
            .order_by(Respuesta.id))).all()
        return {c.codigo_control: (r, c) for r, c in filas}

    async def _rutas(self, controles: dict[str, MatrizControl]) -> dict[str, dict]:
        """Módulo formativo del plan (HU-12) que trata cada control y el avance de la empresa (HU-26)."""
        rutas: dict[str, object] = {}
        for codigo, c in controles.items():
            ruta = c.brecha.ruta_formativa if c.brecha is not None else None
            if ruta is not None:
                rutas[codigo] = ruta
        if not rutas:
            return {}
        avances = {a.ruta_formativa_id: a for a in (await self.db.execute(
            select(AvanceFormativo).where(AvanceFormativo.empresa_id == self.empresa_id,
                                          AvanceFormativo.ruta_formativa_id.in_([r.id for r in rutas.values()]))
        )).scalars().all()}
        salida = {}
        for codigo, r in rutas.items():
            a = avances.get(r.id)
            salida[codigo] = {"id": r.id, "nombre": r.nombre, "nivel": r.nivel, "horas": r.horas,
                              "estado": a.estado if a is not None else "no_iniciado"}
        return salida

    # ================================================================ C1 · matriz de riesgos
    async def _informe(self):
        from app.application.use_cases.informe_rat import InformeRatCasos

        return await InformeRatCasos(self.db, self.cliente).armar()

    @staticmethod
    def _riesgo_dict(a) -> dict:
        r = a.riesgo
        return {
            "actividad_id": a.id, "nombre": a.nombre, "estado": a.estado, "estado_nombre": a.estado_nombre,
            "version": a.version, "origen": a.origen, "nivel": r.nivel, "puntaje": r.puntaje,
            "probabilidad": r.probabilidad, "impacto": r.impacto, "requiere_pia": r.requiere_pia,
            "motivos_pia": list(r.motivos_pia), "factores": [f.titulo for f in r.factores],
            "tratamientos": r.tratamientos[:3],
        }

    def _matriz(self, inf) -> dict:
        acts = [a for a in inf.actividades if a.riesgo is not None]
        mayores = [a for a in sorted(acts, key=lambda x: (-x.riesgo.puntaje, -x.riesgo.impacto, x.nombre.lower()))
                   if a.riesgo.mayor_riesgo]
        return {
            "referencia": riesgos.REFERENCIA_MATRIZ, "metodologia": riesgos.METODOLOGIA,
            "metodologia_pia": riesgos.METODOLOGIA_PIA,
            "por_nivel": riesgos.conteo_niveles([a.riesgo for a in acts]),
            "mayor_riesgo": [self._riesgo_dict(a) for a in mayores],
            "pia_recomendadas": sum(1 for a in acts if a.riesgo.requiere_pia),
            "mapa_calor": riesgos.mapa_calor([a.riesgo for a in acts]),
        }

    async def matriz(self) -> dict:
        return self._matriz(await self._informe())

    # ================================================================ C3 · aportes a la evaluación
    async def _vista_evidencia(self, estado: cu.EstadoRegistro, actividades, ev: Evaluacion | None) -> dict:
        aportes = cu.aportes(estado, actividades)
        base = {"evaluacion_id": ev.id if ev else None, "aplicable": estado.vigente_completo,
                "faltantes": estado.faltantes(), "controles": [], "por_mejorar": 0, "puntaje_general": None}
        if ev is None:
            return base
        from app.application.use_cases.remediacion import puntaje_general_actual

        base["puntaje_general"] = await puntaje_general_actual(self.db, ev.id)
        respuestas = await self._respuestas(ev.id, CONTROLES_REGISTRO)
        por_control = {a.control: a for a in aportes}
        controles = []
        for codigo in CONTROLES_REGISTRO:
            par = respuestas.get(codigo)
            if par is None:
                continue                      # el control no aplica a esta evaluación (filtro)
            r, c = par
            actual = r.estado_clasificacion_final or r.estado_clasificacion
            ap = por_control.get(codigo)
            controles.append({
                "respuesta_id": r.id, "obligacion": c.obligacion, "estado_actual": actual,
                "estado_actual_nombre": ETIQUETA_ESTADO.get(actual or "", actual),
                "estado_aportado": ap.estado if ap else None,
                "estado_aportado_nombre": ETIQUETA_ESTADO.get(ap.estado) if ap else None,
                "motivo": ap.motivo if ap else None,
                "mejora": bool(ap and cu.mejora(actual, ap.estado)),
                "respaldado_por_registro": r.fuente_clasificacion == FuenteClasificacion.RAT.value,
            })
        base["controles"] = controles
        base["por_mejorar"] = sum(1 for x in controles if x["mejora"])
        return base

    async def aplicar(self, origen: str = "manual") -> dict:
        """
        C3: usa el registro vigente y completo como evidencia en la evaluación completada más reciente.
        Solo MEJORA controles; cada control mejorado deja su evidencia y su recálculo del puntaje.
        `origen`: "manual" (botón) | "aprobacion" (al dejar vigente una actividad).
        """
        from app.application.use_cases.generate_resumen import GenerateResumenUseCase
        from app.application.use_cases.remediacion import puntaje_general_actual

        _, _, _, actividades, _, estado = await self._registro()
        ev = await self._evaluacion()
        if ev is None:
            return {"aplicado": False, "motivo": "sin_evaluacion", "controles": [],
                    "mensaje": "Tu empresa aún no tiene una evaluación completada donde usar el registro como evidencia."}
        if not estado.vigente_completo:
            return {"aplicado": False, "motivo": "registro_incompleto", "controles": [], "faltantes": estado.faltantes(),
                    "mensaje": "Para usar el registro como evidencia, déjalo vigente y completo."}
        aportes = cu.aportes(estado, actividades)
        respuestas = await self._respuestas(ev.id, [a.control for a in aportes])
        huella = huella_registro(actividades)
        hoy = date.today()
        mejorados = []
        puntaje_inicial = await puntaje_general_actual(self.db, ev.id)
        for ap in aportes:
            par = respuestas.get(ap.control)
            if par is None:
                continue
            r, control = par
            actual = r.estado_clasificacion_final or r.estado_clasificacion
            if not cu.mejora(actual, ap.estado):
                continue
            antes = await puntaje_general_actual(self.db, ev.id)
            r.estado_clasificacion_final = ap.estado
            r.fuente_clasificacion = FuenteClasificacion.RAT.value
            r.confianza_clasificacion = None
            r.fecha_validacion = hoy
            r.sincronizar_brecha(control)
            evidencia = Evidencia(
                respuesta_id=r.id, nombre_archivo=NOMBRE_EVIDENCIA, storage_path="", mime_type=MIME_EVIDENCIA,
                hash_archivo=huella, estado_validacion=EstadoValidacion.VALIDATED.value, fecha_subida=hoy,
                fecha_procesada=hoy, origen=ORIGEN_RAT, estado_declarado=ap.estado, estado_previo=actual,
                estado_resultante=ap.estado, justificacion_llm=ap.motivo, puntaje_previo=antes,
                datos_extraidos={"actividades": len(actividades), "huella_registro": huella, "origen": origen})
            self.db.add(evidencia)
            await self.db.flush()
            await GenerateResumenUseCase(self.db).execute(ev.id)          # recalcula puntaje y radar (commit)
            despues = await puntaje_general_actual(self.db, ev.id)
            evidencia.puntaje_resultante = despues
            mejorados.append({"control": ap.control, "respuesta_id": r.id, "evidencia_id": evidencia.id_evidencia,
                              "estado_previo": actual, "estado_resultante": ap.estado, "obligacion": control.obligacion,
                              "puntaje_previo": antes, "puntaje_resultante": despues})
        if mejorados:
            self.bitacora.registrar(
                accion=Accion.RAT_EVIDENCIA_APLICADA, entidad="evaluacion", entidad_id=ev.id, actor=self.actor,
                detalle={"origen": origen, "actividades": len(actividades), "huella": huella[:16],
                         "controles": [{"control": m["control"], "estado_previo": m["estado_previo"],
                                        "estado_resultante": m["estado_resultante"]} for m in mejorados],
                         "puntaje_previo": puntaje_inicial, "puntaje_resultante": mejorados[-1]["puntaje_resultante"]})
            await self.db.commit()
            if settings.BENCHMARK_AL_COMPLETAR:
                try:
                    from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase

                    await UpdateBenchmarkUseCase(self.db).execute()
                except Exception:  # noqa: BLE001 - lo repara el cron de las 02:00
                    await self.db.rollback()
        n = len(mejorados)
        return {
            "aplicado": bool(mejorados), "motivo": None if mejorados else "sin_mejoras", "evaluacion_id": ev.id,
            "controles": [{k: v for k, v in m.items() if k != "control"} for m in mejorados],
            "puntaje_previo": puntaje_inicial,
            "puntaje_resultante": mejorados[-1]["puntaje_resultante"] if mejorados else puntaje_inicial,
            "mensaje": (f"Tu registro mejoró {n} control{'es' if n > 1 else ''} de tu evaluación y se recalculó tu "
                        "puntaje." if mejorados else
                        "Tu evaluación ya refleja todo lo que demuestra el registro: no hubo controles por mejorar."),
        }

    # ================================================================ C4 · espacio de la empresa
    async def resumen(self) -> dict:
        version_mapa, elementos, flujos, actividades, flujos_libres, estado = await self._registro()
        ev = await self._evaluacion()
        inf = await self._informe()
        brechas = cu.brechas(actividades, flujos_libres)
        controles = await self._controles({b["control"] for b in brechas} | set(CONTROLES_REGISTRO))
        rutas = await self._rutas(controles)
        respuestas = await self._respuestas(ev.id, {b["control"] for b in brechas}) if ev and brechas else {}
        for b in brechas:
            c = controles.get(b["control"])
            par = respuestas.get(b["control"])
            actual = (par[0].estado_clasificacion_final or par[0].estado_clasificacion) if par else None
            b["obligacion"] = c.obligacion if c else None
            b["ruta"] = rutas.get(b["control"])
            b["remediacion"] = {"evaluacion_id": ev.id, "respuesta_id": par[0].id, "estado": actual,
                                "estado_nombre": ETIQUETA_ESTADO.get(actual or "", actual),
                                "abierta": actual in ("no_cumplido", "parcialmente_cumplido", "requiere_revision")} \
                if par else None
            b.pop("control")                  # código interno: no sale de la API
        porcentajes = [a.completitud["porcentaje"] for a in actividades]
        matriz = self._matriz(inf)
        return {
            "mapa": {"iniciado": estado.mapa_iniciado, "version": version_mapa, "elementos": len(elementos),
                     "flujos": len(flujos), "flujos_sin_actividad": len(flujos_libres)},
            "registro": {
                "activas": estado.activas, "vigentes": estado.vigentes, "completas": estado.completas,
                "en_revision": estado.en_revision, "borradores": estado.borradores, "por_revisar": estado.por_revisar,
                "completitud": analisis.completitud_global(porcentajes)["porcentaje"],
                "vigente_completo": estado.vigente_completo, "faltantes": estado.faltantes(),
            },
            "riesgos": matriz,
            "brechas": brechas,
            "evidencia": await self._vista_evidencia(estado, actividades, ev),
            "borradores": {
                "pia": {"recomendada": matriz["pia_recomendadas"] > 0, "actividades": matriz["pia_recomendadas"]},
                "aviso": {"finalidades": sum(len(a.contenido.get("finalidades") or []) for a in actividades)},
            },
        }


async def aplicar_tras_aprobar(db: AsyncSession, cliente) -> dict | None:
    """
    C3 automático: al dejar vigente una actividad se intenta usar el registro como evidencia. Nunca hace
    fallar la aprobación (que ya quedó confirmada): si algo falla, se registra y se devuelve None.
    """
    try:
        r = await CumplimientoRegistro(db, cliente).aplicar(origen="aprobacion")
        return r if r.get("aplicado") or r.get("motivo") == "registro_incompleto" else None
    except Exception as e:  # noqa: BLE001
        logger.error("HU-38: no se pudo usar el registro como evidencia (%s)", type(e).__name__)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
