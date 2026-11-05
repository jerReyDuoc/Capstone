"""
HU-22 · Bandeja de revisión del Oficial de Cumplimiento.

  C1  Listado filtrable de pendientes: clasificaciones que el LLM o la capa de seguridad
      tocaron (divergencias, baja confianza, bloqueos, controles sin resolver) y eventos de
      seguridad sin resolver.
  C2  Confirmar o corregir: PATCH /api/respuestas/{id}/revision (con comentario) y
      PATCH /api/seguridad/eventos/{id}/revision (ataque confirmado o falso positivo).
  C3  Cada revisión queda en el audit_log (HU-09); el historial de una respuesta se lee de ahí.

Motivos por los que una respuesta entra a la bandeja (una puede tener varios):

  seguridad         la capa anti prompt-injection bloqueó su justificación o una evidencia
  divergencia       el LLM propuso una clasificación distinta de la que declaró el usuario
  sin_resolver      sigue en 'requiere_revision' (nadie la ha cerrado)
  baja_confianza    el LLM respondió con confianza < UMBRAL_CONFIANZA (no se aplicó)
  resuelta_por_llm  el usuario no supo clasificarla (declaró 'requiere_revision') y la cerró el LLM
  concordante       el LLM respaldó al usuario con confianza suficiente. No es urgente: solo se
                    lista al pedirla (filtro motivo=concordante) para muestrear la verdad de
                    referencia también donde el modelo "acertó".

Una respuesta está PENDIENTE si nunca se revisó o si, después de revisada, otra evidencia
volvió a cambiar su clasificación (la fuente dejó de ser 'revision').

La verdad de referencia (resumen) compara la última clasificación del LLM de cada respuesta
revisada con la clasificación del oficial, con la misma función que /api/ia/metricas.

Escala: el piloto tiene pocas evaluaciones; se cargan como máximo MAX_CANDIDATAS respuestas
candidatas y se filtra y pagina en memoria (los motivos se calculan con sus evidencias).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.ai.metricas import precision_clasificacion
from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad, ResolucionEvento
from app.domain.models.evidencia import Evidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import DecisionRevision, EstadoClasificacion, FuenteClasificacion, Respuesta
from app.domain.models.usuario_admin import UsuarioAdmin
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

MAX_CANDIDATAS = 3000

SEGURIDAD = "seguridad"
DIVERGENCIA = "divergencia"
SIN_RESOLVER = "sin_resolver"
BAJA_CONFIANZA = "baja_confianza"
RESUELTA_POR_LLM = "resuelta_por_llm"
CONCORDANTE = "concordante"

# Orden de urgencia: lo primero que debe mirar el oficial
MOTIVOS = (SEGURIDAD, DIVERGENCIA, SIN_RESOLVER, BAJA_CONFIANZA, RESUELTA_POR_LLM, CONCORDANTE)
MOTIVOS_PRIORITARIOS = MOTIVOS[:-1]

ESTADOS_REVISION = ("pendiente", "revisada", "todas")
ORDENES = ("prioridad", "reciente")

_RANGO_CRITICIDAD = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
_REQ = EstadoClasificacion.REQUIERE_REVISION.value


def _sin_tildes(texto: str | None) -> str:
    base = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def rango_criticidad(criticidad: str | None) -> int:
    return _RANGO_CRITICIDAD.get(_sin_tildes(criticidad), 4)


# ===================================================================== lógica pura
@dataclass(frozen=True)
class EvidenciaLLM:
    """Lo mínimo de una evidencia para decidir los motivos (también se usa en las pruebas)."""
    id: int
    clasificacion_llm: str | None
    confianza: float | None
    fecha: date | None
    es_remediacion: bool = False
    estado_declarado: str | None = None


def ultima_del_llm(evidencias: list[EvidenciaLLM]) -> EvidenciaLLM | None:
    """La evidencia procesada por el LLM más reciente (por fecha y luego por id)."""
    procesadas = [e for e in evidencias if e.clasificacion_llm or e.confianza is not None]
    if not procesadas:
        return None
    return max(procesadas, key=lambda e: (e.fecha or date.min, e.id))


def calcular_motivos(*, declarado: str | None, estado_final: str | None, fuente: str | None,
                     evidencias: list[EvidenciaLLM], con_evento: bool, umbral: float) -> list[str]:
    """Motivos (en orden de urgencia) por los que la respuesta debe pasar por un humano."""
    motivos: set[str] = set()
    if con_evento or fuente == FuenteClasificacion.SEGURIDAD.value:
        motivos.add(SEGURIDAD)
    if estado_final == _REQ:
        motivos.add(SIN_RESOLVER)
    ultima = ultima_del_llm(evidencias)
    if ultima is not None:
        # en remediación (HU-17) lo "declarado" es lo que la empresa dice haber alcanzado
        base = ultima.estado_declarado if ultima.es_remediacion and ultima.estado_declarado else declarado
        segura = ultima.confianza is not None and ultima.confianza >= umbral
        if ultima.confianza is not None and ultima.confianza < umbral:
            motivos.add(BAJA_CONFIANZA)
        if ultima.clasificacion_llm:
            if base == _REQ:
                if segura:
                    motivos.add(RESUELTA_POR_LLM)
            elif base and ultima.clasificacion_llm != base:
                motivos.add(DIVERGENCIA)
            elif base and segura and not motivos:
                motivos.add(CONCORDANTE)
    return [m for m in MOTIVOS if m in motivos]


def esta_pendiente(clasificacion_revisada: str | None, fuente: str | None) -> bool:
    return clasificacion_revisada is None or fuente != FuenteClasificacion.REVISION.value


def es_prioritaria(motivos: list[str]) -> bool:
    return any(m in MOTIVOS_PRIORITARIOS for m in motivos)


def clave_prioridad(motivos: list[str], criticidad: str | None, fecha: datetime | date | None) -> tuple:
    primero = MOTIVOS.index(motivos[0]) if motivos else len(MOTIVOS)
    instante = fecha if isinstance(fecha, datetime) else (
        datetime.combine(fecha, datetime.min.time()) if isinstance(fecha, date) else datetime.min)
    return (primero, rango_criticidad(criticidad), -instante.timestamp() if instante != datetime.min else 0)


# ===================================================================== consultas
@dataclass
class FiltrosBandeja:
    vista: str = "clasificaciones"          # clasificaciones | eventos
    estado: str = "pendiente"               # pendiente | revisada | todas
    motivo: str | None = None               # uno de MOTIVOS (None = todos los prioritarios)
    evaluacion_id: int | None = None
    dominio_id: int | None = None
    criticidad: str | None = None
    origen: str | None = None               # solo eventos: justificacion | evidencia | tutor ...
    orden: str = "prioridad"
    page: int = 1
    size: int = 20


@dataclass
class _Fila:
    respuesta: Respuesta
    control: MatrizControl | None
    dominio: str | None
    evaluacion: Evaluacion | None
    empresa: str | None
    motivos: list[str] = field(default_factory=list)
    eventos: int = 0
    ultima: EvidenciaLLM | None = None


def _evidencias_llm(r: Respuesta) -> list[EvidenciaLLM]:
    return [EvidenciaLLM(id=e.id_evidencia, clasificacion_llm=e.clasificacion_llm, confianza=e.confianza,
                         fecha=e.fecha_procesada, es_remediacion=e.es_remediacion,
                         estado_declarado=e.estado_declarado)
            for e in (r.evidencias or [])]


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


class BandejaRevision:
    def __init__(self, session: AsyncSession, umbral_confianza: float):
        self.s = session
        self.umbral = umbral_confianza

    # ------------------------------------------------------------ clasificaciones
    async def _candidatas(self, f: FiltrosBandeja) -> list[_Fila]:
        con_llm = exists().where(Evidencia.respuesta_id == Respuesta.id,
                                 or_(Evidencia.clasificacion_llm.is_not(None), Evidencia.confianza.is_not(None)))
        con_evento = exists().where(EventoSeguridad.respuesta_id == Respuesta.id)
        q = (
            select(Respuesta, MatrizControl, Dominio.nombre_dominio, Evaluacion, Empresa.razon_social)
            .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .outerjoin(Dominio, Dominio.id == MatrizControl.dominio_id)
            .outerjoin(Evaluacion, Evaluacion.id == Respuesta.evaluacion_id)
            .outerjoin(Empresa, Empresa.id == Evaluacion.empresa_id)
            .options(selectinload(Respuesta.evidencias))
            .where(or_(
                con_llm, con_evento,
                Respuesta.fuente_clasificacion.in_([FuenteClasificacion.SEGURIDAD.value,
                                                    FuenteClasificacion.REVISION.value]),
                Respuesta.estado_clasificacion_final == _REQ,
            ))
            .order_by(Respuesta.id.desc())
            .limit(MAX_CANDIDATAS)
        )
        if f.evaluacion_id:
            q = q.where(Respuesta.evaluacion_id == f.evaluacion_id)
        if f.dominio_id:
            q = q.where(MatrizControl.dominio_id == f.dominio_id)
        filas = [_Fila(respuesta=r, control=c, dominio=d, evaluacion=ev, empresa=emp)
                 for r, c, d, ev, emp in (await self.s.execute(q)).all()]
        if f.criticidad:
            filas = [x for x in filas if rango_criticidad(x.control.criticidad if x.control else None)
                     == rango_criticidad(f.criticidad)]
        ids = [x.respuesta.id for x in filas]
        conteo_eventos: dict[int, int] = {}
        if ids:
            for rid, n in (await self.s.execute(
                select(EventoSeguridad.respuesta_id, func.count())
                .where(EventoSeguridad.respuesta_id.in_(ids)).group_by(EventoSeguridad.respuesta_id)
            )).all():
                conteo_eventos[rid] = n
        for x in filas:
            r = x.respuesta
            evs = _evidencias_llm(r)
            x.eventos = conteo_eventos.get(r.id, 0)
            x.ultima = ultima_del_llm(evs)
            x.motivos = calcular_motivos(
                declarado=r.estado_clasificacion, estado_final=r.estado_clasificacion_final,
                fuente=r.fuente_clasificacion, evidencias=evs, con_evento=x.eventos > 0, umbral=self.umbral)
        return filas

    def _item_respuesta(self, x: _Fila) -> dict:
        r, c, ev = x.respuesta, x.control, x.evaluacion
        pendiente = esta_pendiente(r.clasificacion_revisada, r.fuente_clasificacion)
        return {
            "tipo_item": "respuesta",
            "id": r.id,
            "evaluacion": {
                "id": r.evaluacion_id,
                "origen": ev.origen if ev else None,
                "estado_progreso": ev.estado_progreso if ev else None,
                "cerrada": bool(ev and ev.esta_cerrada),
                "es_prueba": bool(ev and ev.es_prueba),
                "empresa": x.empresa,
            },
            "control": {
                "id": c.id_control if c else r.matriz_controles_id_control,
                "codigo": c.codigo_control if c else None,
                "pregunta": c.pregunta_evaluacion if c else None,
                "criticidad": c.criticidad if c else None,
                "dominio_id": c.dominio_id if c else None,
                "dominio": x.dominio,
            },
            "declarado": r.estado_clasificacion,
            "estado_final": r.estado_clasificacion_final,
            "fuente": r.fuente_clasificacion,
            "llm": ({"clasificacion": x.ultima.clasificacion_llm, "confianza": x.ultima.confianza,
                     "fecha": _iso(x.ultima.fecha), "evidencia_id": x.ultima.id,
                     "bajo_umbral": x.ultima.confianza is not None and x.ultima.confianza < self.umbral}
                    if x.ultima else None),
            "motivos": x.motivos,
            "eventos_seguridad": x.eventos,
            "pendiente": pendiente,
            "revision": ({"clasificacion": r.clasificacion_revisada, "decision": r.decision_revision,
                          "fecha": _iso(r.fecha_revision), "comentario": r.comentario_revision,
                          "vigente": not pendiente}
                         if r.clasificacion_revisada else None),
            "fecha_referencia": _iso(r.fecha_validacion or (x.ultima.fecha if x.ultima else None)),
        }

    @staticmethod
    def _filtrar_estado(filas: list[_Fila], estado: str) -> list[_Fila]:
        if estado == "pendiente":
            return [x for x in filas if esta_pendiente(x.respuesta.clasificacion_revisada, x.respuesta.fuente_clasificacion)]
        if estado == "revisada":
            return [x for x in filas if not esta_pendiente(x.respuesta.clasificacion_revisada, x.respuesta.fuente_clasificacion)]
        return filas

    async def clasificaciones(self, f: FiltrosBandeja) -> tuple[list[dict], int, dict]:
        filas = self._filtrar_estado(await self._candidatas(f), f.estado)
        # Las revisadas se muestran siempre (ya pasaron por la bandeja); entre las pendientes,
        # solo las que tienen un motivo prioritario, salvo que se pida otro motivo.
        conteo = {m: sum(1 for x in filas if m in x.motivos) for m in MOTIVOS}
        if f.motivo:
            filas = [x for x in filas if f.motivo in x.motivos]
        elif f.estado == "pendiente":
            filas = [x for x in filas if es_prioritaria(x.motivos)]
        else:
            filas = [x for x in filas if x.motivos or x.respuesta.clasificacion_revisada]
        if f.orden == "reciente":
            filas.sort(key=lambda x: (x.respuesta.fecha_validacion or date.min, x.respuesta.id), reverse=True)
        else:
            filas.sort(key=lambda x: clave_prioridad(
                x.motivos, x.control.criticidad if x.control else None,
                x.respuesta.fecha_validacion))
        total = len(filas)
        pagina = filas[(f.page - 1) * f.size: f.page * f.size]
        return [self._item_respuesta(x) for x in pagina], total, conteo

    # ------------------------------------------------------------ eventos
    def _q_eventos(self, f: FiltrosBandeja):
        q = select(EventoSeguridad, MatrizControl.codigo_control, MatrizControl.pregunta_evaluacion).outerjoin(
            MatrizControl, MatrizControl.id_control == EventoSeguridad.matriz_control_id)
        if f.estado == "pendiente":
            q = q.where(EventoSeguridad.revisado.is_(False))
        elif f.estado == "revisada":
            q = q.where(EventoSeguridad.revisado.is_(True))
        if f.evaluacion_id:
            q = q.where(EventoSeguridad.evaluacion_id == f.evaluacion_id)
        if f.origen:
            q = q.where(EventoSeguridad.origen == f.origen)
        return q

    @staticmethod
    def _item_evento(ev: EventoSeguridad, codigo: str | None, pregunta: str | None) -> dict:
        return {
            "tipo_item": "evento",
            "id": ev.id_evento,
            "fecha": _iso(ev.fecha),
            "tipo": ev.tipo,
            "origen": ev.origen,
            "evaluacion_id": ev.evaluacion_id,
            "respuesta_id": ev.respuesta_id,
            "evidencia_id": ev.evidencia_id,
            "control": {"id": ev.matriz_control_id, "codigo": codigo, "pregunta": pregunta}
            if ev.matriz_control_id else None,
            "extracto": ev.extracto,
            "pendiente": not ev.revisado,
            "revision": ({"resolucion": ev.resolucion, "comentario": ev.comentario_revision,
                          "fecha": _iso(ev.fecha_revision)} if ev.revisado else None),
        }

    async def eventos(self, f: FiltrosBandeja) -> tuple[list[dict], int]:
        q = self._q_eventos(f)
        total = (await self.s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        filas = (await self.s.execute(
            q.order_by(EventoSeguridad.fecha.desc(), EventoSeguridad.id_evento.desc())
            .offset((f.page - 1) * f.size).limit(f.size))).all()
        return [self._item_evento(ev, cod, preg) for ev, cod, preg in filas], total

    async def eventos_pendientes(self, f: FiltrosBandeja) -> int:
        q = self._q_eventos(FiltrosBandeja(estado="pendiente", evaluacion_id=f.evaluacion_id))
        return (await self.s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()

    async def bandeja(self, f: FiltrosBandeja) -> dict:
        cuenta_f = FiltrosBandeja(estado="pendiente", evaluacion_id=f.evaluacion_id,
                                  dominio_id=f.dominio_id, criticidad=f.criticidad)
        pendientes = self._filtrar_estado(await self._candidatas(cuenta_f), "pendiente")
        conteo_pend = {m: sum(1 for x in pendientes if m in x.motivos) for m in MOTIVOS}
        clasif_pend = sum(1 for x in pendientes if es_prioritaria(x.motivos))
        eventos_pend = await self.eventos_pendientes(f)
        if f.vista == "eventos":
            items, total = await self.eventos(f)
        else:
            items, total, _ = await self.clasificaciones(f)
        return {
            "vista": f.vista, "estado": f.estado, "motivo": f.motivo,
            "items": items, "total": total, "page": f.page, "size": f.size,
            "pages": (total + f.size - 1) // f.size if f.size else 0,
            "pendientes": {"clasificaciones": clasif_pend, "eventos": eventos_pend,
                           "por_motivo": conteo_pend},
            "umbral_confianza": self.umbral,
        }

    # ------------------------------------------------------------ detalle
    async def detalle_respuesta(self, respuesta_id: int) -> dict | None:
        q = (
            select(Respuesta, MatrizControl, Dominio.nombre_dominio, Evaluacion, Empresa.razon_social)
            .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .outerjoin(Dominio, Dominio.id == MatrizControl.dominio_id)
            .outerjoin(Evaluacion, Evaluacion.id == Respuesta.evaluacion_id)
            .outerjoin(Empresa, Empresa.id == Evaluacion.empresa_id)
            .options(selectinload(Respuesta.evidencias))
            .where(Respuesta.id == respuesta_id)
        )
        fila = (await self.s.execute(q)).first()
        if fila is None:
            return None
        r, c, d, ev, emp = fila
        eventos = list((await self.s.execute(
            select(EventoSeguridad).where(EventoSeguridad.respuesta_id == r.id)
            .order_by(EventoSeguridad.fecha.desc()))).scalars().all())
        evs = _evidencias_llm(r)
        x = _Fila(respuesta=r, control=c, dominio=d, evaluacion=ev, empresa=emp, eventos=len(eventos),
                  ultima=ultima_del_llm(evs))
        x.motivos = calcular_motivos(declarado=r.estado_clasificacion, estado_final=r.estado_clasificacion_final,
                                     fuente=r.fuente_clasificacion, evidencias=evs, con_evento=bool(eventos),
                                     umbral=self.umbral)
        item = self._item_respuesta(x)
        item["justificacion_usuario"] = r.justificacion_usuario
        if c is not None:
            item["control"].update({"obligacion": c.obligacion, "evidencia_esperada": c.evidencia_esperada,
                                    "articulo_referencia": c.articulo_referencia})
        item["evidencias"] = [
            {"id": e.id_evidencia, "nombre_archivo": e.nombre_archivo, "origen": e.origen,
             "estado_validacion": e.estado_validacion, "estado_declarado": e.estado_declarado,
             "clasificacion_llm": e.clasificacion_llm, "confianza": e.confianza,
             "justificacion_llm": e.justificacion_llm, "errores": e.errores_validacion or [],
             "fecha_subida": _iso(e.fecha_subida), "fecha_procesada": _iso(e.fecha_procesada),
             "eliminada": e.eliminada}
            for e in sorted(r.evidencias or [], key=lambda e: (e.fecha_procesada or date.min, e.id_evidencia),
                            reverse=True)
        ]
        item["eventos"] = [self._item_evento(e, c.codigo_control if c else None,
                                             c.pregunta_evaluacion if c else None) for e in eventos]
        item["historial"] = await self.historial(r.id)
        item["opciones"] = EstadoClasificacion.resolutivos()
        return item

    async def historial(self, respuesta_id: int) -> list[dict]:
        """C3: las revisiones de la respuesta, leídas del audit_log (lo inmutable manda)."""
        filas, _ = await BitacoraRepository(self.s).listar(
            entidad="respuestas", entidad_id=respuesta_id, accion=Accion.RESPUESTA_REVISADA, size=50)
        ids_admin = {f.actor_id for f in filas if f.actor_id}
        correos: dict[int, str] = {}
        if ids_admin:
            correos = {a.id: a.email for a in (await self.s.execute(
                select(UsuarioAdmin).where(UsuarioAdmin.id.in_(ids_admin)))).scalars().all()}
        return [{
            "audit_id": f.id, "fecha": _iso(f.fecha), "actor_rol": f.actor_rol, "actor_id": f.actor_id,
            "revisor": correos.get(f.actor_id) if f.actor_id else None,
            "anterior": (f.detalle or {}).get("estado_final_anterior"),
            "nueva": (f.detalle or {}).get("estado_final_nuevo"),
            "decision": (f.detalle or {}).get("decision"),
            "clasificacion_llm": (f.detalle or {}).get("clasificacion_llm"),
            "con_comentario": bool((f.detalle or {}).get("comentario_huella")),
        } for f in filas]

    # ------------------------------------------------------------ verdad de referencia
    async def resumen(self) -> dict:
        revisadas = list((await self.s.execute(
            select(Respuesta).options(selectinload(Respuesta.evidencias))
            .where(Respuesta.clasificacion_revisada.is_not(None))
        )).scalars().all())
        pares = []
        confirmadas = corregidas = 0
        for r in revisadas:
            if r.decision_revision == DecisionRevision.CONFIRMADA.value:
                confirmadas += 1
            elif r.decision_revision == DecisionRevision.CORREGIDA.value:
                corregidas += 1
            ultima = ultima_del_llm(_evidencias_llm(r))
            if ultima and ultima.clasificacion_llm:
                pares.append((ultima.clasificacion_llm, r.clasificacion_revisada))
        eventos = dict((await self.s.execute(
            select(EventoSeguridad.resolucion, func.count()).where(EventoSeguridad.revisado.is_(True))
            .group_by(EventoSeguridad.resolucion))).all())
        confirmados = eventos.get(ResolucionEvento.ATAQUE_CONFIRMADO.value, 0)
        falsos = eventos.get(ResolucionEvento.FALSO_POSITIVO.value, 0)
        return {
            "revisadas": len(revisadas),
            "confirmadas": confirmadas,
            "corregidas": corregidas,
            "precision_llm": precision_clasificacion(pares),
            "eventos": {
                "ataques_confirmados": confirmados,
                "falsos_positivos": falsos,
                "sin_veredicto": sum(n for k, n in eventos.items() if k is None),
                "precision_deteccion": round(confirmados / (confirmados + falsos), 3)
                if confirmados + falsos else None,
            },
            "umbral_confianza": self.umbral,
        }
