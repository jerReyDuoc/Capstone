# HU-13 · Especificación de diseño (handoff)

**Historia:** como usuario quiero navegar por un panel web intuitivo con gráficos de madurez, resumen de brechas y
navegación fluida, para gestionar la gobernanza de IA de mi empresa desde computadores o tablets.

## Cumplimiento de criterios de aceptación

| Criterio | Cómo se cumple | Evidencia |
|---|---|---|
| 1. Responsivo ≥ 1024 px | Grilla de 12 columnas; ≥ 1280 px barra lateral completa (248 px); 1024–1279 px barra compacta con íconos y tooltip; < 1024 px la barra pasa arriba y todo se apila. Sin scroll horizontal en 1024, 1280 y 1440. | `docs/capturas/*_1024.png`, `*_1440.png` |
| 2. Gráficos interactivos de radar y barras | Radar de madurez (empresa vs. industria, series activables, tooltip, Enter abre el dominio). Barras por criticidad (cada barra filtra el listado). Barras horizontales empresa vs. industria por dominio. Todos con hover, foco de teclado y vista de tabla. | Pantallas Diagnóstico y Brechas |
| 3. WCAG 2.1 AA y mockups | Contrastes ≥ 4,5:1 en texto y ≥ 3:1 en componentes; navegación completa por teclado; alternativas en texto/tabla. Composición basada en el mockup "Cyber_Audit / ComplianceAI" (barra lateral, título "Diagnóstico", resumen de riesgo, brechas por prioridad). | `docs/ACCESIBILIDAD.md` |

## Tokens de diseño (`app/globals.css`)

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#050807` | Fondo de página (con grilla sutil y halo verde arriba a la izquierda, como el sitio) |
| `--surface` / `--surface-2` / `--surface-3` | `#0A100E` / `#0F1714` / `#142019` | Tarjetas, elementos anidados, inputs |
| `--line-strong` / `--line-control` | `#24332D` / `#567067` | Borde de tarjetas / borde de controles (3,6:1) |
| `--text` / `--text-muted` / `--text-subtle` | `#F1F4F3` / `#A9B3AF` / `#8A9590` | Texto principal / secundario / terciario |
| `--accent` | `#14D89E` | Verde menta de la marca: botón primario, ítem activo, serie "Tu empresa" |
| `--accent-strong` | `#0BAF80` | Rellenos de barras (como las barras del bloque "Automatización") |
| `--on-accent` | `#03110C` | Texto sobre botón primario |
| `--alto` / `--medio` / `--bajo` | `#F2605C` / `#F2B53F` / `#3DBE74` | Criticidad y niveles (rojo, ámbar, verde del mockup) |
| `--serie-industria` | `#8FA3FF` | Serie de referencia (siempre punteada) |

Tipografía: **Space Grotesk** (títulos, cifras) e **Inter** (texto), cargadas con `next/font`. Escala en `rem`.
Radios 8/12/18 px y píldora para botones; espaciado en múltiplos de 4.

## Layout

```
┌──────────┬───────────────────────────────────────────────────────┐
│ Marca    │ EYEBROW · Título                 [Evaluación ▾] [↻]   │
│          ├─────────────┬─────────────┬─────────────┬─────────────┤
│ Diagnós. │ Madurez gen.│ Nivel       │ Brechas     │ Controles   │  4 × col-3
│ Dominios ├─────────────┴─────────┬───┴─────────────┴─────────────┤
│ Brechas  │ Radar de madurez      │ Brechas por prioridad         │  col-7 / col-5
│          ├───────────────────────┴──┬────────────────────────────┤
│          │ Comparativa industria    │ Resumen de brechas (top 4) │  col-6 / col-6
│ Ley      ├──────────────────────────┴────────────────────────────┤
│ 21.719   │ Callout "De la señal a la decisión"                   │
└──────────┴───────────────────────────────────────────────────────┘
```

## Componentes

| Componente | Props | Estados / interacción |
|---|---|---|
| `RadarMadurez` | `dominios`, `onSeleccionar?` | Hover/foco → tooltip; Enter/Espacio → detalle del dominio; chips activan series; "Ver como tabla"; < 3 dominios → mensaje + tabla |
| `BarrasCriticidad` | `conteo`, `onSeleccionar?` | Barra con 0 brechas queda deshabilitada (`aria-disabled`); "Sin clasificar" solo aparece si hay |
| `BarrasDominio` | `dominios`, `onSeleccionar?` | Bandas de nivel de fondo; barra punteada = industria; sin benchmark → solo empresa |
| `Kpi` | `icono`, `etiqueta`, `valor`, `sufijo?`, `pista?`, `medidor?` | Medidor con `role="meter"` |
| `PageHeader` | `eyebrow`, `titulo`, `subtitulo` | Selector de evaluación (cambia `?evaluacion=`) y botón Actualizar |
| `EstadoPanel` | render-prop con el `PanelVista` | `cargando` (skeleton, `role=status`), `sin-evaluaciones`, `sin-resumen` (404), `error` (`role=alert` + Reintentar) |

## Casos borde contemplados

- Evaluación sin resumen (404 de `/resumen`): estado explicativo, el selector sigue disponible.
- Rubro sin benchmark o evaluación sin rubro: `/comparativa` falla y el panel sigue sin la serie de industria.
- Respuesta incumplida sin brecha de catálogo: se muestra como "Sin clasificar".
- Más de 100 respuestas: el cliente recorre todas las páginas.
- Criticidad con mayúsculas o "Crítica": se normaliza a Alta/Media/Baja.
- Cambios rápidos de evaluación: las peticiones anteriores se cancelan (`AbortController`).

## Movimiento

Transiciones de 180 ms (`cubic-bezier(.2,.7,.2,1)`) en hover/foco y 600 ms en el medidor. Todo se desactiva con
`prefers-reduced-motion: reduce`.
