"""
RUT chileno (HU-27: RUT de la empresa cliente).

Acepta 76.123.456-7, 76123456-7, 761234567 o con k minúscula; guarda 76123456-7.
Valida el dígito verificador con el algoritmo módulo 11.
"""
import re

_LIMPIO = re.compile(r"^(\d{1,8})([0-9K])$")


class RutInvalidoError(ValueError):
    pass


def digito_verificador(cuerpo: str) -> str:
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar_rut(rut: str) -> str:
    """Devuelve el RUT como 76123456-7 o lanza RutInvalidoError."""
    limpio = re.sub(r"[.\s-]", "", (rut or "")).upper()
    m = _LIMPIO.match(limpio)
    if not m:
        raise RutInvalidoError("El RUT debe tener el formato 76.123.456-7.")
    cuerpo, dv = m.group(1).lstrip("0") or "0", m.group(2)
    if int(cuerpo) < 1_000_000:
        raise RutInvalidoError("El RUT no es válido.")
    if digito_verificador(cuerpo) != dv:
        raise RutInvalidoError("El dígito verificador del RUT no es correcto.")
    return f"{cuerpo}-{dv}"


def rut_valido(rut: str) -> bool:
    try:
        normalizar_rut(rut)
        return True
    except RutInvalidoError:
        return False
