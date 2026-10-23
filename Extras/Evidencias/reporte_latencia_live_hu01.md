# Reporte de latencia - API REST diagnóstico

- **Fecha:** 2026-10-16 01:44:34
- **Modo:** live — http://localhost:8000
- **Requisito:** p95 < 500 ms por endpoint
- **Muestras:** 50 medidas por endpoint + 3 lote(s) de calentamiento con la misma concurrencia; concurrencia 10 (filtro y cerrar, secuenciales)
- **Subida de evidencias incluida:** no
- **Cliente:** Python 3.13.16 en Linux 6.18.33.2-microsoft-standard-WSL2
- **Resultado:** 12/12 endpoints cumplen
- **Arranque en frío (informativo, no evaluado):** primer lote de 10 peticiones simultáneas tras abrir conexiones = 55 ms

| CRUD | Endpoint | Conc. | p50 (ms) | p95 (ms) | máx (ms) | media (ms) | HTTP | Cumple |
|---|---|---:|---:|---:|---:|---:|---|---|
| C | POST filtro (crear/rehacer) | 1 | 16.1 | 21.8 | 23.4 | 16.2 | 200 | ✅ |
| R | GET filtro | 10 | 39.4 | 52.1 | 52.6 | 39.7 | 200 | ✅ |
| R | GET controles aplicables | 10 | 19.6 | 24.1 | 25.7 | 19.9 | 200 | ✅ |
| C | POST respuesta | 10 | 55.1 | 67.2 | 68.0 | 55.2 | 200,201 | ✅ |
| R | GET respuesta | 10 | 29.1 | 43.5 | 44.4 | 30.5 | 200 | ✅ |
| R | GET respuestas de evaluación (paginado) | 10 | 39.2 | 44.4 | 45.3 | 39.0 | 200 | ✅ |
| R | GET evaluación | 10 | 17.2 | 21.3 | 22.3 | 17.0 | 200 | ✅ |
| R | GET progreso del cuestionario | 10 | 38.4 | 43.7 | 44.6 | 37.3 | 200 | ✅ |
| U | POST cerrar (recalcular resumen) | 1 | 18.7 | 30.3 | 30.7 | 19.6 | 200 | ✅ |
| R | GET resumen | 10 | 20.7 | 23.8 | 25.4 | 20.3 | 200 | ✅ |
| U | POST cerrar con 100% N/A | 1 | 15.2 | 25.4 | 33.7 | 16.1 | 200 | ✅ |
| R | GET resumen con 100% N/A (404 esperado) | 10 | 23.7 | 32.1 | 33.1 | 24.0 | 404 | ✅ |
