"""
QA - Pruebas unitarias de ESCENARIOS BORDE del diagnóstico.

  A. Valores N/A masivos      -> GenerateResumenUseCase, CreateRespuestaUseCase
  B. Falta de evidencia        -> UploadEvidenceUseCase, ProcessEvidenceUseCase, resumen

Ejecutar desde Proyecto/backend/:
    pytest tests/test_bordes_na_y_evidencia.py -v

No requieren PostgreSQL, Redis ni Groq: la sesión, los repositorios, el storage
y el LLM son dobles de prueba.

Convención de nombres:
  test_*            -> comportamiento esperado; debe pasar.
  test_riesgo_*     -> documenta el comportamiento ACTUAL en un borde discutible
                       (el de respuestas duplicadas pasó a prueba esperada en HU-01)
                       (pasa hoy; si el equipo cambia la regla, se actualiza).
  xfail(strict=True)-> DEFECTO confirmado. Falla "esperadamente" hasta que se
                       corrija; cuando se corrija pasará y pytest avisará
                       (XPASS estricto) para quitar la marca.
"""
import asyncio
import hashlib
import time
from types import SimpleNamespace

import pytest

import app.domain.models  # noqa: F401  (registra todos los modelos de SQLAlchemy)
import app.application.use_cases.generate_resumen as gen_mod
from app.application.filters.control_tree import CONTROLES_BASE, CONTROLES_POR_FILTRO
from app.application.schemas.evidence_validation import EvidenceValidation
from app.application.use_cases.create_respuesta import CreateRespuestaUseCase, EvaluacionCerradaError
from app.application.use_cases.generate_resumen import GenerateResumenUseCase, nivel_madurez
from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
from app.application.use_cases.upload_evidence import UploadEvidenceUseCase
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.models.resumen import Resumen
from app.infrastructure.repositories.evaluacion_repository import ContextoEvaluacion
from app.infrastructure.security.prompt_guard import ReglasPromptGuard

NA = EstadoClasificacion.NO_APLICA.value
CUMP = EstadoClasificacion.CUMPLIDO.value
PARC = EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value
NOC = EstadoClasificacion.NO_CUMPLIDO.value
REV = EstadoClasificacion.REQUIERE_REVISION.value

DOMINIO_POR_PREFIJO = {"DAT": 1, "GOB": 2, "RIE": 3, "SEG": 4}
TODOS_LOS_CONTROLES = sorted(set(CONTROLES_BASE).union(*CONTROLES_POR_FILTRO.values()))
FILTRO_SOLO_BASE = {"F1": True, **{f"F{i}": False for i in range(2, 8)}}
FILTRO_TODO_SI = {f"F{i}": True for i in range(1, 8)}


# =====================================================================
# Dobles de prueba
# =====================================================================
class _Result:
    def __init__(self, filas):
        self._filas = list(filas)

    def all(self):
        return list(self._filas)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._filas))


class FakeSession:
    """Sesión mínima para GenerateResumenUseCase (2 execute en orden fijo)."""

    def __init__(self, pares, existentes=(), evaluacion=True):
        self._evaluacion = SimpleNamespace(id=1) if evaluacion else None
        self._resultados = [_Result(pares), _Result(existentes)]
        self.agregados, self.borrados, self.commits = [], [], 0

    async def get(self, _modelo, _id):
        return self._evaluacion

    async def execute(self, _stmt):
        return self._resultados.pop(0)

    async def delete(self, obj):
        self.borrados.append(obj)

    async def flush(self):
        pass

    def add(self, obj):
        self.agregados.append(obj)

    async def commit(self):
        self.commits += 1


def _usar_filtro(monkeypatch, respuestas_filtro: dict[str, bool]):
    filas = [
        SimpleNamespace(pregunta=SimpleNamespace(codigo=c), respuesta=v)
        for c, v in respuestas_filtro.items()
    ]

    class FakeRespFiltroRepo:
        def __init__(self, _session):
            pass

        async def list_by_evaluacion(self, _id):
            return filas

    monkeypatch.setattr(gen_mod, "RespuestaFiltroRepository", FakeRespFiltroRepo)


