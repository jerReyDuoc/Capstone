"""
HU-30 · Reglas de vigencia del contrato de la empresa cliente (lógica pura, sin BD).

El contrato tiene un ESTADO que fija el administrador y unas FECHAS. La SITUACIÓN se
calcula con ambos en cada petición (no se guarda), así un contrato vence solo cuando pasa
su fecha de término, sin cron ni tareas programadas:

  estado (lo fija el admin)    fechas                       situación
  ---------------------------  ---------------------------  -------------------------------
  activo                       hoy < inicio                 pendiente   (aún no empieza)
  activo                       inicio ≤ hoy ≤ término       vigente     ← único con servicio
  suspendido                   hoy ≤ término                suspendido
  suspendido                   término < hoy                (como activo: vencido/finalizado)
  activo                       término < hoy ≤ fin gracia   vencido     (en plazo de gracia)
  terminado                    hoy ≤ fin gracia             terminado   (en plazo de gracia)
  activo / terminado           hoy > fin gracia             finalizado  (retención, HU-25)

Fin del plazo de gracia = (la fecha en que el contrato dejó de regir) + CONTRATO_GRACIA_DIAS.
Esa fecha es la de término pactada o, si el admin lo terminó antes, la de terminación (la
que ocurra primero): terminar un contrato ya vencido no reinicia el plazo.

Qué permite cada situación:
  servicio pagado (cursos, tutor IA, borradores, espacio de la empresa)  solo 'vigente'
  descargar sus documentos                                               todas menos 'finalizado'
  funciones gratuitas (evaluación, resultados, informe PDF, plan) y ARCOP  siempre (no dependen
                                                                          del contrato)

Este módulo no importa SQLAlchemy a propósito: se prueba sin base de datos
(tests/test_hu30_contrato.py) y lo usan el modelo Empresa y las guardas de
app/core/servicio_pagado.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class EstadoContrato(str, Enum):
    """Lo que decide el administrador desde el panel interno."""
    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    TERMINADO = "terminado"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


class SituacionContrato(str, Enum):
    """Lo que resulta de combinar el estado con las fechas (se calcula, no se guarda)."""
    PENDIENTE = "pendiente"
    VIGENTE = "vigente"
    SUSPENDIDO = "suspendido"
    VENCIDO = "vencido"
    TERMINADO = "terminado"
    FINALIZADO = "finalizado"


class MotivoContrato(str, Enum):
    """
    Motivo de una suspensión o terminación. Es una lista cerrada a propósito: un texto
    libre podría traer datos personales y terminaría en la bitácora, que es de solo
    inserción y no se puede corregir.
    """
    NO_PAGO = "no_pago"
    SOLICITUD_CLIENTE = "solicitud_cliente"
    INCUMPLIMIENTO = "incumplimiento"
    FIN_ACUERDO = "fin_acuerdo"
    OTRO = "otro"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


class Operacion(str, Enum):
    RENOVAR = "renovar"
    SUSPENDER = "suspender"
    REACTIVAR = "reactivar"
    TERMINAR = "terminar"


S = SituacionContrato

# Desde qué situación se permite cada operación del administrador.
PERMITIDAS: dict[Operacion, frozenset[SituacionContrato]] = {
    # Renovar fija una nueva fecha de término y deja el contrato activo (también levanta
    # una suspensión o deshace una terminación mientras dure el plazo de gracia).
    Operacion.RENOVAR: frozenset({S.PENDIENTE, S.VIGENTE, S.SUSPENDIDO, S.VENCIDO, S.TERMINADO}),
    # Suspender corta el servicio sin terminar el contrato (p. ej. por falta de pago).
    Operacion.SUSPENDER: frozenset({S.PENDIENTE, S.VIGENTE}),
    # Reactivar levanta la suspensión sin cambiar fechas.
    Operacion.REACTIVAR: frozenset({S.SUSPENDIDO}),
    # Terminar abre el plazo de gracia para descargar documentos.
    Operacion.TERMINAR: frozenset({S.PENDIENTE, S.VIGENTE, S.SUSPENDIDO, S.VENCIDO}),
}


@dataclass(frozen=True)
class Vigencia:
    situacion: SituacionContrato
    fin_gracia: date | None          # solo cuando el contrato dejó de regir

    @property
    def servicio_habilitado(self) -> bool:
        return self.situacion is S.VIGENTE

    @property
    def documentos_disponibles(self) -> bool:
        return self.situacion is not S.FINALIZADO

    @property
    def en_gracia(self) -> bool:
        return self.situacion in (S.VENCIDO, S.TERMINADO)

    def mensaje(self) -> str:
        return MENSAJES[self.situacion].format(
            fin_gracia=self.fin_gracia.strftime("%d-%m-%Y") if self.fin_gracia else "")

    def como_dict(self) -> dict:
        return {
            "situacion": self.situacion.value,
            "servicio_habilitado": self.servicio_habilitado,
            "documentos_disponibles": self.documentos_disponibles,
            "en_plazo_de_gracia": self.en_gracia,
            "documentos_disponibles_hasta": self.fin_gracia.isoformat() if self.fin_gracia and self.en_gracia else None,
            "mensaje": self.mensaje(),
        }


MENSAJES = {
    S.PENDIENTE: "El contrato de tu empresa aún no comienza. El servicio se habilita en su fecha de inicio.",
    S.VIGENTE: "El contrato de tu empresa está vigente.",
    S.SUSPENDIDO: "El servicio de tu empresa está suspendido. Contacta a Therion Labs para reactivarlo.",
    S.VENCIDO: "El contrato de tu empresa venció. Puedes descargar tus documentos hasta el {fin_gracia}; "
               "para seguir usando el servicio, contacta a Therion Labs para renovarlo.",
    S.TERMINADO: "El contrato de tu empresa terminó. Puedes descargar tus documentos hasta el {fin_gracia}.",
    S.FINALIZADO: "El contrato de tu empresa terminó y el plazo para descargar documentos ya venció. "
                  "Tus derechos sobre tus datos personales (ARCOP) siguen disponibles.",
}


def fin_de_gracia(termino: date, fecha_terminacion: date | None, gracia_dias: int) -> date:
    fin_regimen = min(termino, fecha_terminacion) if fecha_terminacion else termino
    return fin_regimen + timedelta(days=gracia_dias)


def evaluar(*, estado: str, inicio: date, termino: date, fecha_terminacion: date | None,
            hoy: date, gracia_dias: int) -> Vigencia:
    if estado == EstadoContrato.SUSPENDIDO.value and hoy <= termino:
        return Vigencia(S.SUSPENDIDO, None)
    if estado == EstadoContrato.TERMINADO.value:
        fin = fin_de_gracia(termino, fecha_terminacion or hoy, gracia_dias)
        return Vigencia(S.TERMINADO if hoy <= fin else S.FINALIZADO, fin)
    # activo, o suspendido cuya fecha de término ya pasó (vence igual que uno activo)
    if hoy < inicio:
        return Vigencia(S.PENDIENTE, None)
    if hoy <= termino:
        return Vigencia(S.VIGENTE, None)
    fin = fin_de_gracia(termino, None, gracia_dias)
    return Vigencia(S.VENCIDO if hoy <= fin else S.FINALIZADO, fin)
