"""
HU-26 · Recorrido de los módulos formativos y registro del avance de la empresa.

Como Usuario definitivo de una empresa cliente, quiero realizar los módulos recomendados en
el plan formativo y registrar el avance, para cerrar las brechas detectadas mediante
formación y demostrar el progreso alcanzado.

  C1  Con el servicio activo (contrato vigente, HU-30: app/core/servicio_pagado.py) cada
      módulo del plan (HU-12) se recorre: lecciones con contenido y material de apoyo
      (placeholders) y una actividad de verificación al final que corrige el servidor.
  C2  El avance queda en la EMPRESA (avance_formativo): módulos iniciados y completados y el
      porcentaje por dimensión y nivel (resumir_avance), que ve el panel de formación.
  C3  Al aprobar la actividad se registra la fecha y se emite el código de la constancia
      (PDF descargable). Las brechas del módulo quedan con "formación completada", pero el
      puntaje NO cambia: eso solo pasa con evidencia nueva (HU-17, remediacion.py).

Quién: solo el rol cliente, y solo sobre los módulos del plan de una evaluación migrada a su
empresa (o los que ya empezó). Todo cambio queda en la bitácora (HU-09).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.formacion.constancia_pdf import DatosConstancia, generar_constancia, nombre_constancia
from app.application.formacion.logica import (
    AvanceModulo,
    Leccion,
    Pregunta,
    codigo_constancia,
    corregir,
    lecciones_de_ruta,
    preguntas_publicas,
    resumir_avance,
)
from app.application.informes.analisis import PlanFormativo, RutaCatalogo, construir_brechas, construir_plan
from app.application.informes.carga import DatosEvaluacion, SinResultadosError, cargar_evaluacion
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.formacion import AvanceFormativo, EstadoAvance, LeccionFormativa, PreguntaVerificacion
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository


class FormacionError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _avance_logico(a: AvanceFormativo) -> AvanceModulo:
    return AvanceModulo(
        ruta_id=a.ruta_formativa_id, estado=a.estado, lecciones_vistas=frozenset(a.ids_vistas),
        intentos=a.intentos or 0, mejor_puntaje=a.mejor_puntaje, ultimo_puntaje=a.ultimo_puntaje,
        fecha_inicio=a.fecha_inicio, fecha_completado=a.fecha_completado, codigo_constancia=a.codigo_constancia,
    )


async def evaluacion_de_la_empresa(db: AsyncSession, empresa_id: int, evaluacion_id: int | None) -> int:
    """La evaluación pedida si es de la empresa; si no se pide, la más reciente con resultados."""
    if evaluacion_id is not None:
        ev = await db.get(Evaluacion, evaluacion_id)
        if ev is None or ev.empresa_id != empresa_id:
            raise FormacionError(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada")
        return ev.id
    # HU-29: la regla única de "la más reciente" (la completada de mayor id; una reevaluación
    # en curso no reemplaza a la última terminada). Antes se ordenaba por fecha_migracion,
    # que las reevaluaciones no tienen.
    from app.application.use_cases.historial_empresa import evaluacion_mas_reciente

    fila = (await evaluacion_mas_reciente(db, empresa_id)
            or await evaluacion_mas_reciente(db, empresa_id, solo_completadas=False))
    if fila is None:
        raise FormacionError(404, "SIN_PLAN", "Tu empresa aún no tiene una evaluación con plan formativo.")
    return fila


async def plan_de_evaluacion(db: AsyncSession, evaluacion_id: int) -> tuple[DatosEvaluacion, PlanFormativo]:
    try:
        datos = await cargar_evaluacion(db, evaluacion_id)
    except SinResultadosError as e:
        raise FormacionError(404, "SIN_RESULTADOS", str(e))
    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    return datos, construir_plan(construir_brechas(datos.respuestas, puntajes), datos.dominios, datos.rutas)


class FormacionEmpresa:
    """Casos de uso del recorrido. `cliente` es el ClienteConServicio de servicio_pagado.py."""

    def __init__(self, db: AsyncSession, cliente):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.bitacora = BitacoraRepository(db)

    # ------------------------------------------------------------ lectura
    async def _avances(self) -> dict[int, AvanceFormativo]:
        filas = (await self.db.execute(
            select(AvanceFormativo).where(AvanceFormativo.empresa_id == self.empresa.id)
        )).scalars().all()
        return {a.ruta_formativa_id: a for a in filas}

    async def _lecciones(self, ruta: RutaCatalogo) -> list[Leccion]:
        filas = (await self.db.execute(
            select(LeccionFormativa).where(LeccionFormativa.ruta_formativa_id == ruta.id)
        )).scalars().all()
        guardadas = [
            Leccion(orden=f.orden, titulo=f.titulo, resumen=f.resumen,
                    contenido=tuple(x.strip() for x in (f.contenido or "").splitlines() if x.strip()),
                    material=tuple(f.material_apoyo or ()), duracion_min=f.duracion_min)
            for f in filas
        ]
        return lecciones_de_ruta(ruta, guardadas)

    async def _conteo_lecciones(self, rutas: list[RutaCatalogo]) -> dict[int, int]:
        filas = (await self.db.execute(
            select(LeccionFormativa.ruta_formativa_id, LeccionFormativa.orden)
        )).all()
        conteo: dict[int, int] = {}
        for ruta_id, _ in filas:
            conteo[ruta_id] = conteo.get(ruta_id, 0) + 1
        return {r.id: conteo.get(r.id) or len(r.contenidos) for r in rutas}

    async def _preguntas(self, ruta_id: int) -> list[Pregunta]:
        filas = (await self.db.execute(
            select(PreguntaVerificacion).where(PreguntaVerificacion.ruta_formativa_id == ruta_id)
        )).scalars().all()
        return [Pregunta(id=f.id, orden=f.orden, enunciado=f.enunciado, opciones=tuple(f.opciones or ()),
                         correcta=f.correcta, explicacion=f.explicacion) for f in filas]

    async def _contexto(self, evaluacion_id: int | None):
        ev = await evaluacion_de_la_empresa(self.db, self.empresa.id, evaluacion_id)
        datos, plan = await plan_de_evaluacion(self.db, ev)
        return ev, datos, plan

    async def avance(self, evaluacion_id: int | None) -> dict:
        ev, datos, plan = await self._contexto(evaluacion_id)
        avances = await self._avances()
        resumen = resumir_avance(
            plan, {k: _avance_logico(a) for k, a in avances.items()},
            await self._conteo_lecciones(datos.rutas), datos.rutas,
        )
        return {
            "evaluacion_id": ev,
            "empresa": {"id": self.empresa.id, "razon_social": self.empresa.razon_social},
            "umbral_aprobacion": settings.FORMACION_UMBRAL_APROBACION,
            **resumen,
        }

    async def _modulo_accesible(self, ruta_id: int, evaluacion_id: int | None):
        """La ruta debe estar en el plan de la evaluación o la empresa ya debe haberla empezado."""
        ev, datos, plan = await self._contexto(evaluacion_id)
        ruta = next((r for r in datos.rutas if r.id == ruta_id), None)
        avances = await self._avances()
        en_plan = next(
            ((d, m) for d in plan.dimensiones for m in d.modulos if m.ruta.id == ruta_id), None
        )
        if ruta is None or (en_plan is None and ruta_id not in avances):
            raise FormacionError(404, "MODULO_NO_ENCONTRADO", "Este módulo no está en el plan formativo de tu empresa.")
        return ev, ruta, en_plan, avances.get(ruta_id)

    def _avance_dict(self, a: AvanceFormativo | None, total_lecciones: int) -> dict:
        if a is None:
            return {"estado": "no_iniciado", "lecciones_vistas": [], "intentos": 0, "mejor_puntaje": None,
                    "ultimo_puntaje": None, "fecha_inicio": None, "fecha_completado": None,
                    "codigo_constancia": None, "porcentaje_lecciones": 0.0}
        vistas = sorted(o for o in a.ids_vistas if 1 <= o <= total_lecciones)
        return {
            "estado": a.estado, "lecciones_vistas": vistas, "intentos": a.intentos or 0,
            "mejor_puntaje": a.mejor_puntaje, "ultimo_puntaje": a.ultimo_puntaje,
            "fecha_inicio": a.fecha_inicio.isoformat(timespec="seconds") if a.fecha_inicio else None,
            "fecha_completado": a.fecha_completado.isoformat(timespec="seconds") if a.fecha_completado else None,
            "codigo_constancia": a.codigo_constancia,
            "porcentaje_lecciones": 100.0 if a.completado else (
                round(100 * len(vistas) / total_lecciones, 1) if total_lecciones else 0.0),
        }

    async def _intentos_restantes(self, limitador, ruta_id: int) -> int | None:
        if limitador is None:
            return None
        fecha, _, _ = ventana_diaria()
        try:
            usados = await limitador.usados(self._clave_intentos(ruta_id, fecha))
        except Exception:  # noqa: BLE001 - es solo informativo
            return None
        return max(0, settings.FORMACION_INTENTOS_DIA - usados)

    def _clave_intentos(self, ruta_id: int, fecha: str) -> str:
        return f"form:intento:{self.empresa.id}:{ruta_id}:{fecha}"

    async def modulo(self, ruta_id: int, evaluacion_id: int | None, limitador=None) -> dict:
        ev, ruta, en_plan, a = await self._modulo_accesible(ruta_id, evaluacion_id)
        lecciones = await self._lecciones(ruta)
        preguntas = await self._preguntas(ruta_id)
        dim, mod = en_plan if en_plan else (None, None)
        avance = self._avance_dict(a, len(lecciones))
        return {
            "evaluacion_id": ev,
            "ruta": {
                "id": ruta.id, "nombre": ruta.nombre, "dominio": ruta.dominio_efectivo, "nivel": ruta.nivel_efectivo,
                "objetivo": ruta.objetivo, "objetivos_especificos": list(ruta.objetivos_especificos),
                "horas": ruta.horas, "modalidad": ruta.modalidad, "publico_objetivo": ruta.publico_objetivo,
            },
            "en_plan": en_plan is not None,
            "motivo": mod.motivo if mod else "historial",
            "prioridad": mod.prioridad if mod else "Complementario",
            "brechas": [
                {"codigo": c.codigo, "respuesta_id": c.respuesta_id, "control_codigo": c.control_codigo,
                 "dominio": c.dominio, "severidad": c.severidad, "estado": c.estado}
                for c in (mod.brechas if mod else [])
            ],
            "lecciones": [
                {"orden": l.orden, "titulo": l.titulo, "resumen": l.resumen, "contenido": list(l.contenido),
                 "material_apoyo": list(l.material), "duracion_min": l.duracion_min,
                 "vista": l.orden in set(avance["lecciones_vistas"])}
                for l in lecciones
            ],
            "actividad": {
                "preguntas": preguntas_publicas(preguntas, self.empresa.id),
                "umbral_aprobacion": settings.FORMACION_UMBRAL_APROBACION,
                "intentos_por_dia": settings.FORMACION_INTENTOS_DIA,
                "intentos_restantes_hoy": await self._intentos_restantes(limitador, ruta_id),
                "disponible": bool(preguntas) and len(avance["lecciones_vistas"]) >= len(lecciones),
            },
            "avance": avance,
            "dimension_nivel": dim.nivel_asignado if dim else None,
        }

    # ------------------------------------------------------------ escritura
    async def _obtener_o_crear(self, ruta_id: int, ev: int) -> tuple[AvanceFormativo, bool]:
        a = (await self.db.execute(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == self.empresa.id, AvanceFormativo.ruta_formativa_id == ruta_id
            ).with_for_update()
        )).scalar_one_or_none()
        if a is not None:
            return a, False
        ahora = _ahora()
        a = AvanceFormativo(
            empresa_id=self.empresa.id, ruta_formativa_id=ruta_id, evaluacion_id=ev,
            usuario_definitivo_id=self.cliente.actor.id, estado=EstadoAvance.EN_CURSO.value,
            lecciones_vistas=[], intentos=0, fecha_inicio=ahora, fecha_ultima_actividad=ahora,
        )
        self.db.add(a)
        return a, True

    async def marcar_leccion(self, ruta_id: int, orden: int, evaluacion_id: int | None) -> dict:
        ev, ruta, _, _ = await self._modulo_accesible(ruta_id, evaluacion_id)
        lecciones = await self._lecciones(ruta)
        if not any(l.orden == orden for l in lecciones):
            raise FormacionError(404, "LECCION_NO_ENCONTRADA", "Esta lección no existe en el módulo.")
        a, nuevo = await self._obtener_o_crear(ruta_id, ev)
        vistas = a.ids_vistas
        if orden not in vistas:
            # Se reasigna la lista (no se muta) para que SQLAlchemy detecte el cambio del JSON
            a.lecciones_vistas = sorted(vistas | {orden})
        a.fecha_ultima_actividad = _ahora()
        if nuevo:
            await self.db.flush()
            self.bitacora.registrar(
                accion=Accion.FORMACION_MODULO_INICIADO, entidad="avance_formativo", entidad_id=a.id,
                actor=self.cliente.actor, detalle={"empresa_id": self.empresa.id, "ruta_id": ruta_id, "evaluacion_id": ev},
            )
        await self.db.commit()
        return self._avance_dict(a, len(lecciones))

    async def verificar(self, ruta_id: int, respuestas: dict[int, int], evaluacion_id: int | None,
                        limitador) -> dict:
        ev, ruta, _, a = await self._modulo_accesible(ruta_id, evaluacion_id)
        lecciones = await self._lecciones(ruta)
        preguntas = await self._preguntas(ruta_id)
        if a is not None and a.completado:
            raise FormacionError(409, "MODULO_COMPLETADO", "Ya completaste este módulo. Descarga tu constancia.")
        if not preguntas:
            raise FormacionError(409, "SIN_ACTIVIDAD", "Este módulo aún no tiene actividad de verificación.")
        vistas = a.ids_vistas if a else set()
        pendientes = [l.orden for l in lecciones if l.orden not in vistas]
        if pendientes:
            raise FormacionError(409, "LECCIONES_PENDIENTES",
                                 f"Te faltan {len(pendientes)} lecciones antes de la actividad de verificación.",
                                 pendientes=pendientes)
        por_id = {p.id: p for p in preguntas}
        for pid, opcion in respuestas.items():
            if pid not in por_id or not 0 <= int(opcion) < len(por_id[pid].opciones):
                raise FormacionError(422, "RESPUESTA_INVALIDA", "Una de las respuestas no corresponde a esta actividad.")

        fecha, ventana, _ = ventana_diaria()
        consumo = await limitador.consumir(self._clave_intentos(ruta_id, fecha), settings.FORMACION_INTENTOS_DIA, ventana)
        if not consumo.permitido:
            raise FormacionError(429, "LIMITE_INTENTOS",
                                 f"Usaste los {settings.FORMACION_INTENTOS_DIA} intentos de hoy. Repasa las lecciones "
                                 "y vuelve a intentarlo mañana.", reintentar_en_s=consumo.reintentar_en_s)

        nota = corregir(preguntas, respuestas, settings.FORMACION_UMBRAL_APROBACION)
        a, _ = await self._obtener_o_crear(ruta_id, ev)
        ahora = _ahora()
        a.intentos = (a.intentos or 0) + 1
        a.ultimo_puntaje = nota.puntaje
        a.mejor_puntaje = max(nota.puntaje, a.mejor_puntaje or 0)
        a.fecha_ultima_actividad = ahora
        if nota.aprobado:
            a.estado = EstadoAvance.COMPLETADO.value
            a.fecha_completado = ahora
            a.codigo_constancia = codigo_constancia()
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.FORMACION_VERIFICACION, entidad="avance_formativo", entidad_id=a.id,
            actor=self.cliente.actor, resultado=RESULTADO_OK if nota.aprobado else RESULTADO_RECHAZADO,
            detalle={"ruta_id": ruta_id, "puntaje": nota.puntaje, "intento": a.intentos},
        )
        if nota.aprobado:
            self.bitacora.registrar(
                accion=Accion.FORMACION_MODULO_COMPLETADO, entidad="avance_formativo", entidad_id=a.id,
                actor=self.cliente.actor,
                detalle={"empresa_id": self.empresa.id, "ruta_id": ruta_id, "evaluacion_id": ev,
                         "codigo_constancia": a.codigo_constancia},
            )
        await self.db.commit()
        return {
            "aprobado": nota.aprobado, "puntaje": nota.puntaje, "correctas": nota.correctas, "total": nota.total,
            "umbral_aprobacion": settings.FORMACION_UMBRAL_APROBACION,
            "detalle": nota.detalle, "sin_responder": nota.sin_responder,
            "intentos_restantes_hoy": max(0, consumo.limite - consumo.usados),
            "avance": self._avance_dict(a, len(lecciones)),
        }

    async def constancia(self, ruta_id: int) -> tuple[bytes, str]:
        a = (await self.db.execute(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == self.empresa.id, AvanceFormativo.ruta_formativa_id == ruta_id
            )
        )).scalar_one_or_none()
        if a is not None and a.completado and a.fecha_eliminacion_constancia and not a.codigo_constancia:
            # HU-29: la empresa la eliminó desde "Mis documentos" (el módulo sigue completado)
            raise FormacionError(404, "CONSTANCIA_ELIMINADA",
                                 "Eliminaste esta constancia desde Mis documentos; su código quedó anulado.")
        if a is None or not a.completado or not a.codigo_constancia:
            raise FormacionError(404, "CONSTANCIA_NO_DISPONIBLE",
                                 "La constancia se descarga cuando apruebas la actividad de verificación.")
        from app.domain.models.ruta_formativa import RutaFormativa
        from app.domain.models.dominio import Dominio

        ruta = await self.db.get(RutaFormativa, ruta_id)
        dominio = await self.db.get(Dominio, ruta.dominio_id) if ruta and ruta.dominio_id else None
        rc = RutaCatalogo(id=ruta.id, nombre=ruta.nombre or f"Ruta {ruta.id}",
                          dominio=dominio.nombre_dominio if dominio else None, nivel=ruta.nivel)
        datos = DatosConstancia(
            razon_social=self.empresa.razon_social, rut=self.empresa.rut, participante=self.cliente.usuario.nombre,
            modulo=rc.nombre, dominio=rc.dominio_efectivo, nivel=rc.nivel_efectivo, horas=ruta.horas,
            modalidad=ruta.modalidad, objetivo=ruta.objetivo, fecha_completado=a.fecha_completado,
            puntaje=a.mejor_puntaje, codigo=a.codigo_constancia,
        )
        pdf = generar_constancia(datos)
        self.bitacora.registrar(
            accion=Accion.FORMACION_CONSTANCIA, entidad="avance_formativo", entidad_id=a.id,
            actor=self.cliente.actor, detalle={"ruta_id": ruta_id},
        )
        await self.db.commit()
        return pdf, nombre_constancia(datos)


async def avance_de_empresa_para_admin(db: AsyncSession, empresa, evaluacion_id: int | None) -> dict:
    """Vista del administrador de Therion Labs (panel interno): el mismo resumen del cliente."""
    from types import SimpleNamespace

    from app.core.autenticacion import Actor
    falso = SimpleNamespace(actor=Actor(id=0, rol="admin_therion"), usuario=None, empresa=empresa)
    return await FormacionEmpresa(db, falso).avance(evaluacion_id)
