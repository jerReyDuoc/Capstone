# HU-11 · Especificación de diseño (handoff)

**Historia:** como gestor de proyectos quiero visualizar un listado priorizado de las brechas normativas detectadas
tras el autodiagnóstico, para enfocar los recursos de la empresa en los hallazgos de mayor criticidad.

**Pantallas afectadas:** `/panel/brechas` (rediseñada) y `/panel` Diagnóstico (KPI, gráfico, resumen y la nueva
sección "Brechas en seguimiento"). No requiere cambios en el backend.

## Trazabilidad de criterios de aceptación

| Criterio | Cómo se cumple | Dónde |
|---|---|---|
| 1. Análisis automático de controles No Cumplidos o Parcialmente Cumplidos | Al cargar la evaluación, el panel toma el **estado efectivo** de cada respuesta (el final de la revisión LLM/humana manda sobre el original) y convierte en brecha todo `no_cumplido` y `parcialmente_cumplido`. Se enriquece con el catálogo de brechas y, si la respuesta no trae brecha, con el control (`GET /api/controles`): código, dominio, obligación, criticidad y recomendación. Las `requiere_revision` no se cuentan aún y se informa cuántas quedan. Una franja explica el embudo: *50 controles → 5 no cumplidos y 5 parciales → 10 brechas*. | `lib/adaptadores.ts` (`construirBrechas`), `VistaBrechas` |
| 2. Listado ordenado por severidad (Crítica, Alta, Media, Baja) | El catálogo solo trae impacto Alta/Media/Baja, así que la severidad se calcula con una **matriz impacto × estado** (tabla abajo). El listado se numera (columna *Prioridad*, estable aunque se filtre). Desempate: no cumplidas primero → mayor impacto → dominio menos maduro → código. | `lib/severidad.ts`, tarjetas de severidad, tabla "Cómo se prioriza" |
| 3. Filtro y exportación a dashboard y PDF | **Filtros** combinables: severidad (varias), dominio, estado y búsqueda de texto sin tildes; viven en la URL (compartibles). **PDF**: informe para papel A4 horizontal mediante "Guardar como PDF". **Dashboard**: "Fijar en Diagnóstico" deja el listado filtrado como tarjeta en el panel principal, con conteos recalculados en vivo. **CSV** adicional para dashboards externos (Power BI, Looker Studio, Excel). Todo exporta exactamente lo filtrado. | `lib/filtrosBrechas.ts`, `lib/exportar.ts`, `lib/vistasFijadas.ts`, `InformeBrechas`, `VistasFijadas` |

## Matriz de severidad

|                 | No cumplido | Parcialmente cumplido |
|-----------------|-------------|-----------------------|
| Impacto alto    | **Crítica** | Alta                  |
| Impacto medio   | Alta        | Media                 |
| Impacto bajo    | Media       | Baja                  |

Si el catálogo ya trae "Crítica", se respeta. Sin impacto en catálogo ni control → **Sin clasificar** (se muestra al
final con aviso; nunca se esconde). La regla está en un solo objeto (`MATRIZ_SEVERIDAD`) para que el PO la ajuste.

## Tokens nuevos (`app/globals.css`)

| Token | Valor | Contraste | Uso |
|---|---|---|---|
| `--critico` | `#FF5C7A` | 6,5:1 sobre `--surface` | Severidad Crítica (tarjeta, fila, barra) |
| `--on-critico` | `#1A0208` | 6,7:1 sobre `--critico` | Texto de la insignia sólida "Crítica" |
| `--critico-soft` | `rgba(255,92,122,.16)` | texto 14,4:1 | Fondo de celda/tarjeta activa |
| `--naranja` / `--naranja-soft` | `#F58A4B` / `.14` | 7,9:1 · insignia 6,5:1 | Severidad Alta |

Media y Baja reutilizan `--medio` y `--bajo`. En impresión se redefinen para papel blanco: crítica `#B4123A` (6,8:1),
alta `#C2410C` (5,2:1), media `#A16207` (4,9:1), baja `#15803D` (5,0:1).

**Decisión de color:** el rojo de "Crítica" y el de `--alto` miden 1,07:1 entre sí, indistinguibles para daltónicos.
Por eso "Crítica" se diferencia por **forma** (insignia sólida con texto oscuro) y "Alta" pasa a naranja; además el
nombre de la severidad siempre está escrito (WCAG 1.4.1).

