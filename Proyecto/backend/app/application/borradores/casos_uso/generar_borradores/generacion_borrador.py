"""Generación del borrador a partir de la plantilla, la evaluación y el registro (C1, C2)."""
from __future__ import annotations

import hashlib
from datetime import datetime

from app.application.ai.anonimizador import AnonimizacionError
from app.application.borradores import generador_markdown as generador
from app.application.borradores.generador_markdown import AdaptacionIA, IdentidadEmpresa
from app.application.borradores.plantillas_borrador import (
    PLANTILLAS,
    VERSION_PLANTILLAS,
    TipoPlantilla,
    plantilla as obtener_plantilla,
)
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.models.borrador_modelo import BorradorDocumento, EstadoBorrador
from app.domain.auditoria.acciones import Accion
from app.application.borradores.casos_uso.generar_borradores.comun import (
    ZONA,
    AVISOS,
    BorradorError,
    _ahora,
    borrador_a_dict,
)

class GeneracionMixin:
    """Generación del borrador a partir de la plantilla, la evaluación y el registro (C1, C2)."""

    # ------------------------------------------------------------------ generar (C1, C2)
    async def _contexto(self, evaluacion_id: int | None):
        from app.application.informes.carga import SinResultadosError, cargar_evaluacion
        from app.application.empresa.casos_uso.formacion_empresa import FormacionError, evaluacion_de_la_empresa

        try:
            ev_id = await evaluacion_de_la_empresa(self.db, self.empresa.id, evaluacion_id)
        except FormacionError as e:
            codigo = "SIN_EVALUACION" if e.codigo == "SIN_PLAN" else e.codigo
            raise BorradorError(e.status, codigo, "Tu empresa aún no tiene una evaluación completada para adaptar "
                                "el borrador." if codigo == "SIN_EVALUACION" else e.mensaje)
        try:
            datos = await cargar_evaluacion(self.db, ev_id)
        except SinResultadosError as e:
            raise BorradorError(409, "SIN_RESULTADOS", str(e))
        controles = {c for p in PLANTILLAS.values() for c in p.controles}
        fuentes = {}
        for codigo, framework, articulo in await self.repo.fuentes_de_controles(controles):
            partes = [p.strip() for p in (framework, articulo) if p and p.strip()]
            if codigo and partes:
                fuentes[codigo] = " · ".join(partes)
        return generador.contexto_desde_evaluacion(datos, fuentes)

    async def _identidad(self, ctx) -> IdentidadEmpresa:
        rubro = await self.repo.rubro(self.empresa.rubro_id) if self.empresa.rubro_id else None
        return IdentidadEmpresa(razon_social=self.empresa.razon_social, rut=self.empresa.rut,
                                rubro=(rubro.nombre_rubro if rubro else None) or ctx.rubro)
    async def generar(self, tipo: str | None, instrucciones: str | None, usar_ia: bool = True,
                      evaluacion_id: int | None = None, actividades: list[int] | None = None) -> dict:
        t = TipoPlantilla.normalizar(tipo)
        if t is None:
            raise BorradorError(422, "PLANTILLA_INVALIDA", "Elige una plantilla: Política de uso de LLM, Aviso de "
                                "privacidad o Evaluación de impacto (PIA).", plantillas=TipoPlantilla.valores())
        instrucciones = (instrucciones or "").strip()
        if len(instrucciones) > settings.BORRADORES_MAX_CHARS_INSTRUCCIONES:
            raise BorradorError(422, "INSTRUCCIONES_DEMASIADO_LARGAS",
                                f"Las instrucciones superan los {settings.BORRADORES_MAX_CHARS_INSTRUCCIONES} caracteres.",
                                max_caracteres=settings.BORRADORES_MAX_CHARS_INSTRUCCIONES)
        en_revision = await self.repo.contar_en_revision(self.empresa.id)
        if en_revision >= settings.BORRADORES_MAX_EN_REVISION:
            raise BorradorError(409, "LIMITE_BORRADORES",
                                f"Tu empresa tiene {en_revision} borradores en revisión. Consolida o descarta alguno "
                                "para generar otro.")

        plantilla = obtener_plantilla(t)
        ctx = await self._contexto(evaluacion_id)
        identidad = await self._identidad(ctx)
        # HU-38 C2: la PIA y el aviso de privacidad toman lo que ya dice el registro de actividades
        registro = None
        if t in (TipoPlantilla.PIA, TipoPlantilla.AVISO_PRIVACIDAD):
            registro = await self._registro()
            if actividades:
                validas = {a.id for a in registro.actividades}
                if t != TipoPlantilla.PIA or not set(actividades) <= validas:
                    raise BorradorError(422, "ACTIVIDADES_INVALIDAS",
                                        "Elige actividades de tu registro (solo para la evaluación de impacto).")
                registro = registro.con_seleccion(actividades)
        if usar_ia:
            adaptacion, info = await self._adaptar(plantilla, ctx, instrucciones)
        else:
            adaptacion, info = AdaptacionIA(), {"adaptado_ia": False, "motivo_sin_ia": "ia_no_solicitada",
                                                 "traza_id": None, "prompt_version": None, "advertencias": [],
                                                 "entidades_anonimizadas": 0}
        try:
            # Defensa en profundidad: las notas del modelo también pasan por el NER antes de guardarse
            notas = [n for n in [await self.anonimizador.anonimizar(x) if self.anonimizador else x
                                 for x in adaptacion.notas] if n]
        except AnonimizacionError:
            notas = []
        contenido = generador.generar_markdown(plantilla, ctx, identidad, adaptacion, datetime.now(ZONA),
                                               registro=registro)
        ahora = _ahora()
        advertencias = list(dict.fromkeys(info["advertencias"] + ([info["motivo_sin_ia"]]
                                                                  if info["motivo_sin_ia"] else [])
                                          + (registro.advertencias(t.value) if registro is not None else [])))
        huella_contexto = ctx.huella() if registro is None else hashlib.sha256(
            (ctx.huella() + registro.huella()).encode()).hexdigest()[:32]
        b = BorradorDocumento(
            empresa_id=self.empresa.id, evaluacion_id=ctx.evaluacion_id, usuario_definitivo_id=self.usuario.id,
            tipo=t.value, titulo=plantilla.titulo, estado=EstadoBorrador.EN_REVISION.value, version=1,
            contenido=contenido, adaptado_ia=info["adaptado_ia"], prompt_version=info["prompt_version"],
            traza_id=info["traza_id"], version_plantillas=VERSION_PLANTILLAS, huella_contexto=huella_contexto,
            notas=notas or None, advertencias=advertencias or None,
            fecha_creacion=ahora, fecha_actualizacion=ahora,
        )
        self.repo.agregar(b)
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.BORRADOR_GENERADO, entidad="borrador_documento", entidad_id=b.id,
            actor=self.cliente.actor,
            detalle={"empresa_id": self.empresa.id, "tipo": t.value, "evaluacion_id": ctx.evaluacion_id,
                     "adaptado_ia": info["adaptado_ia"], "secciones_adaptadas": len(adaptacion.secciones),
                     "prioritarias": len(generador.clausulas_prioritarias(plantilla, ctx)),
                     "brechas_en_contexto": len(ctx.brechas_de(plantilla)), "motivo_sin_ia": info["motivo_sin_ia"],
                     "advertencias": advertencias, "traza_id": info["traza_id"],
                     "prompt_version": info["prompt_version"], "version_plantillas": VERSION_PLANTILLAS,
                     "entidades_anonimizadas": info["entidades_anonimizadas"],
                     "huella_instrucciones": huella(instrucciones) if instrucciones else None,
                     "largo_instrucciones": len(instrucciones), "pendientes": len(generador.pendientes(contenido)),
                     "actividades_registro": registro.resumen(t.value)["actividades"] if registro is not None else None},
        )
        await self.db.commit()
        respuesta = {"borrador": borrador_a_dict(b, con_contenido=True), "cuota": await self.cuota()}
        if registro is not None:
            respuesta["registro"] = registro.resumen(t.value)
        aviso = AVISOS.get(info["motivo_sin_ia"] or "")
        if aviso:
            respuesta["aviso"] = aviso
        return respuesta
