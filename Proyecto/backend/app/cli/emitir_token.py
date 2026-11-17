"""
Emisión de tokens de acceso de prueba (solo desarrollo), sin pasar por el login:
    python -m app.cli.emitir_token --usuario 1 --rol referente
"""
import argparse

from app.domain.auth.actor import Rol
from app.infrastructure.security.cripto.contrasenas_y_tokens import emitir_token


def main() -> None:
    p = argparse.ArgumentParser(description="Emite un token de acceso de prueba (solo desarrollo).")
    p.add_argument("--usuario", type=int, required=True,
                   help="usuario_temporal.id, evaluacion.id (encuestado), usuarios_admin.id, "
                        "usuario_definitivo.id (cliente) o usuario_auditor.id (auditor_externo)")
    p.add_argument("--rol", choices=Rol.valores(), required=True)
    p.add_argument("--ttl", type=int, default=None, help="minutos de validez")
    a = p.parse_args()
    print(emitir_token(a.usuario, a.rol, a.ttl))


if __name__ == "__main__":
    main()
