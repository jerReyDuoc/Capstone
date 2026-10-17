"""
HU-06 — Pruebas unitarias de la anonimización previa a persistir.

Ejecutar desde Proyecto/backend/:
    pytest tests/test_hu06_anonimizacion.py -v

No requieren BD, Redis, spaCy ni API key (NLP simulado, repositorios en memoria).
La prueba de regresión de punta a punta (BD + logs + disco) está en
tests/test_hu06_regresion_pii.py.

Cubre:
  C1 etiquetas fijas en lo que se guarda (justificación, nombre de archivo, archivo)
  C2 enmascaramiento en memoria ANTES de persistir (fail-closed si el motor falla)
  -  archivos de evidencia cifrados en reposo y reemplazados por el texto anonimizado
  -  mapa de entidades irreversible (sin valores originales)
  -  textos ARCOP cifrados (excepción documentada) y legibles por el ORM
"""
import asyncio
import uuid

import pytest

import app.domain.models  # noqa: F401  (registra todos los modelos de SQLAlchemy)
from app.application.ai.anonimizador import AnonimizacionError, AnonimizadorPII
from app.application.use_cases.create_respuesta import (
    AnonimizacionNoDisponibleError,
    CreateRespuestaUseCase,
)
from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
from app.core.config import settings
from app.domain.models.evidencia import EstadoValidacion, Evidencia
from app.domain.ports.registro_ia_port import ContextoLlamada, RegistroSanitizacion
from app.domain.ports.sanitizer_port import EntidadDetectada, TipoEntidad
from app.infrastructure.security.cifrado import CifradorDatos, CifradorEntidades
from app.infrastructure.security.ner_sanitizer import NERSanitizer
from app.infrastructure.storage.archivo_cifrado_storage import ArchivoCifradoStorage

from _capa_ia_fakes import StubNLP
from test_seguridad_integracion import (
    FakeEvaluaciones, FakeEvidenciaRepo, FakeRespuestaRepo, FakeValidator, _control, _respuesta,
)

RUT = "12.345.678-5"
NOMBRE = "Juan Pérez Soto"
CORREO = "jperez@empresa-demo.cl"
TELEFONO = "+56 9 8765 4321"
PII = (RUT, NOMBRE, CORREO, TELEFONO)
JUST_PII = f"Lo aprobó {NOMBRE}, RUT {RUT}. Consultas a {CORREO} o al {TELEFONO}."
CLAVE = settings.ENTITY_MAP_KEY  # clave de prueba de conftest.py


def _anon(nombres=(NOMBRE,)) -> AnonimizadorPII:
    return AnonimizadorPII(NERSanitizer(lambda: StubNLP(nombres)))


class NERRoto:
    def sanitizar(self, texto, max_chars=None):
        raise RuntimeError("modelo no disponible")


def _sin_pii(texto: str) -> bool:
    return not any(v in texto for v in PII)


# ---------------------------------------------------------------- AnonimizadorPII
def test_anonimizador_usa_etiquetas_fijas():
    t = asyncio.run(_anon().anonimizar(JUST_PII))
    assert _sin_pii(t)
    for etiqueta in ("[NOMBRE_ANON]", "[RUT_ANON]", "[CORREO_ANON]", "[TEL_ANON]"):
        assert etiqueta in t
    assert "[RUT_1]" not in t and "_ANON_" not in t


def test_anonimizador_no_toca_textos_sin_pii():
    texto = "  Contamos con una política   aprobada por el directorio.  "
    assert asyncio.run(_anon().anonimizar(texto)) == texto
    assert asyncio.run(_anon().anonimizar(None)) is None


def test_anonimizador_es_idempotente():
    una = asyncio.run(_anon().anonimizar(JUST_PII))
    assert asyncio.run(_anon().anonimizar(una)) == una


def test_anonimizador_falla_cerrado_sin_filtrar_el_texto():
    with pytest.raises(AnonimizacionError) as e:
        asyncio.run(AnonimizadorPII(NERRoto()).anonimizar(JUST_PII))
    assert _sin_pii(str(e.value))


def test_anonimizador_deshabilitado_solo_en_debug():
    a = AnonimizadorPII(None, habilitado=False)
    assert asyncio.run(a.anonimizar(JUST_PII)) == JUST_PII
    with pytest.raises(ValueError):
        AnonimizadorPII(None)  # habilitado sin motor: error de configuración


