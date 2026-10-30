# HU-10 · Comparativa de madurez contra el sector con k-anonimato (backend)

**Historia.** Como Analista de Riesgos, quiero comparar los puntajes de madurez contra el sector industrial, asegurando que si la muestra es pequeña (k < 5) los datos se oculten, para proteger la identidad de las empresas competidoras.

## Qué cambia

Antes existía una comparativa con el rubro (HU-12/HU-13) que ocultaba el promedio con menos de `COMPARATIVA_MIN_MUESTRAS = 3` **evaluaciones**. Eso no protegía a las empresas: contaba evaluaciones (una empresa que se reevaluaba tres veces "desbloqueaba" el promedio sola), devolvía el número exacto de evaluaciones aunque estuviera bajo el umbral y `GET /api/evaluaciones/benchmark` publicaba sin filtro máximo y mínimo, que siempre son el puntaje de una empresa concreta.

Con la HU-10 la cohorte **k** pasa a ser el número de **organizaciones distintas** del rubro y toda publicación del sector pasa por una sola regla (`app/application/benchmark/k_anonimato.py`).

| Criterio | Cómo se cumple |
|---|---|
| C1 · Promedios agregados por sector | `UpdateBenchmarkUseCase` guarda por rubro una fila por dimensión y una fila con `dominio_id = NULL` con el puntaje **general** (promedio ponderado por preguntas, igual que `/resumen`). Se exponen en `GET /api/evaluaciones/benchmark` y en el bloque `sector` de `GET /api/evaluaciones/{id}/comparativa`. |
| C2 · Supresión si k < 5 | `publicar()` devuelve todo en `null` (promedio, mediana, percentiles, diferencia, posición **y el propio k**) cuando la cohorte tiene menos de `K_ANONIMATO_MINIMO = 5` empresas. Si el rubro completo está suprimido, ninguna dimensión se publica. El informe PDF usa la misma regla. |
| C3 · Advertencia en la interfaz | `sector.advertencia = {codigo, mensaje}` con `COHORTE_INSUFICIENTE`, `COHORTE_PARCIAL` (algunas dimensiones ocultas) o `SIN_RUBRO`. El mensaje dice el umbral, nunca cuántas empresas hay. |

## Defensas adicionales (análisis de riesgo)

Una supresión k < 5 ingenua se puede esquivar. Por eso se agregaron estas reglas, todas en `k_anonimato.py` y probadas en `tests/test_hu10_benchmark_sectorial.py`:

1. **k cuenta organizaciones, no evaluaciones.** La identidad es la empresa cliente; si no hay, el usuario temporal del encuestado; de cada una cuenta solo su evaluación más reciente. Repetir la encuesta no infla k.
2. **No se revela k bajo el umbral.** Saber que en un rubro hay 2 empresas ya acota quiénes son.
3. **Nunca se publican máximo ni mínimo.** Siguen calculándose en la tabla (uso interno) pero no salen por la API.
4. **Mediana y percentiles 25/75 solo con `K_ANONIMATO_DISTRIBUCION = 10` empresas o más.** Con 5 empresas el percentil 25 coincide exactamente con el puntaje de la segunda empresa más baja.
5. **Promedio publicado en enteros.** Mitiga el ataque de diferenciación: quien ve el promedio con 5 empresas y luego con 6 podría despejar el puntaje de la nueva (`x = p6·6 − p5·5`). Con enteros el error del despeje es de hasta ±5,5 puntos.
6. **En production `K_ANONIMATO_MINIMO` no puede ser menor que 5** (validación al arrancar).

**Riesgo residual (documentado).** El redondeo no elimina del todo la diferenciación si un atacante observa muchas altas sucesivas; la mitigación completa sería publicar el benchmark solo con el cron diario (no al completar), lo que retrasa la comparativa un día. Se deja `BENCHMARK_AL_COMPLETAR` como está (decisión de HU-12) y el riesgo queda anotado para el PO. Tampoco se puede impedir que alguien registre varias "empresas" falsas con usuarios temporales distintos para completar la cohorte; las evaluaciones marcadas de prueba (HU-19) ya se excluyen y el admin puede marcar las sospechosas con `PATCH /api/evaluaciones/{id}/prueba`.

## Archivos

Nuevos:

- `app/application/benchmark/__init__.py`, `k_anonimato.py` (reglas puras), `sector.py` (lectura con supresión y advertencias)
- `migrations/versions/a7c4e2f9d1b3_hu10_k_anonimato_benchmark.py` (`benchmark.total_empresas`, `percentil_25`, `percentil_75`; revisa `f1d6b3a8c2e4`)
- `scripts/recalcular_benchmark.py`
- `tests/test_hu10_benchmark_sectorial.py`

Modificados:

- `app/application/use_cases/update_benchmark.py` (k por organización, fila general, percentiles)
- `app/api/routes/reportes.py` (`/benchmark` y `/comparativa` con supresión y bloque `sector`)
- `app/application/informes/carga.py`, `analisis.py`, `pdf_informe.py` (PDF: "Oculto: menos de 5 empresas")
- `app/domain/models/benchmark.py`, `app/core/catalogo_datos_personales.py` (T-06: columnas nuevas sin datos personales)
- `app/core/config.py` (`K_ANONIMATO_MINIMO`, `K_ANONIMATO_DISTRIBUCION`; **se elimina `COMPARATIVA_MIN_MUESTRAS`**)
- `tests/test_hu12_plan_formativo.py` (usa `K_ANONIMATO_MINIMO`)
- `Proyecto/.env.example`, `Proyecto/README.md`

## Contrato de la API

`GET /api/evaluaciones/{id}/comparativa` agrega `k_minimo` y `sector`:

```json
"sector": {
  "rubro_id": 1, "rubro": "Retail", "k_minimo": 5,
  "cohorte_suficiente": true, "empresas": 12,
  "promedio": 58, "mediana": 57, "percentil_25": 45, "percentil_75": 70,
  "tu_puntaje": 52.4, "diferencia": -5.6, "posicion": "franja_central",
  "dimensiones_publicadas": 3, "dimensiones_suprimidas": 1,
  "advertencia": {"codigo": "COHORTE_PARCIAL", "mensaje": "..."}
}
```

Cada fila de `comparativas` agrega `dominio_id`, `percentil_25`, `percentil_75`, `cohorte_suficiente`, `empresas` y `posicion` (`bajo_cuartil_inferior`, `franja_central`, `sobre_cuartil_superior`, o sin percentiles `bajo_promedio`, `en_promedio`, `sobre_promedio`). **Cambios incompatibles:** `muestras` ahora es `null` con cohorte insuficiente, y `maximo_industria` / `minimo_industria` ya no existen. `GET /api/evaluaciones/benchmark` devuelve `cohorte_suficiente`, `empresas`, `promedio`, `mediana`, `percentil_25`, `percentil_75` (sin `maximo`, `minimo` ni `total_evaluaciones`) e incluye la fila general con `dominio_id: null`.

## Cómo probar

Después de migrar hay que recalcular una vez (las filas antiguas no tienen `total_empresas` y quedan suprimidas hasta el siguiente recálculo):

```
docker compose exec worker python scripts/recalcular_benchmark.py
docker compose exec worker pytest tests/test_hu10_benchmark_sectorial.py tests/test_hu12_plan_formativo.py -v
```

Para ver la comparativa con datos en local, con menos de 5 empresas de prueba basta `K_ANONIMATO_MINIMO=1` en el `.env` (solo desarrollo; en production el arranque lo rechaza).
