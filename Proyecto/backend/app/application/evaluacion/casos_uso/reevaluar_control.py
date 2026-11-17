"""
HU-17 · Re-evaluar un control con evidencia nueva (remediación de la empresa cliente).

Como Evaluador de Madurez de IA, quiero cargar archivos de evidencia (políticas,
procedimientos, contratos) para que el Agente IA los analice y re-evalúe el control, para
actualizar automáticamente el puntaje de madurez y cerrar la brecha sin repetir el
autodiagnóstico.

  C1  Carga de archivos PDF, DOCX y TXT en la vista de remediación (lista blanca por
      contenido y tamaño máximo; subir_evidencia.validar_archivo).
  C2  Análisis local: extracción del texto y NER antes del LLM (HU-06) y verificación de los
      términos del control (archivos.terminos_control).
  C3  El worker actualiza el estado del control y recalcula el puntaje global y el radar
      (process_evidence._cerrar_remediacion -> GenerarResumenUseCase).

Este es el ÚNICO camino por el que cambia el puntaje de una evaluación migrada: completar un
módulo formativo (HU-26) marca la brecha con "formación hecha", pero no la cierra.

Reglas: solo el rol cliente con el servicio activo (servicio_pagado.py), sobre evaluaciones
COMPLETADAS de su empresa y controles con brecha (no cumplido, parcial o en revisión). La
empresa declara a qué estado llegó (cumplido o parcial, mejor que el actual); decide el LLM y
una evidencia nueva nunca baja el control.
"""
from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.anonimizador import AnonimizacionError
from app.domain.evaluacion.analisis_brechas import ESTADOS_BRECHA, NO_CUMPLIDO, calcular_severidad, PESO_SEVERIDAD
from app.application.informes.carga import SinResultadosError, cargar_evaluacion
from app.application.evaluacion.casos_uso.crear_respuesta import normalizar_justificacion
from app.application.encuesta_publica.casos_uso.limites_encuesta import ventana_diaria
from app.application.evidencias.casos_uso.subir_evidencia import ArchivoDemasiadoGrandeError, TipoArchivoNoAdmitidoError, validar_archivo
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import ORIGEN_REMEDIACION, ORIGENES_REMEDIACION, EstadoValidacion, Evidencia
from app.domain.models.respuesta import EstadoClasificacion
from app.domain.ports.guardia_prompt_port import PERFIL_JUSTIFICACION
from app.domain.auditoria.acciones import Accion

ESTADOS_CON_BRECHA = (EstadoClasificacion.NO_CUMPLIDO.value, EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value,
                      EstadoClasificacion.REQUIERE_REVISION.value)
DECLARABLES = (EstadoClasificacion.CUMPLIDO.value, EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value)
_RANGO = {"no_cumplido": 0, "requiere_revision": 0, "parcialmente_cumplido": 1, "cumplido": 2}
_SIN_TERMINAR = (EstadoValidacion.PENDING.value, EstadoValidacion.PROCESSING.value)
MAX_JUSTIFICACION = 2000


async def puntaje_general_actual(db: AsyncSession, evaluacion_id: int) -> float | None:
    """Puntaje general vigente (promedio de los dominios ponderado por controles), como el panel."""
    filas = await fabricas().remediacion(db).filas_resumen(evaluacion_id)
    total = sum(c or 0 for _, c in filas)
    if not total:
        return None
    return round(sum((p or 0) * (c or 0) for p, c in filas) / total, 2)