@pytest.mark.parametrize("nombre,esperado", [
    (f"contrato_{RUT}.pdf", "contrato_[RUT_ANON].pdf"),
    (f"CV_{NOMBRE.replace(' ', '_')}.docx", "CV_[NOMBRE_ANON].docx"),
    ("politica_gobernanza_v3.txt", "politica_gobernanza_v3.txt"),
    ("../../etc/passwd", "passwd"),
])
def test_nombre_de_archivo_anonimizado(nombre, esperado):
    assert asyncio.run(_anon().anonimizar_nombre_archivo(nombre)) == esperado


# ---------------------------------------------------------------- justificación (C2)
def _uc(repo, anonimizador):
    return CreateRespuestaUseCase(repo, FakeEvaluaciones(), anonimizador=anonimizador)


def test_justificacion_se_guarda_anonimizada():
    repo = FakeRespuestaRepo(control=_control())
    r = asyncio.run(_uc(repo, _anon()).execute(1, 7, "cumplido", JUST_PII))
    assert _sin_pii(r.justificacion_usuario) and "[RUT_ANON]" in r.justificacion_usuario
    assert repo.creadas[0].justificacion_usuario == r.justificacion_usuario


def test_si_falla_la_anonimizacion_no_se_guarda_nada():
    repo = FakeRespuestaRepo(control=_control())
    with pytest.raises(AnonimizacionNoDisponibleError) as e:
        asyncio.run(_uc(repo, AnonimizadorPII(NERRoto())).execute(1, 7, "cumplido", JUST_PII))
    assert e.value.status_code == 503 and e.value.codigo == "ANONIMIZACION_NO_DISPONIBLE"
    assert repo.creadas == [] and _sin_pii(str(e.value))


def test_reenvio_identico_con_pii_no_cuenta_como_cambio():
    """El guardado automático reenvía el texto original; lo guardado está anonimizado.
    Se compara anonimizado contra anonimizado: no se pierde la validación del LLM."""
    guardada = asyncio.run(_anon().anonimizar(JUST_PII))
    existente = _respuesta(guardada)
    existente.matriz_controles_id_control = 7
    existente.fuente_clasificacion, existente.confianza_clasificacion = "llm", 0.95

    class Repo(FakeRespuestaRepo):
        async def get_by_evaluacion_control(self, *_):
            return existente

    resultado = asyncio.run(_uc(Repo(control=_control()), _anon()).guardar(1, 7, "cumplido", JUST_PII))
    assert resultado.modificada is False
    assert existente.fuente_clasificacion == "llm" and existente.confianza_clasificacion == 0.95


# ---------------------------------------------------------------- archivos de evidencia
class MemoriaStorage:
    def __init__(self):
        self.archivos: dict[str, bytes] = {}

    async def save(self, content, filename):
        ruta = f"/mem/{uuid.uuid4().hex}"
        self.archivos[ruta] = content
        return ruta

    async def get(self, ruta):
        return self.archivos[ruta]

    async def delete(self, ruta):
        self.archivos.pop(ruta, None)


def _storage():
    interno = MemoriaStorage()
    return ArchivoCifradoStorage(interno, CifradorDatos(CLAVE, "evidencias")), interno


def test_archivo_cifrado_en_reposo():
    storage, interno = _storage()
    ruta = asyncio.run(storage.save(JUST_PII.encode(), "acta.txt"))
    crudo = interno.archivos[ruta]
    assert CifradorDatos.esta_cifrado(crudo) and _sin_pii(crudo.decode("latin-1"))
    assert asyncio.run(storage.get(ruta)) == JUST_PII.encode()


def _procesar(contenido: str, anonimizador):
    storage, interno = _storage()
    ruta = asyncio.run(storage.save(contenido.encode(), "acta.txt"))
    evidencia = Evidencia(id_evidencia=99, respuesta_id=10, nombre_archivo="acta.txt", storage_path=ruta,
                          mime_type="text/plain", hash_archivo="0" * 64,
                          estado_validacion=EstadoValidacion.PENDING.value)
    validator = FakeValidator()
    uc = ProcessEvidenceUseCase(FakeEvidenciaRepo(evidencia), FakeRespuestaRepo(_respuesta(), _control()),
                                storage, validator, anonimizador=anonimizador)
    asyncio.run(uc.execute(99))
    return evidencia, interno, validator, ruta


