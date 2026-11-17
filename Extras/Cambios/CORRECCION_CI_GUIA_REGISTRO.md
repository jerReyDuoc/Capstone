# Corrección CI · rutas de la guía del asistente de registro (17-11)

**Síntoma:** el push "Correciones y mejoras al Asistente de Registro" (fe0cebd) dejó en rojo
`CI / Backend · pytest + cobertura (>= 70 %)` y, por arrastre, `CI / CI aprobado`.

**Causa:** el commit agregó dos endpoints nuevos (`GET /api/asistente/guia` y `POST /api/asistente/guia`)
pero no los clasificó en la matriz de autorización. La prueba
`tests/integracion/test_hu20_autorizacion.py::test_todas_las_rutas_estan_clasificadas` exige que toda
ruta de la API esté en alguna lista de esa matriz, y falla con "Rutas sin clasificar en HU-20".

**Corrección:** se agregan ambas rutas a `RUTAS_CON_TOKEN_PROPIO`, junto a las demás del asistente.
Así también queda probado que sin sesión responden 401 (`test_ruta_con_token_propio_exige_token`).
Las pruebas de 403 y del flujo completo ya están en `tests/ia/test_guia_registro.py`.

**Archivo modificado:** `Proyecto/backend/tests/integracion/test_hu20_autorizacion.py` (+5 líneas).

**Regla para la próxima vez:** cada endpoint nuevo debe agregarse a una de las listas de
`test_hu20_autorizacion.py` en el mismo commit.