def _par(codigo, final, declarada=None):
    respuesta = SimpleNamespace(
        estado_clasificacion=declarada if declarada is not None else final,
        estado_clasificacion_final=final,
    )
    control = SimpleNamespace(codigo_control=codigo, dominio_id=DOMINIO_POR_PREFIJO[codigo[:3]])
    return respuesta, control


def _resumen(monkeypatch, pares, filtro=FILTRO_SOLO_BASE):
    _usar_filtro(monkeypatch, filtro)
    session = FakeSession(pares)
    resultado = asyncio.run(GenerateResumenUseCase(session).execute(1))
    return resultado, session


class FakeRespuestaRepo:
    def __init__(self, respuesta=None, control=None):
        self.respuesta, self.control, self.creadas, self.actualizadas = respuesta, control, [], []

    async def create(self, r):
        r.id = len(self.creadas) + 1
        self.creadas.append(r)
        return r

    async def get(self, _id):
        return self.respuesta

    async def get_by_evaluacion_control(self, evaluacion_id, control_id):
        return next((r for r in self.creadas
                     if r.evaluacion_id == evaluacion_id and r.matriz_controles_id_control == control_id), None)

    async def update(self, r):
        self.actualizadas.append(r)
        return r

    async def get_control(self, _id):
        return self.control

    async def get_brecha(self, _id):
        return None


class FakeEvaluaciones:
    """Contexto de evaluación abierta con el filtro completo (todo SI) por defecto."""

    def __init__(self, estado="en_progreso", filtro_completado=True, filtro=None, existe=True):
        self.estado, self.filtro_completado, self.existe = estado, filtro_completado, existe
        self.filtro = FILTRO_TODO_SI if filtro is None else filtro

    async def get_contexto(self, evaluacion_id):
        if not self.existe:
            return None
        return ContextoEvaluacion(id=evaluacion_id, estado_progreso=self.estado,
                                  filtro_completado=self.filtro_completado,
                                  respuestas_filtro=dict(self.filtro))


class FakeEvidenciaRepo:
    def __init__(self, evidencia=None):
        self.evidencia, self.creadas = evidencia, []

    async def get(self, _id):
        return self.evidencia

    async def create(self, e):
        e.id_evidencia = 1
        self.creadas.append(e)
        return e

    async def update(self, e):
        return e


class FakeStorage:
    def __init__(self, contenido: bytes = b"", error: Exception | None = None):
        self.contenido, self.error, self.guardados = contenido, error, []

    async def save(self, content, filename):
        self.guardados.append((filename, content))
        return f"/tmp/{filename}"

    async def get(self, _path):
        if self.error:
            raise self.error
        return self.contenido


class FakeUpload:
    def __init__(self, contenido: bytes, filename="evidencia.txt", content_type="text/plain"):
        self._contenido, self.filename, self.content_type = contenido, filename, content_type

    async def read(self):
        return self._contenido


class FakeValidator:
    def __init__(self, clasificacion=CUMP, confianza=0.95, suficiente=True):
        self.clasificacion, self.confianza, self.suficiente = clasificacion, confianza, suficiente
        self.llamadas = []

    async def validate(self, contenido, control, respuesta, brecha=None, justificacion=None, contexto=None):
        self.llamadas.append({"contenido": contenido, "justificacion": justificacion})
        return EvidenceValidation(
            clasificacion=self.clasificacion,
            confianza=self.confianza,
            justificacion="resultado simulado",
            respalda_clasificacion_usuario=self.clasificacion == CUMP,
            divergencia_explicada=None if self.clasificacion == CUMP else "simulado",
            evidencia_suficiente=self.suficiente,
        )


def _control(codigo="GOB-001"):
    return SimpleNamespace(id_control=7, codigo_control=codigo, catalogo_brechas_id_brecha=3)


