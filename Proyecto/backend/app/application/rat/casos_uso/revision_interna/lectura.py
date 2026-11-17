"""Revisión interna: lectura del estado, rechazos, historial de revisiones y diferencias entre versiones."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.application.rat import armado_informe_rat as I
from app.application.rat.casos_uso.revision_interna.comun import (
    Contexto, RevisionError, _hoy_chile, _iso, _sin_preguntas, catalogo_criterios, observacion_vista,
)
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.rat_revision import ABIERTA, EN_CURSO, RatObservacion, RatRevision, ConfiguracionRevisionRat
from app.domain.rat import lista_verificacion as R


class LecturaMixin:
    """Depende de los atributos que fija RevisionInternaCasos.__init__ (db, repo, informes, bitacora, ...)."""

    # ================================================================ lectura
    async def _contexto(self) -> Contexto:
        from app.application.rat.casos_uso.registro_actividades_casos import RegistroActividadesCasos

        inf = await self.informes.armar()
        version_mapa, elementos, flujos = await RegistroActividadesCasos(self.db, self.cliente)._mapa()
        objs = R.objetos(list(inf.actividades), elementos, flujos)
        return Contexto(inf, version_mapa, objs, {o.clave: o for o in objs})

    async def _en_curso(self, bloquear: bool = False) -> RatRevision | None:
        return await self.repo.revision_en_curso(self.empresa_id, bloquear=bloquear)

    async def _revision(self, revision_id: int) -> RatRevision:
        r = await self.repo.revision(revision_id)
        if r is None or r.empresa_id != self.empresa_id:          # lo ajeno no existe (404)
            raise RevisionError(404, "REVISION_NO_ENCONTRADA", "No encontramos esa revisión de tu registro.")
        return r

    async def _revisadas(self, limite: int = 50) -> list[RatRevision]:
        return await self.repo.revisiones_revisadas(self.empresa_id, limite)

    async def _observaciones(self, revision_id: int | None = None) -> list[RatObservacion]:
        return await self.repo.observaciones(self.empresa_id, revision_id)

    async def _abiertas(self) -> int:
        return await self.repo.observaciones_abiertas(self.empresa_id)

    async def _config(self) -> ConfiguracionRevisionRat | None:
        return await self.repo.config(self.empresa_id)

    @staticmethod
    def _config_vista(c: ConfiguracionRevisionRat | None) -> dict:
        return {"plazo_meses": c.plazo_meses if c else settings.REVISION_RAT_PLAZO_MESES,
                "aviso_dias": c.aviso_dias if c else settings.REVISION_RAT_AVISO_DIAS,
                "recordatorio_correo": c.recordatorio_correo if c else True,
                "ultimo_recordatorio": _iso(c.ultimo_recordatorio) if c else None,
                "personalizada": c is not None}

    async def _primera_vigencia(self) -> date | None:
        f = await self.repo.primera_vigencia(self.empresa_id)
        return _hoy_chile(f) if f else None

    async def _periodicidad(self, ultima: RatRevision | None, cfg: dict) -> dict:
        est = R.periodicidad(_hoy_chile(), _hoy_chile(ultima.fecha_revision) if ultima else None,
                             await self._primera_vigencia(), cfg["plazo_meses"], cfg["aviso_dias"])
        return {**est, **cfg, "ultima_revision": _iso(ultima.fecha_revision) if ultima else None}

    def _vista_revision(self, r: RatRevision, contar: dict | None = None) -> dict:
        return {
            "id": r.id, "numero": r.numero, "estado": r.estado, "fecha_inicio": _iso(r.fecha_inicio),
            "fecha_revision": _iso(r.fecha_revision), "revisor": r.revisor_nombre, "cargo": r.revisor_cargo,
            "conclusion": r.conclusion, "version_rat": r.version_rat, "huella": r.huella,
            "huella_legible": I.huella_legible(r.huella) if r.huella else None, "version_mapa": r.version_mapa,
            "resumen": contar if contar is not None else {k: v for k, v in (r.resumen or {}).items() if k != "versiones"},
            "informe_id": r.informe_id,
        }

    async def estado(self) -> dict:
        """Todo lo que muestra el modo de revisión: lista consolidada, observaciones, requisitos y periodicidad."""
        ctx = await self._contexto()
        en_curso = await self._en_curso()
        revisadas = await self._revisadas()
        ultima = revisadas[0] if revisadas else None
        observaciones = await self._observaciones(en_curso.id) if en_curso else []
        abiertas_previas = [o for o in await self._observaciones() if o.estado == ABIERTA
                            and (en_curso is None or o.revision_id != en_curso.id)]
        consolidados = R.consolidar(ctx.objetos, en_curso.verificaciones if en_curso else {})
        obs_vistas = [observacion_vista(o, ctx.por_clave) for o in [*observaciones, *abiertas_previas]]
        resumen = R.resumen(consolidados, obs_vistas)
        abiertas = sum(1 for o in obs_vistas if o["estado"] == ABIERTA)
        req = R.requisitos(consolidados, abiertas, len(ctx.inf.actividades))
        cfg = self._config_vista(await self._config())
        marca = ctx.inf.revision
        return {
            "revision": self._vista_revision(en_curso, resumen) if en_curso else None,
            "registro": {
                "huella": ctx.inf.huella, "huella_legible": I.huella_legible(ctx.inf.huella),
                "borrador": ctx.inf.borrador, "motivos_borrador": list(ctx.inf.motivos_borrador),
                "actividades": len(ctx.inf.actividades), "version_mapa": ctx.version_mapa,
                "version_siguiente": await self._version_para(ctx.inf.huella),
                # ¿La versión actual ya tiene constancia? ¿Cambió desde la última revisada?
                "revisada": I.marca_dict(marca),
                "cambio_desde_ultima": bool(ultima and ultima.huella != ctx.inf.huella),
            },
            "objetos": _sin_preguntas(consolidados),
            "observaciones": obs_vistas,
            "resumen": resumen,
            "requisitos": req,
            "criterios": catalogo_criterios(),
            "periodicidad": await self._periodicidad(ultima, cfg),
            "revisadas": [self._vista_revision(r) for r in revisadas],
            "ultima": self._vista_revision(ultima) if ultima else None,
            "versiones": await self._versiones_disponibles(),
            "limites": {"paquetes_dia": settings.REVISION_RAT_PAQUETES_DIA,
                        "correos_dia": settings.REVISION_RAT_CORREOS_DIA,
                        "paquete_correo_mb": settings.REVISION_RAT_PAQUETE_CORREO_MB,
                        "paquete_verificar_mb": settings.REVISION_RAT_PAQUETE_VERIFICAR_MB},
            "correo_habilitado": settings.CORREO_MODO != "desactivado",
            "revisor_sugerido": self.nombre_usuario,
        }

    async def _version_para(self, huella: str) -> int:
        ultima = await self.repo.ultimo_informe(self.empresa_id)
        if ultima is None:
            return 1
        return ultima.version_rat + (0 if ultima.huella == huella else 1)

    # ================================================================ rechazos (quedan en el audit_log)
    async def _rechazar(self, motivo: str, error: RevisionError, **detalle) -> RevisionError:
        await self.db.rollback()
        self.bitacora.registrar(accion=Accion.REVISION_RAT_MARCA_RECHAZADA, entidad="rat_revision", entidad_id=None,
                                actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": motivo, **detalle})
        await self.db.commit()
        return error

    # ================================================================ historial de revisiones
    async def detalle(self, revision_id: int) -> dict:
        r = await self._revision(revision_id)
        if r.estado == EN_CURSO:
            return await self.estado()
        obs = await self._observaciones(r.id)
        return {"revision": self._vista_revision(r), "objetos": r.lista or [],
                "observaciones": [observacion_vista(o) for o in obs], "criterios": catalogo_criterios()}

    # ================================================================ diferencias entre versiones (C4)
    async def _versiones_disponibles(self) -> list[dict]:
        filas = await self.repo.informes_recientes(self.empresa_id, 200)
        revisadas = {(r.version_rat, r.huella): r for r in (await self._revisadas(200))}
        por_version: dict[int, dict] = {}
        for f in filas:                                     # la emisión más reciente de cada versión
            if f.version_rat in por_version:
                continue
            rv = revisadas.get((f.version_rat, f.huella))
            por_version[f.version_rat] = {
                "version": f.version_rat, "fecha": _iso(f.fecha), "borrador": f.borrador, "codigo": f.codigo,
                "actividades": f.actividades, "revisada": bool(rv),
                "revision": {"numero": rv.numero, "fecha": _iso(rv.fecha_revision)} if rv else None}
        for (v, _h), rv in revisadas.items():                # una revisada sin emisión (si el informe no se emitió)
            por_version.setdefault(v, {"version": v, "fecha": _iso(rv.fecha_revision), "borrador": False,
                                       "codigo": None, "actividades": len((rv.resumen or {}).get("versiones") or []),
                                       "revisada": True, "revision": {"numero": rv.numero,
                                                                      "fecha": _iso(rv.fecha_revision)}})
        return [por_version[k] for k in sorted(por_version, reverse=True)]

    async def _entradas_de(self, lista: list[dict]) -> dict[int, R.EntradaComparacion]:
        """[{id, version, huella}] → entradas legibles (desde la versión inmutable de cada actividad)."""
        ids = [x["id"] for x in lista if x.get("version")]
        filas: dict[tuple[int, int], Any] = {}
        if ids:
            filas = await self.repo.versiones_de_actividades(self.empresa_id, ids)
        nombres = await self.repo.nombres_de_actividades(self.empresa_id)
        salida: dict[int, R.EntradaComparacion] = {}
        fuentes = []
        for x in lista:
            v = filas.get((x["id"], x.get("version"))) if x.get("version") else None
            if v is None:
                salida[x["id"]] = R.EntradaComparacion(x["id"], nombres.get(x["id"], f"Actividad {x['id']}"), None,
                                                       x.get("huella"))
                continue
            fuentes.append(I.FuenteActividad(
                id=x["id"], nombre=nombres.get(x["id"], ""), estado="vigente", version_vigente=v.numero,
                fecha_vigencia=v.fecha, fecha_actualizacion=v.fecha, instantanea=v.contenido, huella_version=v.huella,
                fecha_version=v.fecha))
        if fuentes:
            for a in I.armar(fuentes, datetime.now(timezone.utc), self.razon_social).actividades:
                salida[a.id] = self._entrada(a)
        return salida

    @staticmethod
    def _entrada(a: I.ActividadInforme) -> R.EntradaComparacion:
        return R.EntradaComparacion(a.id, a.nombre, a.version, a.huella_version,
                                    {c: (t, txt) for c, t, txt in I.campos_legibles(a)})

    async def _lista_version(self, version: int) -> list[dict] | None:
        rv = await self.repo.revisada_de_version(self.empresa_id, version)
        if rv is not None and (rv.resumen or {}).get("versiones"):
            return list(rv.resumen["versiones"])
        f = await self.repo.informe_de_version(self.empresa_id, version)
        return list(f.versiones or []) if f is not None else None

    async def diferencias(self, desde: int | None, hasta: int | None) -> dict:
        """Compara dos versiones del registro (hasta=None: el registro actual). Sin `desde`: la última revisada."""
        if desde is None:
            ultima = (await self._revisadas(1))
            if not ultima:
                raise RevisionError(404, "SIN_VERSION_ANTERIOR", "Aún no hay una versión revisada con qué comparar: elige "
                                                                 "una versión del registro.")
            desde = ultima[0].version_rat
        antes_lista = await self._lista_version(desde)
        if antes_lista is None:
            raise RevisionError(404, "VERSION_NO_ENCONTRADA", f"No encontramos la versión {desde} del registro.")
        antes = await self._entradas_de(antes_lista)
        if hasta is None:
            inf = await self.informes.armar()
            despues = {a.id: self._entrada(a) for a in inf.actividades}
            etiqueta = "el registro actual"
        else:
            lista = await self._lista_version(hasta)
            if lista is None:
                raise RevisionError(404, "VERSION_NO_ENCONTRADA", f"No encontramos la versión {hasta} del registro.")
            despues = await self._entradas_de(lista)
            etiqueta = f"la versión {hasta}"
        return {"desde": desde, "hasta": hasta, "etiqueta": f"De la versión {desde} a {etiqueta}",
                **R.comparar(antes, despues)}