class RemediacionError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def evidencia_dict(e: Evidencia) -> dict:
    return {
        "id_evidencia": e.id_evidencia, "respuesta_id": e.respuesta_id, "nombre_archivo": e.nombre_archivo,
        "estado_validacion": e.estado_validacion, "estado_declarado": e.estado_declarado,
        "estado_previo": e.estado_previo, "estado_resultante": e.estado_resultante,
        "clasificacion_llm": e.clasificacion_llm, "confianza": e.confianza,
        "justificacion_llm": e.justificacion_llm, "errores_validacion": e.errores_validacion or [],
        "terminos_control": e.terminos_control,
        "fecha_subida": e.fecha_subida.isoformat() if e.fecha_subida else None,
        "fecha_procesada": e.fecha_procesada.isoformat() if e.fecha_procesada else None,
        "en_proceso": e.estado_validacion in _SIN_TERMINAR,
        "puntaje_previo": e.puntaje_previo,
        "puntaje_resultante": e.puntaje_resultante,
        "origen": e.origen,             # HU-38: "rat" = lo respaldó el registro de actividades (sin archivo)
        "mejoro": bool(e.estado_resultante and e.estado_previo
                       and _RANGO.get(e.estado_resultante, 0) > _RANGO.get(e.estado_previo, 0)),
    }