def _respuesta(declarada=CUMP, justificacion="Política aprobada por el directorio."):
    r = Respuesta(
        evaluacion_id=1, matriz_controles_id_control=7,
        estado_clasificacion=declarada, justificacion_usuario=justificacion,
        estado_clasificacion_final=declarada, fuente_clasificacion=FuenteClasificacion.USUARIO.value,
    )
    r.id = 10
    return r


def _evidencia():
    return Evidencia(
        id_evidencia=99, respuesta_id=10, nombre_archivo="e.txt", storage_path="x",
        mime_type="text/plain", hash_archivo="0" * 64,
        estado_validacion=EstadoValidacion.PENDING.value,
    )


def _procesar(storage, validator, respuesta=None, evidencia=None, guard=True):
    respuesta = respuesta if respuesta is not None else _respuesta()
    evidencia = evidencia if evidencia is not None else _evidencia()
    uc = ProcessEvidenceUseCase(
        FakeEvidenciaRepo(evidencia), FakeRespuestaRepo(respuesta, _control()),
        storage, validator, guard=ReglasPromptGuard() if guard else None,
    )
    asyncio.run(uc.execute(99))
    return evidencia, respuesta


# =====================================================================
# A. VALORES N/A MASIVOS - cálculo del resumen
# =====================================================================
class TestResumenConNAMasivo:

    def test_100_por_ciento_na_no_genera_resumenes_ni_divide_por_cero(self, monkeypatch):
        pares = [_par(c, NA) for c in CONTROLES_BASE]
        r, session = _resumen(monkeypatch, pares)

        assert r["total_controles_evaluados"] == 0
        assert r["puntaje_general"] == 0.0
        assert r["dominios"] == []
        assert not [o for o in session.agregados if isinstance(o, Resumen)]
        assert session.commits == 1

    def test_riesgo_100_por_ciento_na_se_informa_como_nivel_inicial(self, monkeypatch):
        """
        RIESGO: una organización con TODO en N/A recibe el mismo resultado
        (0 pts, 'inicial') que una que incumple todo. El informe no distingue
        'sin datos evaluables' de 'madurez mínima'.
        """
        r, _ = _resumen(monkeypatch, [_par(c, NA) for c in CONTROLES_BASE])
        assert r["nivel_madurez_general"] == "inicial"

    def test_na_masivo_con_un_solo_cumplido_da_100_optimizado(self, monkeypatch):
        """21 de 22 en N/A: un único control decide el 100 % del puntaje."""
        pares = [_par(c, NA) for c in CONTROLES_BASE[1:]] + [_par(CONTROLES_BASE[0], CUMP)]
        r, _ = _resumen(monkeypatch, pares)

        assert r["total_controles_evaluados"] == 1
        assert r["puntaje_general"] == 100.0
        assert r["nivel_madurez_general"] == "optimizado"
        assert len(r["dominios"]) == 1

    def test_na_masivo_con_un_solo_no_cumplido_da_0_inicial(self, monkeypatch):
        pares = [_par(c, NA) for c in CONTROLES_BASE[1:]] + [_par(CONTROLES_BASE[0], NOC)]
        r, _ = _resumen(monkeypatch, pares)
        assert (r["puntaje_general"], r["nivel_madurez_general"]) == (0.0, "inicial")

    def test_na_no_entra_al_denominador_pero_requiere_revision_si(self, monkeypatch):
        # DAT: cumplido + parcial -> 75 ; GOB: no_cumplido -> 0 ; RIE: revisión -> 0 ; SEG: todo N/A
        especiales = {"DAT-001": CUMP, "DAT-003": PARC, "GOB-001": NOC, "RIE-001": REV}
        pares = [_par(c, especiales.get(c, NA)) for c in CONTROLES_BASE]
        r, _ = _resumen(monkeypatch, pares)

        assert r["total_controles_evaluados"] == 4
        assert r["puntaje_general"] == 37.5            # 1.5 / 4
        assert r["nivel_madurez_general"] == "en_desarrollo"
        por_dom = {d["dominio_id"]: d for d in r["dominios"]}
        assert por_dom[1]["puntaje"] == 75.0 and por_dom[1]["nivel"] == "gestionado"
        assert por_dom[3]["en_revision"] == 1 and por_dom[3]["puntaje"] == 0.0
        assert 4 not in por_dom                         # dominio 100 % N/A no aparece

    def test_dominio_completamente_na_desaparece_del_informe(self, monkeypatch):
        pares = [_par(c, NA if c.startswith("SEG") else CUMP) for c in CONTROLES_BASE]
        r, _ = _resumen(monkeypatch, pares)
        assert {d["dominio_id"] for d in r["dominios"]} == {1, 2, 3}

    def test_na_final_excluye_aunque_lo_declarado_fuera_cumplido(self, monkeypatch):
        pares = [_par(c, NA, declarada=CUMP) for c in CONTROLES_BASE]
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 0

    def test_final_vacio_y_declarada_na_se_excluye(self, monkeypatch):
        pares = [_par(c, None, declarada=NA) for c in CONTROLES_BASE]
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 0

    def test_respuestas_sin_clasificacion_se_ignoran_silenciosamente(self, monkeypatch):
        """Controles sin responder (None/None) no cuentan ni como 0."""
        pares = [_par(c, None, declarada=None) for c in CONTROLES_BASE[1:]]
        pares.append(_par(CONTROLES_BASE[0], CUMP))
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 1 and r["puntaje_general"] == 100.0

    def test_valor_desconocido_no_rompe_el_calculo(self, monkeypatch):
        pares = [_par("DAT-001", "N/A"), _par("DAT-003", "na"), _par("DAT-004", CUMP)]
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 1

    def test_filtro_f1_no_excluye_todo_aunque_haya_respuestas(self, monkeypatch):
        filtro = {**FILTRO_SOLO_BASE, "F1": False}
        r, _ = _resumen(monkeypatch, [_par(c, CUMP) for c in CONTROLES_BASE], filtro=filtro)
        assert r["total_controles_evaluados"] == 0 and r["dominios"] == []

    def test_controles_fuera_del_filtro_no_puntuan(self, monkeypatch):
        extra = CONTROLES_POR_FILTRO["F2"]  # F2 = NO en FILTRO_SOLO_BASE
        pares = [_par(c, NA) for c in CONTROLES_BASE] + [_par(c, CUMP) for c in extra]
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 0

    def test_todos_los_40_controles_aplicables_en_na(self, monkeypatch):
        """Filtro F1..F7 = SI activa la matriz completa: 22 base + 18 por filtro."""
        pares = [_par(c, NA) for c in TODOS_LOS_CONTROLES]
        r, _ = _resumen(monkeypatch, pares, filtro=FILTRO_TODO_SI)
        assert len(TODOS_LOS_CONTROLES) == 40
        assert r["total_controles_evaluados"] == 0

    def test_resumenes_previos_se_borran_aunque_el_nuevo_quede_vacio(self, monkeypatch):
        _usar_filtro(monkeypatch, FILTRO_SOLO_BASE)
        viejos = [Resumen(evaluacion_id=1, dominio_id=1), Resumen(evaluacion_id=1, dominio_id=2)]
        session = FakeSession([_par(c, NA) for c in CONTROLES_BASE], existentes=viejos)
        asyncio.run(GenerateResumenUseCase(session).execute(1))
        assert session.borrados == viejos

    def test_volumen_10000_filas_mayoria_na_es_rapido_y_cuenta_una_por_control(self, monkeypatch):
        """HU-01: la BD ya no admite estas filas repetidas (restricción única); si
        llegaran, el resumen sigue siendo rápido y solo cuenta la última por control."""
        pares = [_par(CONTROLES_BASE[i % 22], NA) for i in range(9_990)]
        pares += [_par("DAT-001", CUMP) for _ in range(10)]
        t0 = time.perf_counter()
        r, _ = _resumen(monkeypatch, pares)
        ms = (time.perf_counter() - t0) * 1000
        assert r["total_controles_evaluados"] == 1 and r["puntaje_general"] == 100.0
        assert ms < 500, f"Cálculo de resumen tardó {ms:.1f} ms"

    def test_respuestas_duplicadas_de_un_control_cuentan_una_sola_vez(self, monkeypatch):
        """
        HU-01 (antes test_riesgo_..._cuentan_doble): POST /api/respuestas es un upsert
        y la BD tiene unique (evaluación, control). Aun si llegaran dos filas del
        mismo control, el resumen cuenta solo la más reciente: 'no_cumplido' y luego
        'cumplido' => 1 control evaluado y 100 % (antes: 2 controles y 50 %).
        """
        pares = [_par(c, NA) for c in CONTROLES_BASE[1:]]
        pares += [_par("DAT-001", NOC), _par("DAT-001", CUMP)]
        r, _ = _resumen(monkeypatch, pares)
        assert r["total_controles_evaluados"] == 1
        assert r["puntaje_general"] == 100.0

    def test_la_tabla_respuestas_tiene_unique_evaluacion_control(self):
        restricciones = {
            tuple(c.name for c in u.columns)
            for u in Respuesta.__table__.constraints if u.__class__.__name__ == "UniqueConstraint"
        }
        assert ("Evaluacion_id", "Matriz_controles_id_control") in restricciones

    def test_evaluacion_inexistente(self, monkeypatch):
        _usar_filtro(monkeypatch, FILTRO_SOLO_BASE)
        with pytest.raises(ValueError, match="no encontrada"):
            asyncio.run(GenerateResumenUseCase(FakeSession([], evaluacion=False)).execute(404))