def test_worker_deja_solo_el_texto_anonimizado():
    evidencia, interno, validator, original = _procesar(f"Acta firmada por {NOMBRE}, RUT {RUT}.", _anon())
    assert evidencia.estado_validacion == EstadoValidacion.VALIDATED.value
    assert NOMBRE in validator.llamadas[0]["contenido"]      # el validador (gateway) recibe el original
    assert original not in interno.archivos                  # el cifrado se borró
    assert list(interno.archivos) == [evidencia.storage_path]
    texto = interno.archivos[evidencia.storage_path].decode()
    assert _sin_pii(texto) and "[RUT_ANON]" in texto and "[NOMBRE_ANON]" in texto


def test_si_el_motor_falla_el_archivo_queda_cifrado():
    evidencia, interno, _, original = _procesar(f"RUT {RUT}", AnonimizadorPII(NERRoto()))
    assert evidencia.storage_path == original and list(interno.archivos) == [original]
    assert CifradorDatos.esta_cifrado(interno.archivos[original])


# ---------------------------------------------------------------- mapa de entidades
class SesionFalsa:
    def __init__(self):
        self.filas = []

    def add(self, fila):
        self.filas.append(fila)

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _registro(guardar_mapa: bool):
    from app.infrastructure.repositories.registro_ia_repository import RegistroIARepository

    sesion = SesionFalsa()
    repo = RegistroIARepository(sesion, CifradorEntidades(CLAVE), guardar_mapa=guardar_mapa)
    entidad = EntidadDetectada(TipoEntidad.RUT, RUT, 4, 16, "regex")
    asyncio.run(repo.guardar_sanitizaciones([RegistroSanitizacion(
        campo="evidencia", entidades=[entidad], motor="test", duracion_ms=1.0, truncado=False,
        contexto=ContextoLlamada(), traza_id="t" * 32)]))
    return sesion.filas[0]


def test_mapa_de_entidades_irreversible_por_defecto():
    from app.core.config import Settings
    assert Settings.model_fields["GUARDAR_MAPA_ENTIDADES_CIFRADO"].default is False  # decisión del PO
    fila = _registro(guardar_mapa=False)
    assert fila.mapa_cifrado is None
    assert fila.conteo_por_tipo == {"RUT": 1}
    assert fila.entidades[0]["huella"] == CifradorEntidades(CLAVE).huella(RUT)
    assert RUT not in str(fila.entidades)


def test_mapa_reversible_solo_si_se_activa():
    fila = _registro(guardar_mapa=True)
    assert CifradorEntidades(CLAVE).descifrar_json(fila.mapa_cifrado)[0]["valor"] == RUT


# ---------------------------------------------------------------- textos ARCOP (excepción)
def test_texto_arcop_se_cifra_al_escribir_y_se_descifra_al_leer():
    from app.core.cifrado_columnas import TEXTO_ILEGIBLE, TextoCifrado

    tipo = TextoCifrado()
    guardado = tipo.process_bind_param(JUST_PII, None)
    assert guardado.startswith("enc:v1:") and _sin_pii(guardado)
    assert tipo.process_result_value(guardado, None) == JUST_PII
    assert tipo.process_bind_param(guardado, None) == guardado        # no se cifra dos veces
    assert tipo.process_result_value("fila antigua", None) == "fila antigua"
    assert tipo.process_result_value("enc:v1:alterado", None) == TEXTO_ILEGIBLE
    assert tipo.process_bind_param(None, None) is None


def test_texto_arcop_sin_clave_no_se_escribe(monkeypatch):
    from app.core.cifrado_columnas import TextoCifrado
    from app.infrastructure.security.cifrado import ClaveCifradoInvalida

    monkeypatch.setattr(settings, "ENTITY_MAP_KEY", None)
    with pytest.raises(ClaveCifradoInvalida):
        TextoCifrado().process_bind_param(JUST_PII, None)


def test_subclaves_independientes():
    arcop, evid = CifradorDatos(CLAVE, "arcop"), CifradorDatos(CLAVE, "evidencias")
    from app.infrastructure.security.cifrado import ClaveCifradoInvalida
    with pytest.raises(ClaveCifradoInvalida):
        evid.descifrar_texto(arcop.cifrar_texto("x"))