class Remediacion:
    def __init__(self, db: AsyncSession, cliente):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.repo = fabricas().remediacion(db)

    async def _evaluacion(self, evaluacion_id: int) -> Evaluacion:
        ev = await self.repo.obtener_evaluacion(evaluacion_id)
        if ev is None or ev.empresa_id != self.empresa.id:
            raise RemediacionError(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada")
        return ev

    async def listar(self, evaluacion_id: int) -> dict:
        """Controles con brecha de la evaluación, con su estado de formación y su última evidencia."""
        ev = await self._evaluacion(evaluacion_id)
        try:
            datos = await cargar_evaluacion(self.db, evaluacion_id)
        except SinResultadosError as e:
            raise RemediacionError(404, "SIN_RESULTADOS", str(e))

        abiertas = [r for r in datos.respuestas if r.estado in ESTADOS_CON_BRECHA]
        controles = await self.repo.controles_por_ids(
            [r.control_id for r in abiertas if r.control_id]) if abiertas else {}
        completados = await self.repo.rutas_completadas(self.empresa.id)
        ultimas: dict[int, Evidencia] = {}
        historial: dict[int, list[Evidencia]] = {}
        if abiertas:
            filas = await self.repo.evidencias_remediacion([r.id for r in abiertas])  # HU-38: también el registro
            for e in filas:
                ultimas[e.respuesta_id] = e
                historial.setdefault(e.respuesta_id, []).append(e)

        items = []
        for r in abiertas:
            cat = r.brecha_respuesta or r.brecha_control
            estado_sev = r.estado if r.estado in ESTADOS_BRECHA else NO_CUMPLIDO
            severidad, _ = calcular_severidad(cat.criticidad if cat else None, estado_sev, r.control_criticidad)
            ruta = (r.brecha_respuesta.ruta if r.brecha_respuesta else None) or (
                r.brecha_control.ruta if r.brecha_control else None)
            c = controles.get(r.control_id)
            ultima = ultimas.get(r.id)
            items.append({
                "respuesta_id": r.id, "control_codigo": r.control_codigo, "codigo_brecha": cat.codigo if cat else None,
                "dominio": r.control_dominio, "estado": r.estado, "severidad": severidad,
                "obligacion": r.control_obligacion, "pregunta": c.pregunta_evaluacion if c else None,
                "evidencia_esperada": c.evidencia_esperada if c else None,
                "recomendacion": r.control_recomendacion,
                "ruta": {"id": ruta.id, "nombre": ruta.nombre} if ruta else None,
                "formacion_completada": bool(ruta and ruta.id in completados),
                "ultima_evidencia": evidencia_dict(ultima) if ultima else None,
                # Las anteriores, de la más nueva a la más antigua (máx. 10), para ver qué se intentó
                "historial": [evidencia_dict(x) for x in reversed(historial.get(r.id, [])[:-1])][:10],
            })
        items.sort(key=lambda x: (not x["formacion_completada"], PESO_SEVERIDAD.get(x["severidad"], 9),
                                  x["control_codigo"] or ""))
        # Evolución del puntaje por remediaciones (incluye controles ya cerrados, que no están en `controles`)
        # Correcciones 05-11: cada mejora dice en qué dimensión y en qué pregunta ocurrió, para
        # que "Tu madurez ahora" muestre dónde subió la empresa.
        mejoras = await self.repo.mejoras(ev.id)
        cerrados = len(mejoras)
        por_respuesta = {r.id: r for r in datos.respuestas}

        def _mejora(f, a, d, rid, previo, resultante) -> dict:
            r = por_respuesta.get(rid)
            return {"fecha": f.isoformat() if f else None, "antes": a, "despues": d,
                    "dominio": r.control_dominio if r else None,
                    "pregunta": r.control_obligacion if r else None,
                    "estado_previo": previo, "estado_resultante": resultante}

        return {
            "evaluacion_id": ev.id,
            "puntaje_general": datos.puntaje_general,
            "puntaje_inicial": mejoras[0][1] if mejoras else datos.puntaje_general,
            "evolucion": [_mejora(*m) for m in mejoras],
            "controles_mejorados": cerrados,
            "dominios": [{"dominio": d.nombre, "puntaje": d.puntaje} for d in datos.dominios],
            "controles": items,
            "tipos_admitidos": ["pdf", "docx", "txt"],
            "max_mb": settings.EVIDENCIA_MAX_MB,
            "evidencias_por_dia": settings.REMEDIACION_EVIDENCIAS_DIA,
        }

    async def subir(self, respuesta_id: int, nombre: str | None, contenido: bytes, estado_declarado: str,
                    justificacion: str | None, *, storage, anonimizador, guard, registrar_evento,
                    limitador) -> Evidencia:
        respuesta = await self.repo.obtener_respuesta(respuesta_id)
        ev = await self.repo.obtener_evaluacion(respuesta.evaluacion_id) if respuesta and respuesta.evaluacion_id else None
        if respuesta is None or ev is None or ev.empresa_id != self.empresa.id:
            raise RemediacionError(404, "RESPUESTA_NO_ENCONTRADA", "Control no encontrado en las evaluaciones de tu empresa.")
        if not ev.esta_cerrada:
            raise RemediacionError(409, "EVALUACION_ABIERTA",
                                   "Esta evaluación aún no se completa: sube la evidencia desde el cuestionario.")
        actual = respuesta.estado_clasificacion_final or respuesta.estado_clasificacion
        if actual not in ESTADOS_CON_BRECHA:
            raise RemediacionError(409, "CONTROL_SIN_BRECHA", "Este control ya está cumplido o no aplica.")
        if estado_declarado not in DECLARABLES or _RANGO[estado_declarado] <= _RANGO.get(actual, 0):
            raise RemediacionError(422, "ESTADO_DECLARADO_INVALIDO",
                                   "Indica un estado mejor que el actual: cumplido o parcialmente cumplido.")
        justificacion = normalizar_justificacion(justificacion) or None
        if justificacion and len(justificacion) > MAX_JUSTIFICACION:
            raise RemediacionError(422, "JUSTIFICACION_LARGA", f"La justificación admite hasta {MAX_JUSTIFICACION} caracteres.")
        if not contenido:
            raise RemediacionError(400, "ARCHIVO_VACIO", "El archivo está vacío.")
        try:
            mime = validar_archivo(nombre, contenido)
        except (TipoArchivoNoAdmitidoError, ArchivoDemasiadoGrandeError) as e:
            raise RemediacionError(e.status_code, e.codigo, str(e))

        en_proceso = await self.repo.contar_en_proceso(respuesta_id)
        if en_proceso:
            raise RemediacionError(409, "REMEDIACION_EN_PROCESO",
                                   "Ya hay una evidencia de este control en análisis. Espera su resultado.")

        # Seguridad: la justificación llega al prompt del LLM (igual que en el cuestionario)
        #    HU-33: texto corto escrito por el usuario -> revisión estricta
        deteccion = guard.analizar(justificacion, PERFIL_JUSTIFICACION) if justificacion and guard is not None else None
        if deteccion is not None and deteccion.bloquear:
            if registrar_evento is not None:
                from app.domain.models.evento_seguridad import OrigenEvento
                await registrar_evento.execute(texto=justificacion, origen=OrigenEvento.JUSTIFICACION.value,
                                               evaluacion_id=ev.id, respuesta_id=respuesta_id, regla=deteccion.regla)
            raise RemediacionError(422, "PROMPT_INJECTION",
                                   "La justificación contiene instrucciones no permitidas. Describe solo cómo "
                                   "cumple ahora tu organización el control.")
        # HU-06: justificación y nombre del archivo se guardan anonimizados
        try:
            if anonimizador is not None:
                justificacion = await anonimizador.anonimizar(justificacion) if justificacion else None
                nombre = await anonimizador.anonimizar_nombre_archivo(nombre or "evidencia")
        except AnonimizacionError:
            raise RemediacionError(503, "ANONIMIZACION_NO_DISPONIBLE",
                                   "No pudimos proteger los datos personales del archivo. Intenta en unos minutos.")

        fecha, ventana, _ = ventana_diaria()
        clave = f"remed:empresa:{self.empresa.id}:{fecha}"
        consumo = await limitador.consumir(clave, settings.REMEDIACION_EVIDENCIAS_DIA, ventana)
        if not consumo.permitido:
            raise RemediacionError(429, "LIMITE_EVIDENCIAS",
                                   f"Tu empresa ya analizó {settings.REMEDIACION_EVIDENCIAS_DIA} evidencias hoy. "
                                   "Vuelve a intentarlo mañana.", reintentar_en_s=consumo.reintentar_en_s)
        try:
            ruta = await storage.save(contenido, nombre or "evidencia")
            evidencia = Evidencia(
                respuesta_id=respuesta_id, nombre_archivo=nombre or "evidencia", storage_path=ruta, mime_type=mime,
                hash_archivo=hashlib.sha256(contenido).hexdigest(), estado_validacion=EstadoValidacion.PENDING.value,
                fecha_subida=date.today(), origen=ORIGEN_REMEDIACION, estado_declarado=estado_declarado,
                justificacion_remediacion=justificacion, estado_previo=actual,
            )
            self.repo.agregar_evidencia(evidencia)
            await self.db.flush()
            fabricas().bitacora(self.db).registrar(
                accion=Accion.REMEDIACION_EVIDENCIA_SUBIDA, entidad="evidencias", entidad_id=evidencia.id_evidencia,
                actor=self.cliente.actor,
                detalle={"evaluacion_id": ev.id, "respuesta_id": respuesta_id, "estado_previo": actual,
                         "estado_declarado": estado_declarado, "tipo": mime},
            )
            await self.db.commit()
        except Exception:
            await limitador.devolver(clave)
            raise
        return evidencia

    async def detalle(self, evidencia_id: int) -> dict:
        e = await self.repo.obtener_evidencia(evidencia_id)
        respuesta = await self.repo.obtener_respuesta(e.respuesta_id) if e else None
        ev = await self.repo.obtener_evaluacion(respuesta.evaluacion_id) if respuesta else None
        if e is None or e.origen not in ORIGENES_REMEDIACION or ev is None or ev.empresa_id != self.empresa.id:
            raise RemediacionError(404, "EVIDENCIA_NO_ENCONTRADA", "Evidencia no encontrada")
        datos = None
        try:
            datos = await cargar_evaluacion(self.db, ev.id)
        except SinResultadosError:
            pass
        return {
            **evidencia_dict(e),
            "estado_actual": respuesta.estado_clasificacion_final or respuesta.estado_clasificacion,
            "puntaje_general": datos.puntaje_general if datos else None,
            # Para redibujar el radar apenas termina el análisis, sin otra consulta
            "dominios": [{"dominio": d.nombre, "puntaje": d.puntaje} for d in datos.dominios] if datos else [],
        }