class TestNivelMadurez:

    @pytest.mark.parametrize("puntaje, nivel", [
        (0, "inicial"), (25, "inicial"), (25.01, "en_desarrollo"),
        (50, "en_desarrollo"), (50.01, "gestionado"), (75, "gestionado"),
        (75.01, "optimizado"), (100, "optimizado"),
    ])
    def test_limites(self, puntaje, nivel):
        assert nivel_madurez(puntaje) == nivel

    def test_todo_nivel_cabe_en_la_columna(self):
        largo = Resumen.__table__.c.nivel_madurez.type.length
        for puntaje in (0, 30, 60, 90):
            assert len(nivel_madurez(puntaje)) <= largo, nivel_madurez(puntaje)


# =====================================================================
# A. VALORES N/A MASIVOS - creación de respuestas
# =====================================================================
class TestCrearRespuestasNA:

    def _uc(self, repo, evaluaciones=None):
        return CreateRespuestaUseCase(repo, evaluaciones or FakeEvaluaciones(), guard=ReglasPromptGuard())

    def test_na_masivo_40_controles_se_acepta_sin_brechas(self):
        repo = FakeRespuestaRepo(control=_control())
        uc = self._uc(repo)
        for control_id in range(1, len(TODOS_LOS_CONTROLES) + 1):
            asyncio.run(uc.execute(1, control_id, NA, ""))
        assert len(repo.creadas) == 40
        assert all(r.estado_clasificacion_final == NA for r in repo.creadas)
        assert all(r.catalogo_brechas_id_brecha is None for r in repo.creadas)

    def test_na_con_justificacion_vacia_es_valido(self):
        r = asyncio.run(self._uc(FakeRespuestaRepo(control=_control())).execute(1, 7, NA, ""))
        assert r.justificacion_usuario == "" and r.fuente_clasificacion == "usuario"

    @pytest.mark.parametrize("variante", ["N/A", "n/a", "NA", "No Aplica", "no aplica", "NO_APLICA", " no_aplica", ""])
    def test_variantes_de_na_que_no_son_el_valor_canonico_se_rechazan(self, variante):
        repo = FakeRespuestaRepo(control=_control())
        with pytest.raises(ValueError, match="Clasificación inválida"):
            asyncio.run(self._uc(repo).execute(1, 7, variante, "x"))
        assert repo.creadas == []

    def test_no_cumplido_asigna_brecha_pero_na_no(self):
        repo = FakeRespuestaRepo(control=_control())
        noc = asyncio.run(self._uc(repo).execute(1, 7, NOC, "No existe política."))
        assert noc.catalogo_brechas_id_brecha == 3
        na = asyncio.run(self._uc(repo).execute(1, 8, NA, ""))
        assert na.catalogo_brechas_id_brecha is None

    def test_cambiar_no_cumplido_a_na_actualiza_la_misma_fila_y_quita_la_brecha(self):
        repo = FakeRespuestaRepo(control=_control())
        uc = self._uc(repo)
        noc = asyncio.run(uc.execute(1, 7, NOC, "No existe política."))
        na = asyncio.run(uc.execute(1, 7, NA, ""))
        assert na is noc and len(repo.creadas) == 1 and repo.actualizadas == [noc]
        assert na.estado_clasificacion_final == NA and na.catalogo_brechas_id_brecha is None