## Layout `/panel/brechas`

```
EYEBROW · Brechas                                   [Evaluación ▾] [Actualizar]
┌ Análisis automático: 50 controles → 5 no cumplidos y 5 parciales → 10 brechas ┐
┌ CRÍTICA 3 ┬ ALTA 4 ┬ MEDIA 1 ┬ BAJA 2 ┐   4 tarjetas = filtro de severidad
┌ Cómo se prioriza (col-5) ┬ Brechas por dominio (col-7) ┐   ≤1279 px: se apilan
┌ Listado priorizado        [Fijar en Diagnóstico] [Exportar CSV] [Exportar PDF] ┐
│ [Buscar……………………] [Dominio ▾] [Estado ▾] [Limpiar filtros]                     │
│ # │ Severidad+estado │ Brecha (código · control · impacto) │ Dominio │ Acción y ruta │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Componentes

| Componente | Props | Estados / interacción |
|---|---|---|
| `TarjetasSeveridad` | `conteo`, `seleccion`, `onAlternar` | Botones `aria-pressed`, selección múltiple; con 0 brechas quedan deshabilitadas salvo que estén activas; check visible al activar |
| `MatrizPriorizacion` | `brechas` | Tabla real (`th scope`), celdas vacías atenuadas; aviso si hay "Sin clasificar" |
| `BadgeSeveridad` | `severidad` | Crítica sólida; resto suave; prefijo "Severidad" para lector de pantalla |
| `BarrasCriticidad` (nombre conservado) | `conteo: Record<Severidad>`, `onSeleccionar?` | Ahora por severidad; Enter abre Brechas filtrado `?severidad=` |
| `InformeBrechas` | `panel`, `brechas`, `filtros`, `emitido` | Solo en `@media print`; encabezados repetidos por página; filas no se cortan |
| `VistasFijadas` | `panel` | Hasta 4 vistas por evaluación; ✕ deja de seguir; "Abrir listado" restaura filtros; tarjeta guía punteada |

## Casos borde

- Evaluación sin brechas → estado positivo "Sin brechas abiertas" (menciona las que siguen en revisión).
- Filtros sin resultados → estado vacío con "Limpiar filtros"; exportaciones deshabilitadas.
- `/api/controles` caído → el análisis sigue solo con el catálogo (no rompe la pantalla).
- URL manipulada (`?severidad=Urgente`) → se ignora el valor inválido.
- localStorage bloqueado (modo privado) → "Fijar" avisa que no se pudo guardar; el resto funciona.
- CSV: celdas que empiezan con `= + - @` se neutralizan (inyección de fórmulas, OWASP).
- Búsqueda con retardo de 300 ms hacia la URL; "Limpiar" no reaplica filtros antiguos.

## Accesibilidad (WCAG 2.1 AA)

| Criterio | Resultado |
|---|---|
| 1.4.1 Uso del color | Severidad siempre escrita; Crítica con forma distinta; barra lateral de fila + etiqueta |
| 1.4.3 / 1.4.11 Contraste | Texto ≥ 4,5:1 (mín. 5,0 insignia Alta en celda Alta); bordes de control 3,6:1 |
| 1.4.10 Reflow | Sin scroll horizontal a 1440, 1280, 1024 y 720 px (zoom 200 %) |
| 2.1.1 Teclado | Tarjetas, matriz, filtros, orden, exportación y ✕ operables con Tab/Enter/Espacio; el foco se conserva al filtrar |
| 4.1.2 / 4.1.3 | `aria-pressed` en conmutadores, `aria-sort` en columnas, conteo y avisos de exportación en `role="status"` |
| 1.3.1 | Matriz y listado son tablas con encabezados; la búsqueda tiene etiqueta y descripción |

## Fuera de alcance / pendientes para el PO

- Las vistas fijadas viven en el navegador. Si se quieren compartidas entre usuarios, se necesita un endpoint de
  preferencias en el backend (basta con reemplazar el `Almacen` de `lib/vistasFijadas.ts`).
- Validar con el PO la matriz de severidad y los textos guía de cada nivel ("Atender de inmediato", etc.).
