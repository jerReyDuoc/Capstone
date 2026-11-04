"""
HU-24 · Mantenedor de la matriz normativa (solo admin de Therion Labs).

Flujo:
  1. El admin crea un BORRADOR (copia de la versión vigente, o de una anterior para volver
     a ella). Mientras edita, nadie más lo ve: el cuestionario sigue con la vigente.
  2. Agrega, modifica, retira o restaura controles, brechas, rutas formativas y preguntas
     de filtro, y fija las reglas de aplicabilidad de cada control (el árbol).
  3. Revisa los errores, las advertencias y las diferencias con la vigente.
  4. PUBLICA con una etiqueta ("2026.2") y una nota de cambio. En una transacción: las
     tablas del catálogo quedan iguales al borrador, el borrador pasa a "publicada" y la
     anterior a "reemplazada" (su contenido ya no cambia).

Criterio 2: cada evaluación guarda al completarse la versión con que se respondió
(evaluacion.matriz_version_id); su informe, plan formativo y recálculo por remediación
leen esa versión. Las evaluaciones en curso pasan a la nueva al publicar.

Criterio 3: cada operación queda en el audit log (HU-09) en la misma transacción, también
los intentos de publicar rechazados.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.core.config import settings
from app.domain.matriz import contenido as C
from app.domain.matriz import edicion as E
from app.domain.matriz.diferencias import conteo, diferencias
from app.domain.matriz.validacion import errores, validar
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.matriz_version import (
    ESTADO_BORRADOR, ESTADO_PUBLICADA, ESTADO_REEMPLAZADA, MatrizVersion,
)
from app.domain.models.usuario_admin import UsuarioAdmin
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository
from app.infrastructure.repositories.matriz_repository import MatrizRepository

ENTIDAD_AUDIT = "matriz_version"
PATRON_ETIQUETA = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,29}$")
NOTA_MINIMA = 10
OPERACIONES = ("crear", "actualizar", "retirar", "restaurar", "aplicabilidad")


class MatrizError(Exception):
    def __init__(self, codigo: str, mensaje: str, status_code: int = 422, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(fecha: datetime | None) -> str | None:
    return fecha.isoformat() if fecha else None


def invalidar_caches() -> None:
    """Este proceso vuelve a leer la matriz en la próxima petición (los demás, en ≤ 15 s)."""
    from app.infrastructure.cache import arbol_aplicabilidad, catalogo_controles

    catalogo_controles.invalidar()
    arbol_aplicabilidad.invalidar()


class MantenedorMatrizUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MatrizRepository(session)
        self.bitacora = BitacoraRepository(session)

    # ================================================================== lectura
    async def vigente(self) -> MatrizVersion:
        """La versión publicada. Si la BD aún no tiene ninguna (BD nueva o sin migrar la
        semilla), se registra una con lo que reflejan hoy las tablas."""
        v = await self.repo.publicada()
        if v is not None:
            return v
        from app.application.informes.carga import version_matriz_vigente

        contenido = await self.repo.contenido_desde_tablas()
        ahora = _ahora()
        etiqueta = (settings.MATRIZ_VERSION or "2026.1").strip()[:30]
        v = MatrizVersion(
            etiqueta=etiqueta, estado=ESTADO_PUBLICADA, contenido=contenido, huella=C.huella(contenido),
            # mismo texto que ya imprimen los informes (cálculo de HU-21)
            version_texto=await version_matriz_vigente(self.session),
            nota_cambio="Versión inicial registrada desde las tablas del catálogo (HU-24).",
            revision=1, fecha_creacion=ahora, fecha_actualizacion=ahora, fecha_publicacion=ahora,
        )
        self.session.add(v)
        await self.session.flush()
        return v

    async def estado(self) -> dict:
        vigente = await self.vigente()
        borrador = await self.repo.borrador()
        usos = await self.repo.evaluaciones_por_version()
        await self.session.commit()
        return {
            "vigente": await self._ficha(vigente, usos),
            "borrador": await self._ficha_borrador(borrador, vigente) if borrador else None,
            "etiqueta_sugerida": await self._siguiente_etiqueta(),
        }

    async def versiones(self) -> list[dict]:
        await self.vigente()
        usos = await self.repo.evaluaciones_por_version()
        filas = [await self._ficha(v, usos) for v in await self.repo.listar() if v.estado != ESTADO_BORRADOR]
        await self.session.commit()
        return filas

    async def version(self, version_id: int) -> dict:
        v = await self.repo.obtener(version_id)
        if v is None or v.estado == ESTADO_BORRADOR:
            raise MatrizError("NO_ENCONTRADO", "Versión no encontrada.", 404)
        anterior = (await self.session.execute(
            select(MatrizVersion).where(MatrizVersion.id < v.id, MatrizVersion.estado != ESTADO_BORRADOR)
            .order_by(MatrizVersion.id.desc()).limit(1)
        )).scalar_one_or_none()
        usos = await self.repo.evaluaciones_por_version()
        return {
            **await self._ficha(v, usos),
            "contenido": v.contenido,
            "arbol": C.arbol(v.contenido).como_dict(),
            "anterior": {"id": anterior.id, "etiqueta": anterior.etiqueta} if anterior else None,
            "diferencias": diferencias(anterior.contenido, v.contenido) if anterior else None,
        }

    async def borrador(self) -> dict:
        b = await self.repo.borrador()
        if b is None:
            raise MatrizError("SIN_BORRADOR", "No hay un borrador en edición. Crea uno desde la versión vigente.", 404)
        vigente = await self.vigente()
        return {
            **await self._ficha_borrador(b, vigente),
            "contenido": b.contenido,
            "arbol": C.arbol(b.contenido).como_dict(),
        }

    # ================================================================== borrador
    async def crear_borrador(self, actor: Actor, desde_version_id: int | None = None) -> dict:
        if await self.repo.borrador() is not None:
            raise MatrizError("BORRADOR_EXISTE", "Ya hay un borrador en edición: continúalo o descártalo.", 409)
        vigente = await self.vigente()
        origen = vigente
        if desde_version_id is not None and desde_version_id != vigente.id:
            origen = await self.repo.obtener(desde_version_id)
            if origen is None or origen.estado == ESTADO_BORRADOR:
                raise MatrizError("NO_ENCONTRADO", "La versión de origen no existe.", 404)
        contenido = _completar_con(C.copiar(origen.contenido), vigente.contenido) if origen is not vigente \
            else C.copiar(vigente.contenido)
        ahora = _ahora()
        b = MatrizVersion(
            estado=ESTADO_BORRADOR, contenido=contenido, base_version_id=vigente.id, revision=1,
            creado_por_admin_id=actor.id, fecha_creacion=ahora, fecha_actualizacion=ahora,
        )
        self.session.add(b)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise MatrizError("BORRADOR_EXISTE", "Otro administrador acaba de crear un borrador.", 409)
        self.bitacora.registrar(
            accion=Accion.MATRIZ_BORRADOR_CREADO, entidad=ENTIDAD_AUDIT, entidad_id=b.id, actor=actor,
            detalle={"desde_version_id": origen.id, "desde_etiqueta": origen.etiqueta,
                     "base_version_id": vigente.id},
        )
        await self.session.commit()
        return await self.borrador()

    async def editar(self, actor: Actor, operacion: str, entidad: str, item_id: int | None,
                     datos: dict | None, revision: int | None) -> dict:
        if operacion not in OPERACIONES:
            raise MatrizError("OPERACION_INVALIDA", f"Operación inválida: {operacion}.", 400)
        b = await self._borrador_para_editar(revision)
        contenido = C.copiar(b.contenido)
        try:
            if operacion == "crear":
                cambio = E.crear(contenido, entidad, datos or {})
            elif operacion == "actualizar":
                cambio = E.actualizar(contenido, entidad, int(item_id), datos or {})
            elif operacion == "retirar":
                cambio = E.retirar(contenido, entidad, int(item_id))
            elif operacion == "restaurar":
                cambio = E.restaurar(contenido, entidad, int(item_id))
            else:
                datos = datos or {}
                cambio = E.fijar_aplicabilidad(contenido, int(item_id), bool(datos.get("aplica_siempre")),
                                               list(datos.get("filtros") or []))
        except E.EdicionError as e:
            raise MatrizError(e.codigo, str(e), e.status_code, **e.extra)
        b.contenido = C.normalizar(contenido)   # objeto nuevo: SQLAlchemy detecta el cambio del JSON
        b.revision = (b.revision or 1) + 1
        b.fecha_actualizacion = _ahora()
        detalle = cambio.como_detalle()
        detalle["revision"] = b.revision
        if operacion == "aplicabilidad":
            detalle["operacion"] = "reglas"
        self.bitacora.registrar(accion=Accion.MATRIZ_BORRADOR_EDITADO, entidad=ENTIDAD_AUDIT, entidad_id=b.id,
                                actor=actor, detalle=detalle)
        await self.session.commit()
        elemento = C.por_id(b.contenido, entidad).get(cambio.id)
        return {"cambio": detalle, "revision": b.revision, "elemento": elemento}

    async def descartar(self, actor: Actor, revision: int | None) -> dict:
        b = await self._borrador_para_editar(revision)
        vigente = await self.vigente()
        dif = conteo(diferencias(vigente.contenido, b.contenido))
        self.bitacora.registrar(
            accion=Accion.MATRIZ_BORRADOR_DESCARTADO, entidad=ENTIDAD_AUDIT, entidad_id=b.id, actor=actor,
            detalle={"revision": b.revision, "cambios_descartados": dif},
        )
        await self.session.delete(b)
        await self.session.commit()
        return {"descartado": True}

    # ================================================================== publicación
    async def publicar(self, actor: Actor, etiqueta: str, nota: str, revision: int | None) -> dict:
        b = await self._borrador_para_editar(revision)
        vigente = await self.vigente()
        etiqueta = (etiqueta or "").strip()
        nota = (nota or "").strip()

        async def rechazar(codigo: str, mensaje: str, status: int = 422, **extra):
            self.bitacora.registrar(
                accion=Accion.MATRIZ_PUBLICACION_RECHAZADA, entidad=ENTIDAD_AUDIT, entidad_id=b.id, actor=actor,
                resultado=RESULTADO_RECHAZADO,
                detalle={"motivo": codigo, "etiqueta": etiqueta[:30] or None, "revision": b.revision,
                         **({"errores": len(extra.get("problemas", []))} if "problemas" in extra else {})},
            )
            await self.session.commit()
            raise MatrizError(codigo, mensaje, status, **extra)

        if not PATRON_ETIQUETA.match(etiqueta):
            await rechazar("ETIQUETA_INVALIDA", "La etiqueta debe tener de 1 a 30 caracteres: letras, números, "
                                                "punto, guion o guion bajo (ejemplo: 2026.2).", campo="etiqueta")
        existe = (await self.session.execute(
            select(MatrizVersion.id).where(MatrizVersion.etiqueta == etiqueta)
        )).scalar_one_or_none()
        if existe is not None:
            await rechazar("ETIQUETA_DUPLICADA", f"Ya hay una versión {etiqueta}. Usa otra etiqueta.", 409,
                           campo="etiqueta")
        if len(nota) < NOTA_MINIMA or len(nota) > 1000:
            await rechazar("NOTA_INVALIDA", f"Describe el cambio normativo en {NOTA_MINIMA} a 1000 caracteres "
                                            "(queda en el historial y en el audit log).", campo="nota_cambio")
        if b.base_version_id is not None and b.base_version_id != vigente.id:
            await rechazar("BASE_DESACTUALIZADA", "Se publicó otra versión después de crear este borrador. "
                                                  "Descártalo y crea uno nuevo desde la vigente.", 409)
        dif = diferencias(vigente.contenido, b.contenido)
        if dif["total"] == 0:
            await rechazar("SIN_CAMBIOS", "El borrador es igual a la versión vigente: no hay nada que publicar.", 409)
        problemas = validar(b.contenido)
        if errores(problemas):
            await rechazar("BORRADOR_CON_ERRORES", "El borrador tiene errores que impiden publicarlo.", 422,
                           problemas=[p.como_dict() for p in problemas])

        # --- todo lo que sigue va en una sola transacción
        contenido_real = await self.repo.aplicar(b.contenido)
        huella = C.huella(contenido_real)
        ahora = _ahora()
        vigente.estado = ESTADO_REEMPLAZADA
        vigente.fecha_actualizacion = ahora
        await self.session.flush()   # antes de que el borrador pase a publicada (índice único)
        b.estado = ESTADO_PUBLICADA
        b.etiqueta = etiqueta
        b.contenido = contenido_real
        b.huella = huella
        b.version_texto = C.version_texto(etiqueta, huella)
        b.nota_cambio = nota
        b.publicado_por_admin_id = actor.id
        b.fecha_publicacion = ahora
        b.fecha_actualizacion = ahora
        self.bitacora.registrar(
            accion=Accion.MATRIZ_PUBLICADA, entidad=ENTIDAD_AUDIT, entidad_id=b.id, actor=actor,
            detalle={"etiqueta": etiqueta, "version_texto": b.version_texto, "huella": huella,
                     "reemplaza_a": {"id": vigente.id, "etiqueta": vigente.etiqueta},
                     "cambios": conteo(dif), "advertencias": len(problemas), "revision": b.revision,
                     "nota_cambio": nota[:300].replace("@", "(at)")},
        )
        await self.session.commit()
        invalidar_caches()
        usos = await self.repo.evaluaciones_por_version()
        return {**await self._ficha(b, usos), "diferencias": dif}

    async def revisar(self) -> dict:
        """Errores, advertencias y diferencias del borrador (sin publicar)."""
        b = await self.repo.borrador()
        if b is None:
            raise MatrizError("SIN_BORRADOR", "No hay un borrador en edición.", 404)
        vigente = await self.vigente()
        problemas = validar(b.contenido)
        return {
            "revision": b.revision,
            "problemas": [p.como_dict() for p in problemas],
            "errores": len(errores(problemas)),
            "advertencias": len(problemas) - len(errores(problemas)),
            "diferencias": diferencias(vigente.contenido, b.contenido),
            "puede_publicar": not errores(problemas),
        }

    # ================================================================== apoyo
    async def _borrador_para_editar(self, revision: int | None) -> MatrizVersion:
        b = await self.repo.borrador()
        if b is None:
            raise MatrizError("SIN_BORRADOR", "No hay un borrador en edición. Crea uno desde la versión vigente.", 404)
        if revision is not None and int(revision) != int(b.revision or 1):
            raise MatrizError(
                "BORRADOR_CAMBIADO",
                "Otro administrador modificó el borrador mientras lo editabas. Recarga para ver sus cambios.",
                409, revision_actual=b.revision,
            )
        return b

    async def _admin(self, admin_id: int | None) -> dict | None:
        if not admin_id:
            return None
        a = await self.session.get(UsuarioAdmin, admin_id)
        return {"id": admin_id, "email": a.email if a else None}

    async def _ficha(self, v: MatrizVersion, usos: dict[int, int]) -> dict:
        return {
            "id": v.id, "etiqueta": v.etiqueta, "estado": v.estado, "version_texto": v.version_texto,
            "huella": v.huella, "nota_cambio": v.nota_cambio,
            "fecha_publicacion": _iso(v.fecha_publicacion), "fecha_creacion": _iso(v.fecha_creacion),
            "publicado_por": await self._admin(v.publicado_por_admin_id),
            "evaluaciones": usos.get(v.id, 0),
            "resumen": C.resumen(v.contenido),
        }

    async def _ficha_borrador(self, b: MatrizVersion, vigente: MatrizVersion) -> dict:
        dif = diferencias(vigente.contenido, b.contenido)
        problemas = validar(b.contenido)
        return {
            "id": b.id, "estado": b.estado, "revision": b.revision,
            "base_version_id": b.base_version_id, "base_desactualizada": b.base_version_id not in (None, vigente.id),
            "fecha_creacion": _iso(b.fecha_creacion), "fecha_actualizacion": _iso(b.fecha_actualizacion),
            "creado_por": await self._admin(b.creado_por_admin_id),
            "cambios": dif["total"], "conteo_cambios": conteo(dif), "diferencias": dif,
            "errores": len(errores(problemas)), "advertencias": len(problemas) - len(errores(problemas)),
            "resumen": C.resumen(b.contenido),
        }

    async def _siguiente_etiqueta(self) -> str:
        """2026.1 → 2026.2; si la última no termina en número, <año>.<n+1>."""
        etiquetas = [e for e in (await self.session.execute(
            select(MatrizVersion.etiqueta).where(MatrizVersion.etiqueta.is_not(None))
        )).scalars().all()]
        anio = str(_ahora().year)
        usados = set(etiquetas)
        n = 1 + sum(1 for e in etiquetas if e.startswith(f"{anio}."))
        while f"{anio}.{n}" in usados:
            n += 1
        return f"{anio}.{n}"


def _completar_con(origen: dict, vigente: dict) -> dict:
    """
    Borrador desde una versión ANTERIOR: lo que se agregó después sigue existiendo en las
    tablas (no se borra nunca), así que entra al borrador como retirado. Publicar ese
    borrador "vuelve" a la versión anterior sin perder la historia.
    """
    for entidad in C.ORDEN_ENTIDADES:
        ids = {int(x["id"]) for x in origen.get(entidad, [])}
        for x in vigente.get(entidad, []):
            if int(x["id"]) not in ids:
                copia = dict(x)
                copia[C.ENTIDADES[entidad]["activo"]] = False
                origen.setdefault(entidad, []).append(copia)
    origen["dominios"] = C.copiar(vigente).get("dominios", origen.get("dominios", []))
    return C.normalizar(origen)
