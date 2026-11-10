"""
HU-16 · Borradores adaptados de documentos de cumplimiento.

Como Gestor de Riesgos e IA, quiero que el Agente IA genere borradores adaptados de
políticas, avisos y procedimientos normativos, para acelerar la creación de la
documentación legal e institucional requerida para mitigar las no-conformidades.

  C1  Plantillas editables en Markdown/PDF: Política de uso de LLM, Aviso de privacidad y
      PIA/EIPD (app/application/borradores/plantillas.py). El borrador se guarda en Markdown
      y se descarga en Markdown o PDF.
  C2  Cláusulas ajustadas a la Ley N.º 21.719 y a las dimensiones del modelo: cada cláusula
      está atada a una dimensión y a los controles de la matriz; las que tratan una brecha
      abierta de la evaluación más reciente de la empresa llevan su "Medida prioritaria", su
      fundamento es el artículo real de la matriz y el Anexo A cruza el documento con los
      puntajes por dimensión. El Agente IA (skill "borrador" de LangGraph) adapta las
      cláusulas al rubro, a las brechas y a las instrucciones de la empresa.
  C3  Revisión, edición y descarga previa a la consolidación: el borrador queda EN REVISIÓN,
      se edita (con control de versión), se descarga en Markdown o PDF (con marca de agua
      "BORRADOR") y solo al CONSOLIDARLO queda de solo lectura y su PDF se guarda en
      "Mis documentos" (HU-29). Consolidar con campos [COMPLETAR: ...] pendientes exige
      confirmarlo.

Reglas:
  - Solo el usuario definitivo con contrato VIGENTE (la ruta usa empresa_con_servicio, HU-30).
  - El LLM no toca la BD ni ve la razón social, el RUT ni datos de contacto: recibe la
    plantilla, datos de catálogo y las instrucciones de la empresa, que pasan por el filtro
    del agente (HU-18: un ataque bloquea sin llamar al NER ni al LLM) y por el NER del gateway.
  - La salida del modelo se valida y se ancla (salida_ia.py). Si el LLM falla, no está
    habilitado o se agotó la cuota, el borrador se arma igual con la plantilla y se avisa.
  - Cuota de borradores con IA por empresa y día (BORRADORES_IA_DIA_EMPRESA) + cuota global
    del LLM. Si el servicio de IA falla, la cuota se devuelve.
  - Todo queda en la bitácora inmutable (HU-09) sin el texto del borrador ni de las
    instrucciones (solo su huella HMAC).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.agente import AgenteIA, SkillIA
from app.application.ai.anonimizador import AnonimizacionError, AnonimizadorPII
from app.application.ai.gateway import CapaIAError
from app.application.borradores import generador
from app.application.borradores.generador import AdaptacionIA, IdentidadEmpresa
from app.application.borradores.pdf_borrador import PdfNoDisponibleError, generar_pdf_borrador
from app.application.borradores.plantillas import (
    PLANTILLAS,
    VERSION_PLANTILLAS,
    TipoPlantilla,
    catalogo,
    plantilla as obtener_plantilla,
)
from app.application.use_cases.limites_encuesta import Reserva, ventana_diaria
from app.core.cliente import huella
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.borrador import BorradorDocumento, EstadoBorrador
from app.domain.models.documento_empresa import TIPO_BORRADOR
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)
ZONA = ZoneInfo("America/Santiago")
MAX_PENDIENTES_LISTA = 20
MIME_MD = "text/markdown"
MIME_PDF = "application/pdf"

# Mensajes para el usuario cuando el borrador se armó sin el Agente IA
AVISOS = {
    "ia_deshabilitada": "El Agente IA no está habilitado: el borrador se armó con la plantilla y tu evaluación.",
    "ia_no_solicitada": None,
    "cuota_ia_agotada": "Tu empresa usó los borradores con IA de hoy: este se armó con la plantilla y tu evaluación. "
                        "Podrás adaptarlos con IA después del reinicio.",
    "ia_no_disponible": "El Agente IA no respondió: el borrador se armó con la plantilla y tu evaluación. "
                        "Puedes generarlo de nuevo más tarde.",
    "salida_ia_descartada": "Descartamos lo que propuso el Agente IA porque no pasó la validación de seguridad: "
                            "el borrador se armó con la plantilla y tu evaluación.",
}
MENSAJE_BLOQUEO = ("Tus instrucciones contienen texto que intenta cambiar las reglas del Agente IA, así que no se "
                   "procesaron. Escríbelas como preferencias de redacción (por ejemplo, \"somos una clínica que usa "
                   "un chatbot de agendamiento\").")
MENSAJE_ETICA = ("No podemos redactar eso: el documento no puede aparentar un cumplimiento que no existe ni ocultar el "
                 "uso de IA, un incidente o un derecho de los titulares (Ley 21.719). Ajusta tus instrucciones.")


class BorradorError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def borrador_a_dict(b: BorradorDocumento, con_contenido: bool = False) -> dict:
    pend = generador.pendientes(b.contenido)
    d = {
        "id": b.id, "tipo": b.tipo, "titulo": b.titulo, "estado": b.estado, "version": b.version,
        "editable": b.editable, "adaptado_ia": bool(b.adaptado_ia), "evaluacion_id": b.evaluacion_id,
        "version_plantillas": b.version_plantillas, "pendientes": len(pend),
        "notas": list(b.notas or []), "advertencias": list(b.advertencias or []),
        "fecha_creacion": _iso(b.fecha_creacion), "fecha_actualizacion": _iso(b.fecha_actualizacion),
        "fecha_consolidacion": _iso(b.fecha_consolidacion), "documento_id": b.documento_id,
        "descargas": {"md": f"/api/borradores/{b.id}/descarga?formato=md",
                      "pdf": f"/api/borradores/{b.id}/descarga?formato=pdf"},
    }
    if con_contenido:
        d["contenido"] = b.contenido
        d["pendientes_detalle"] = pend[:MAX_PENDIENTES_LISTA]
    return d


class Borradores:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, agente: AgenteIA | None = None,
                 anonimizador: AnonimizadorPII | None = None, limitador: Limitador | None = None,
                 registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.usuario = cliente.usuario
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.bitacora = BitacoraRepository(db)

    # ------------------------------------------------------------------ catálogo y cuota
    def _clave_dia(self, fecha: str) -> str:
        return f"borrador:dia:{self.empresa.id}:{fecha}"

    async def cuota(self) -> dict:
        fecha, _, reinicio = ventana_diaria()
        limite = settings.BORRADORES_IA_DIA_EMPRESA
        try:
            usados = await self.limitador.usados(self._clave_dia(fecha)) if self.limitador else 0
        except LimitadorNoDisponibleError:
            usados = 0
        return {"usados": usados, "limite": limite or None,
                "restantes": max(0, limite - usados) if limite > 0 else None,
                "reinicia_en": reinicio.isoformat().replace("+00:00", "Z")}

    async def catalogo(self) -> dict:
        return {
            "plantillas": catalogo(),
            "ia_habilitada": bool(settings.BORRADORES_IA_HABILITADA),
            "cuota": await self.cuota(),
            "max_caracteres_contenido": settings.BORRADORES_MAX_CHARS_CONTENIDO,
            "max_caracteres_instrucciones": settings.BORRADORES_MAX_CHARS_INSTRUCCIONES,
            "max_en_revision": settings.BORRADORES_MAX_EN_REVISION,
        }

    # ------------------------------------------------------------------ lectura
    async def _borrador(self, borrador_id: int) -> BorradorDocumento:
        b = await self.db.get(BorradorDocumento, borrador_id)
        if b is None or b.empresa_id != self.empresa.id:   # lo ajeno no existe (404, no 403)
            raise BorradorError(404, "BORRADOR_NO_ENCONTRADO", "Borrador no encontrado.")
        return b

    async def listar(self) -> dict:
        filas = (await self.db.execute(
            select(BorradorDocumento).where(BorradorDocumento.empresa_id == self.empresa.id)
            .order_by(BorradorDocumento.fecha_actualizacion.desc(), BorradorDocumento.id.desc())
        )).scalars().all()
        return {"items": [borrador_a_dict(b) for b in filas]}

    async def obtener(self, borrador_id: int) -> dict:
        return {"borrador": borrador_a_dict(await self._borrador(borrador_id), con_contenido=True)}

    # ------------------------------------------------------------------ generar (C1, C2)
    async def _contexto(self, evaluacion_id: int | None):
        from app.application.informes.carga import SinResultadosError, cargar_evaluacion
        from app.application.use_cases.formacion_empresa import FormacionError, evaluacion_de_la_empresa
        from app.domain.models.matriz_control import MatrizControl

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
        for codigo, framework, articulo in (await self.db.execute(
            select(MatrizControl.codigo_control, MatrizControl.framework_fuente, MatrizControl.articulo_referencia)
            .where(MatrizControl.codigo_control.in_(sorted(controles)))
        )).all():
            partes = [p.strip() for p in (framework, articulo) if p and p.strip()]
            if codigo and partes:
                fuentes[codigo] = " · ".join(partes)
        return generador.contexto_desde_evaluacion(datos, fuentes)

    async def _identidad(self, ctx) -> IdentidadEmpresa:
        from app.domain.models.rubro import Rubro

        rubro = await self.db.get(Rubro, self.empresa.rubro_id) if self.empresa.rubro_id else None
        return IdentidadEmpresa(razon_social=self.empresa.razon_social, rut=self.empresa.rut,
                                rubro=(rubro.nombre_rubro if rubro else None) or ctx.rubro)

    async def _reservar_cuota(self) -> Reserva | None:
        """None si la cuota de la empresa o la global se agotó (el borrador se arma sin IA)."""
        fecha, ventana, _ = ventana_diaria()
        reserva = Reserva(self.limitador)
        for clave, limite in ((self._clave_dia(fecha), settings.BORRADORES_IA_DIA_EMPRESA),
                              (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL)):
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana)
            reserva.claves.append(clave)
            if not consumo.permitido:
                await reserva.devolver()
                return None
        return reserva

    async def _evento(self, texto: str, tipo: str | None, evaluacion_id: int | None,
                      regla: str | None = None) -> None:
        if self.registrar_evento is not None:
            await self.registrar_evento.execute(texto, OrigenEvento.BORRADOR.value, evaluacion_id=evaluacion_id,
                                                tipo=tipo or "prompt_injection", regla=regla)

    async def _adaptar(self, plantilla, ctx, instrucciones: str) -> tuple[AdaptacionIA, dict]:
        """Llama al Agente IA. Devuelve la adaptación (vacía si no se pudo) y lo que se audita."""
        info: dict = {"adaptado_ia": False, "motivo_sin_ia": None, "traza_id": None, "prompt_version": None,
                      "advertencias": [], "entidades_anonimizadas": 0}
        if not settings.BORRADORES_IA_HABILITADA or self.agente is None:
            info["motivo_sin_ia"] = "ia_deshabilitada"
            return AdaptacionIA(), info
        reserva = None
        if self.limitador is not None:
            try:
                reserva = await self._reservar_cuota()
            except LimitadorNoDisponibleError:
                info["motivo_sin_ia"] = "ia_no_disponible"
                return AdaptacionIA(), info
            if reserva is None:
                info["motivo_sin_ia"] = "cuota_ia_agotada"
                return AdaptacionIA(), info
        prioritarias = generador.clausulas_prioritarias(plantilla, ctx)
        try:
            salida = await self.agente.ejecutar(
                SkillIA.BORRADOR, textos={"instrucciones": instrucciones},
                datos={"plantilla": plantilla, "contexto": ctx, "prioritarias": prioritarias},
                contexto=ContextoLlamada(evaluacion_id=ctx.evaluacion_id),
            )
        except CapaIAError as e:
            if reserva is not None:
                await reserva.devolver()   # no fue culpa del usuario: no gasta su cuota
            info.update(motivo_sin_ia="ia_no_disponible", error_ia=e.tipo_error)
            return AdaptacionIA(), info

        if salida.bloqueado:
            await self._evento(instrucciones, salida.motivo, ctx.evaluacion_id, regla=salida.regla)
            self.bitacora.registrar(
                accion=Accion.BORRADOR_INSTRUCCIONES_BLOQUEADAS, entidad="borrador_documento", entidad_id=None,
                actor=self.cliente.actor, resultado=RESULTADO_RECHAZADO,
                detalle={"empresa_id": self.empresa.id, "tipo": plantilla.tipo.value, "categoria": salida.motivo,
                         "regla": salida.regla, "huella_instrucciones": huella(instrucciones),
                         "largo": len(instrucciones)},
            )
            await self.db.commit()
            etica = salida.motivo == "uso_indebido"
            raise BorradorError(422, "INSTRUCCIONES_BLOQUEADAS", MENSAJE_ETICA if etica else MENSAJE_BLOQUEO,
                                categoria=salida.motivo)

        resultado = salida.resultado
        info.update(traza_id=resultado.traza_id, prompt_version=resultado.prompt_version,
                    advertencias=list(salida.advertencias), entidades_anonimizadas=resultado.entidades_anonimizadas)
        if salida.salida_bloqueada:
            # HU-18: la salida filtró el system prompt; es un ataque logrado. Se usa la plantilla base.
            await self._evento(instrucciones, "fuga_prompt_salida", ctx.evaluacion_id, regla="salida.fuga_prompt")
            info["motivo_sin_ia"] = "salida_ia_descartada"
            return AdaptacionIA(), info
        data = resultado.data
        adaptacion = AdaptacionIA(
            introduccion=data.introduccion or None,
            secciones={s.clausula_id: s.texto for s in data.secciones},
            notas=tuple(data.notas_revision),
        )
        info["adaptado_ia"] = bool(adaptacion.secciones or adaptacion.introduccion)
        return adaptacion, info

    async def generar(self, tipo: str | None, instrucciones: str | None, usar_ia: bool = True,
                      evaluacion_id: int | None = None) -> dict:
        t = TipoPlantilla.normalizar(tipo)
        if t is None:
            raise BorradorError(422, "PLANTILLA_INVALIDA", "Elige una plantilla: Política de uso de LLM, Aviso de "
                                "privacidad o Evaluación de impacto (PIA).", plantillas=TipoPlantilla.valores())
        instrucciones = (instrucciones or "").strip()
        if len(instrucciones) > settings.BORRADORES_MAX_CHARS_INSTRUCCIONES:
            raise BorradorError(422, "INSTRUCCIONES_DEMASIADO_LARGAS",
                                f"Las instrucciones superan los {settings.BORRADORES_MAX_CHARS_INSTRUCCIONES} caracteres.",
                                max_caracteres=settings.BORRADORES_MAX_CHARS_INSTRUCCIONES)
        en_revision = await self.db.scalar(
            select(func.count()).select_from(BorradorDocumento).where(
                BorradorDocumento.empresa_id == self.empresa.id,
                BorradorDocumento.estado == EstadoBorrador.EN_REVISION.value)
        ) or 0
        if en_revision >= settings.BORRADORES_MAX_EN_REVISION:
            raise BorradorError(409, "LIMITE_BORRADORES",
                                f"Tu empresa tiene {en_revision} borradores en revisión. Consolida o descarta alguno "
                                "para generar otro.")

        plantilla = obtener_plantilla(t)
        ctx = await self._contexto(evaluacion_id)
        identidad = await self._identidad(ctx)
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
        contenido = generador.generar_markdown(plantilla, ctx, identidad, adaptacion, datetime.now(ZONA))
        ahora = _ahora()
        advertencias = list(dict.fromkeys(info["advertencias"] + ([info["motivo_sin_ia"]]
                                                                  if info["motivo_sin_ia"] else [])))
        b = BorradorDocumento(
            empresa_id=self.empresa.id, evaluacion_id=ctx.evaluacion_id, usuario_definitivo_id=self.usuario.id,
            tipo=t.value, titulo=plantilla.titulo, estado=EstadoBorrador.EN_REVISION.value, version=1,
            contenido=contenido, adaptado_ia=info["adaptado_ia"], prompt_version=info["prompt_version"],
            traza_id=info["traza_id"], version_plantillas=VERSION_PLANTILLAS, huella_contexto=ctx.huella(),
            notas=notas or None, advertencias=advertencias or None,
            fecha_creacion=ahora, fecha_actualizacion=ahora,
        )
        self.db.add(b)
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
                     "largo_instrucciones": len(instrucciones), "pendientes": len(generador.pendientes(contenido))},
        )
        await self.db.commit()
        respuesta = {"borrador": borrador_a_dict(b, con_contenido=True), "cuota": await self.cuota()}
        aviso = AVISOS.get(info["motivo_sin_ia"] or "")
        if aviso:
            respuesta["aviso"] = aviso
        return respuesta

    # ------------------------------------------------------------------ revisión y edición (C3)
    def _editable(self, b: BorradorDocumento, version: int | None) -> None:
        if not b.editable:
            raise BorradorError(409, "BORRADOR_CONSOLIDADO",
                                "Este borrador ya está consolidado: es de solo lectura. Genera uno nuevo para cambiarlo.")
        if version is not None and version != b.version:
            raise BorradorError(409, "VERSION_DESACTUALIZADA",
                                "El borrador cambió desde que lo abriste (otra pestaña u otra persona). Recárgalo "
                                "para no perder cambios.", version_actual=b.version)

    async def editar(self, borrador_id: int, contenido: str | None, version: int | None) -> dict:
        b = await self._borrador(borrador_id)
        self._editable(b, version)
        texto = (contenido or "").replace("\r\n", "\n").strip()
        if not texto:
            raise BorradorError(422, "CONTENIDO_VACIO", "El borrador no puede quedar vacío.")
        if len(texto) > settings.BORRADORES_MAX_CHARS_CONTENIDO:
            raise BorradorError(422, "CONTENIDO_DEMASIADO_LARGO",
                                f"El borrador supera los {settings.BORRADORES_MAX_CHARS_CONTENIDO} caracteres.",
                                max_caracteres=settings.BORRADORES_MAX_CHARS_CONTENIDO)
        texto += "\n"
        if texto == b.contenido:
            return {"borrador": borrador_a_dict(b, con_contenido=True)}
        b.contenido = texto
        b.version = (b.version or 1) + 1
        b.fecha_actualizacion = _ahora()
        self.bitacora.registrar(
            accion=Accion.BORRADOR_EDITADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "version": b.version, "largo": len(texto),
                     "pendientes": len(generador.pendientes(texto))},
        )
        await self.db.commit()
        return {"borrador": borrador_a_dict(b, con_contenido=True)}

    def _plantilla(self, b: BorradorDocumento):
        return obtener_plantilla(b.tipo)

    def _pdf(self, b: BorradorDocumento, consolidado: bool) -> bytes:
        fecha = (b.fecha_consolidacion or _ahora()).replace(tzinfo=timezone.utc).astimezone(ZONA)
        pie = (f"{self.empresa.razon_social} · Versión consolidada el {fecha:%d-%m-%Y}" if consolidado
               else f"{self.empresa.razon_social} · Borrador en revisión (versión {b.version})")
        try:
            return generar_pdf_borrador(b.contenido, titulo=b.titulo, pie=pie,
                                        marca_agua=None if consolidado else "BORRADOR")
        except PdfNoDisponibleError as e:
            raise BorradorError(503, "PDF_NO_DISPONIBLE", str(e))

    async def descargar(self, borrador_id: int, formato: str) -> tuple[bytes, str, str]:
        b = await self._borrador(borrador_id)
        formato = (formato or "").lower()
        if formato not in ("md", "pdf"):
            raise BorradorError(422, "FORMATO_INVALIDO", "El formato debe ser md o pdf.")
        consolidado = not b.editable
        base = f"{self._plantilla(b).nombre_corto}_{'consolidado' if consolidado else 'borrador'}-{b.id}_v{b.version}"
        if formato == "md":
            contenido, nombre, mime = b.contenido.encode("utf-8"), f"{base}.md", MIME_MD
        else:
            contenido, nombre, mime = self._pdf(b, consolidado), f"{base}.pdf", MIME_PDF
        self.bitacora.registrar(
            accion=Accion.BORRADOR_DESCARGADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "formato": formato, "version": b.version, "estado": b.estado},
        )
        await self.db.commit()
        return contenido, nombre, mime

    # ------------------------------------------------------------------ consolidar (C3)
    async def consolidar(self, borrador_id: int, version: int | None, confirmar_pendientes: bool = False) -> dict:
        from app.application.use_cases.documentos_empresa import _doc_dict, guardar_documento

        b = await self._borrador(borrador_id)
        self._editable(b, version)
        pend = generador.pendientes(b.contenido)
        if pend and not confirmar_pendientes:
            raise BorradorError(409, "CAMPOS_PENDIENTES",
                                f"El borrador tiene {len(pend)} campos por completar. Complétalos o confirma que "
                                "quieres consolidarlo así.", pendientes=pend[:MAX_PENDIENTES_LISTA], total=len(pend))
        ahora = _ahora()
        b.fecha_consolidacion = ahora
        pdf = self._pdf(b, consolidado=True)
        local = ahora.replace(tzinfo=timezone.utc).astimezone(ZONA)
        nombre = f"{self._plantilla(b).nombre_corto}_{local:%Y-%m-%d}_{b.id}.pdf"
        try:
            doc = await guardar_documento(
                self.db, empresa_id=self.empresa.id, tipo=TIPO_BORRADOR, nombre=nombre, contenido=pdf,
                mime_type=MIME_PDF, evaluacion_id=b.evaluacion_id, actor=self.cliente.actor,
            )
        except Exception:
            await self.db.rollback()
            raise
        b.estado = EstadoBorrador.CONSOLIDADO.value
        b.documento_id = doc.id
        b.fecha_actualizacion = ahora
        self.bitacora.registrar(
            accion=Accion.BORRADOR_CONSOLIDADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "version": b.version, "documento_id": doc.id, "pendientes": len(pend),
                     "confirmo_pendientes": bool(pend), "evaluacion_id": b.evaluacion_id},
        )
        await self.db.commit()
        return {"borrador": borrador_a_dict(b, con_contenido=True), "documento": _doc_dict(doc)}

    async def descartar(self, borrador_id: int) -> None:
        b = await self._borrador(borrador_id)
        detalle = {"tipo": b.tipo, "estado": b.estado, "version": b.version, "documento_id": b.documento_id}
        await self.db.delete(b)
        self.bitacora.registrar(
            accion=Accion.BORRADOR_DESCARTADO, entidad="borrador_documento", entidad_id=borrador_id,
            actor=self.cliente.actor, detalle=detalle,
        )
        await self.db.commit()