# =====================================================================
# B. FALTA DE EVIDENCIA - subida
# =====================================================================
class TestSubidaSinEvidencia:

    def _subir(self, respuesta, archivo):
        storage, evid_repo = FakeStorage(), FakeEvidenciaRepo()
        uc = UploadEvidenceUseCase(evid_repo, FakeRespuestaRepo(respuesta), storage, FakeEvaluaciones())
        return asyncio.run(uc.execute(10, archivo)), storage, evid_repo

    def test_archivo_vacio_se_rechaza_y_no_se_guarda(self):
        storage, evid_repo = FakeStorage(), FakeEvidenciaRepo()
        uc = UploadEvidenceUseCase(evid_repo, FakeRespuestaRepo(_respuesta()), storage, FakeEvaluaciones())
        with pytest.raises(ValueError, match="vacío"):
            asyncio.run(uc.execute(10, FakeUpload(b"")))
        assert storage.guardados == [] and evid_repo.creadas == []

    def test_respuesta_inexistente(self):
        uc = UploadEvidenceUseCase(FakeEvidenciaRepo(), FakeRespuestaRepo(None), FakeStorage(), FakeEvaluaciones())
        with pytest.raises(ValueError, match="no encontrada"):
            asyncio.run(uc.execute(10, FakeUpload(b"x")))

    def test_respuesta_sin_clasificacion_declarada(self):
        r = _respuesta()
        r.estado_clasificacion = None
        uc = UploadEvidenceUseCase(FakeEvidenciaRepo(), FakeRespuestaRepo(r), FakeStorage(), FakeEvaluaciones())
        with pytest.raises(ValueError, match="no tiene clasificación"):
            asyncio.run(uc.execute(10, FakeUpload(b"x")))

    @pytest.mark.parametrize("estado", ["completada", "cerrada"])
    def test_evaluacion_cerrada_rechaza_evidencia_y_no_guarda_el_archivo(self, estado):
        storage, evid_repo = FakeStorage(), FakeEvidenciaRepo()
        uc = UploadEvidenceUseCase(evid_repo, FakeRespuestaRepo(_respuesta()), storage,
                                   FakeEvaluaciones(estado=estado))
        with pytest.raises(EvaluacionCerradaError, match="no admite evidencias"):
            asyncio.run(uc.execute(10, FakeUpload(b"Politica de IA v1")))
        assert storage.guardados == [] and evid_repo.creadas == []

    @pytest.mark.parametrize("clasif", [NOC, NA])
    def test_clasificaciones_que_no_requieren_evidencia_rechazan_subida(self, clasif):
        storage = FakeStorage()
        uc = UploadEvidenceUseCase(FakeEvidenciaRepo(), FakeRespuestaRepo(_respuesta(clasif)), storage, FakeEvaluaciones())
        with pytest.raises(ValueError, match="No se puede subir evidencia"):
            asyncio.run(uc.execute(10, FakeUpload(b"contenido")))
        assert storage.guardados == []

    def test_requiere_revision_admite_evidencia_para_que_la_resuelva_el_llm(self):
        """HU-02: el usuario declara 'requiere_revision' y sube la evidencia que el LLM clasifica."""
        ev, storage, _ = self._subir(_respuesta(REV), FakeUpload(b"Inventario de modelos v1"))
        assert ev.estado_validacion == EstadoValidacion.PENDING.value and len(storage.guardados) == 1

    def test_subida_valida_queda_pending_con_hash_y_mime_por_defecto(self):
        contenido = b"Politica de IA v1"
        ev, storage, _ = self._subir(_respuesta(PARC), FakeUpload(contenido, content_type=None))
        assert ev.estado_validacion == EstadoValidacion.PENDING.value
        assert ev.hash_archivo == hashlib.sha256(contenido).hexdigest()
        assert ev.mime_type == "application/octet-stream"
        assert len(storage.guardados) == 1


