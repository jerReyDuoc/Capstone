# Reporte de latencia - API REST diagnóstico

- **Fecha:** 2026-10-11 20:22:51
- **Modo:** live — http://127.0.0.1:8000
- **Requisito:** p95 < 500 ms por endpoint
- **Muestras:** 50 medidas por endpoint + 3 lote(s) de calentamiento con la misma concurrencia; concurrencia 10 (filtro y cerrar, secuenciales)
- **Subida de evidencias incluida:** sí
- **Cliente:** Python 3.13.3 en Windows 11
- **Resultado:** 12/13 endpoints cumplen
- **Arranque en frío (informativo, no evaluado):** primer lote de 10 peticiones simultáneas tras abrir conexiones = 2259 ms

| CRUD | Endpoint | Conc. | p50 (ms) | p95 (ms) | máx (ms) | media (ms) | HTTP | Cumple |
|---|---|---:|---:|---:|---:|---:|---|---|
| C | POST filtro (crear/rehacer) | 1 | 36.9 | 48.0 | 53.6 | 37.4 | 200 | ✅ |
| R | GET filtro | 10 | 85.0 | 178.8 | 180.0 | 98.6 | 200 | ✅ |
| R | GET controles aplicables | 10 | 171.1 | 542.7 | 547.5 | 227.4 | 200 | ❌ |
| C | POST respuesta | 10 | 94.4 | 177.6 | 180.6 | 110.8 | 201 | ✅ |
| R | GET respuesta | 10 | 36.0 | 43.8 | 44.9 | 36.9 | 200 | ✅ |
| R | GET respuestas de evaluación (paginado) | 10 | 48.2 | 76.9 | 79.1 | 52.3 | 200 | ✅ |
| R | GET evaluación | 10 | 19.4 | 21.9 | 22.3 | 18.7 | 200 | ✅ |
| C | POST evidencia (upload) | 10 | 102.5 | 131.2 | 132.3 | 106.0 | 202 | ✅ |
| R | GET evidencia | 10 | 25.7 | 31.0 | 32.9 | 25.5 | 200 | ✅ |
| U | POST cerrar (recalcular resumen) | 1 | 30.3 | 48.8 | 55.0 | 32.8 | 200 | ✅ |
| R | GET resumen | 10 | 27.7 | 36.1 | 38.3 | 28.1 | 200 | ✅ |
| U | POST cerrar con 100% N/A | 1 | 22.4 | 27.8 | 92.4 | 23.5 | 200 | ✅ |
| R | GET resumen con 100% N/A (404 esperado) | 10 | 22.3 | 25.5 | 27.1 | 21.8 | 404 | ✅ |