# =====================================================================
# B. FALTA DE EVIDENCIA - procesamiento
# =====================================================================
class TestProcesamientoSinEvidencia:

    def test_archivo_borrado_del_storage_termina_en_error_sin_tocar_respuesta(self):
        validator = FakeValidator()
        ev, resp = _procesar(FakeStorage(error=FileNotFoundError("no existe /tmp/x")), validator)
        assert ev.estado_validacion == EstadoValidacion.ERROR.value
        assert "no existe" in ev.errores_validacion[0]
        assert ev.fecha_procesada is not None
        assert validator.llamadas == []
        assert resp.estado_clasificacion_final == CUMP and resp.fuente_clasificacion == "usuario"

    def test_respuesta_borrada_termina_en_error(self):
        evidencia = _evidencia()
        uc = ProcessEvidenceUseCase(
            FakeEvidenciaRepo(evidencia), FakeRespuestaRepo(None),
            FakeStorage(b"texto"), FakeValidator(), guard=ReglasPromptGuard(),
        )
        asyncio.run(uc.execute(99))
        assert evidencia.estado_validacion == EstadoValidacion.ERROR.value
        assert "Respuesta" in evidencia.errores_validacion[0]

    def test_evidencia_inexistente_lanza_error(self):
        uc = ProcessEvidenceUseCase(
            FakeEvidenciaRepo(None), FakeRespuestaRepo(_respuesta()),
            FakeStorage(b"x"), FakeValidator(),
        )
        with pytest.raises(ValueError, match="no encontrada"):
            asyncio.run(uc.execute(99))

    @pytest.mark.parametrize("contenido", [b"", b"\xff\xfe\xfd", b"   \n\t  "],
                             ids=["vacio", "binario_no_utf8", "solo_espacios"])
    def test_riesgo_evidencia_sin_texto_igual_se_envia_al_llm(self, contenido):
        """
        RIESGO: no hay validación de 'contenido legible' antes del LLM; un
        archivo binario o en blanco consume una llamada al modelo.
        """
        validator = FakeValidator(confianza=0.2)
        _procesar(FakeStorage(contenido), validator)
        assert len(validator.llamadas) == 1
        assert validator.llamadas[0]["contenido"].strip() == ""

    def test_riesgo_evidencia_vacia_y_llm_dudoso_mantiene_cumplido_del_usuario(self):
        """
        RIESGO (Regla 1 - fallback al usuario): con evidencia vacía y LLM con
        baja confianza, la evidencia queda REJECTED pero la respuesta conserva
        'cumplido' y puntúa 1.0 en el resumen.
        """
        ev, resp = _procesar(FakeStorage(b""), FakeValidator(confianza=0.2))
        assert ev.estado_validacion == EstadoValidacion.REJECTED.value
        assert resp.estado_clasificacion_final == CUMP
        assert resp.fuente_clasificacion == FuenteClasificacion.USUARIO.value

    def test_riesgo_evidencia_insuficiente_segun_llm_no_se_considera(self):
        """
        RIESGO: EvidenceValidation.evidencia_suficiente=False no participa en la
        decisión del backend; con confianza alta se acepta 'cumplido'.
        """
        ev, resp = _procesar(FakeStorage(b"Documento de una linea."),
                             FakeValidator(clasificacion=CUMP, confianza=0.95, suficiente=False))
        assert resp.estado_clasificacion_final == CUMP
        assert resp.fuente_clasificacion == FuenteClasificacion.LLM.value
        assert ev.estado_validacion == EstadoValidacion.VALIDATED.value

    def test_llm_seguro_de_no_cumplido_por_falta_de_evidencia_baja_y_asigna_brecha(self):
        ev, resp = _procesar(FakeStorage(b"Acta sin relacion con el control."),
                             FakeValidator(clasificacion=NOC, confianza=0.9, suficiente=False))
        assert resp.estado_clasificacion_final == NOC
        assert resp.catalogo_brechas_id_brecha == 3
        assert ev.estado_validacion == EstadoValidacion.VALIDATED.value

    def test_confianza_exactamente_en_umbral_decide_el_llm(self):
        _, resp = _procesar(FakeStorage(b"Politica aprobada."),
                            FakeValidator(clasificacion=PARC, confianza=settings.UMBRAL_CONFIANZA))
        assert resp.estado_clasificacion_final == PARC
        assert resp.fuente_clasificacion == FuenteClasificacion.LLM.value

    def test_evidencia_muy_larga_se_trunca_antes_del_llm(self):
        # El recorte ahora lo hace la capa de IA (sanitiza primero, recorta después).
        from _capa_ia_fakes import crear_validador
        texto = ("La organizacion mantiene un inventario de modelos actualizado. " * 2000).encode()
        validator, gw = crear_validador(max_chars_evidencia=settings.MAX_CHARS_EVIDENCIA_LLM)
        # Sin guard: el texto repetido dispara la heurística anti-inyección y
        # aquí solo se quiere aislar el truncado.
        _procesar(FakeStorage(texto), validator, guard=False)
        enviado = gw.provider.requests[0].user
        bloque = enviado.split("<evidencia_adjunta>\n", 1)[1].split("\n</evidencia_adjunta>", 1)[0]
        # HU-17 (RAG local): un texto que no cabe se reduce a sus pasajes más relevantes, sin
        # pasar nunca del máximo (antes se cortaba exactamente en MAX_CHARS_EVIDENCIA_LLM).
        assert settings.MAX_CHARS_EVIDENCIA_LLM * 0.8 < len(bloque) <= settings.MAX_CHARS_EVIDENCIA_LLM

    def test_justificacion_vacia_no_rompe_el_procesamiento(self):
        validator = FakeValidator()
        _, resp = _procesar(FakeStorage(b"Politica aprobada."), validator,
                            respuesta=_respuesta(justificacion=None))
        assert validator.llamadas[0]["justificacion"] == ""
        assert resp.fuente_clasificacion == FuenteClasificacion.LLM.value


class TestResumenSinEvidencia:

    def test_riesgo_cumplido_declarado_sin_evidencia_puntua_completo(self, monkeypatch):
        """
        RIESGO: el resumen no mira si existe evidencia. Un 'cumplido' declarado
        y nunca respaldado (sin archivo) vale 1.0 igual que uno validado.
        """
        pares = [_par(c, NA) for c in CONTROLES_BASE[2:]]
        pares += [_par("DAT-001", CUMP), _par("DAT-003", PARC)]   # sin evidencias
        r, _ = _resumen(monkeypatch, pares)
        assert r["puntaje_general"] == 75.0