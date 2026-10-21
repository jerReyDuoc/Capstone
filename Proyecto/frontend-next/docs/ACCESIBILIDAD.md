## Auditoría de accesibilidad: Panel ComplianceAI (HU-13)
**Estándar:** WCAG 2.1 AA | **Fecha:** 20-10-2026 | **Alcance:** /panel, /panel/dominios, /panel/brechas

### Resumen
**Hallazgos:** 5 | **Críticos:** 0 abiertos | **Mayores:** 0 abiertos | **Menores:** 0 abiertos

Durante la implementación se detectaron y corrigieron 5 problemas. Queda pendiente la verificación manual con lector
de pantalla, que debe hacer el equipo antes del cierre del sprint.

### Hallazgos

#### Perceptible
| # | Problema | Criterio | Severidad | Estado |
|---|---|---|---|---|
| 1 | Texto de los gráficos ilegible al escalar el SVG a 1024 px | 1.4.4 Cambio de tamaño | 🟡 Mayor | ✅ Corregido: radar 7/5 columnas en tablet, viewBox reducidos, tope de altura |
| 2 | Los datos de los gráficos solo existían como imagen | 1.1.1 / 1.3.1 | 🔴 Crítico | ✅ Corregido: `figcaption` con resumen en texto + "Ver como tabla" en cada gráfico |
| 3 | Serie de la industria distinguible solo por color | 1.4.1 Uso del color | 🟡 Mayor | ✅ Corregido: siempre punteada; criticidad y nivel siempre con texto |

#### Operable
| # | Problema | Criterio | Severidad | Estado |
|---|---|---|---|---|
| 4 | Al ordenar la tabla el botón se remontaba y se perdía el foco | 2.4.3 Orden del foco | 🟡 Mayor | ✅ Corregido |
| 5 | Puntos de la industria agregaban 4 paradas de Tab redundantes antes de los de la empresa | 2.4.3 | 🟢 Menor | ✅ Corregido: solo la serie de la empresa es enfocable; su etiqueta incluye el valor de la industria |

### Contraste (calculado con la fórmula WCAG)
| Elemento | Primer plano | Fondo | Ratio | Requerido | ¿Cumple? |
|---|---|---|---|---|---|
| Texto principal | `#F1F4F3` | `#0A100E` | 17,35:1 | 4,5:1 | ✅ |
| Texto secundario | `#A9B3AF` | `#0A100E` | 8,92:1 | 4,5:1 | ✅ |
| Texto terciario | `#8A9590` | `#0F1714` | 5,88:1 | 4,5:1 | ✅ |
| Acento / eyebrow | `#14D89E` | `#0A100E` | 10,38:1 | 4,5:1 | ✅ |
| Botón primario | `#03110C` | `#14D89E` | 10,42:1 | 4,5:1 | ✅ |
| Badge alto | `#F2605C` | `#0F1714` | 5,73:1 | 4,5:1 | ✅ |
| Badge medio | `#F2B53F` | `#0F1714` | 9,94:1 | 4,5:1 | ✅ |
| Badge bajo | `#3DBE74` | `#0F1714` | 7,65:1 | 4,5:1 | ✅ |
| Serie industria | `#8FA3FF` | `#0A100E` | 8,10:1 | 3:1 | ✅ |
| Borde de controles | `#567067` | `#0A100E` | 3,58:1 | 3:1 | ✅ |
| Anillo de foco | `#14D89E` | `#050807` | 10,86:1 | 3:1 | ✅ |

### Navegación por teclado (verificada con Playwright)
| Elemento | Orden de Tab | Enter/Espacio | Escape | Flechas |
|---|---|---|---|---|
| "Saltar al contenido" | 1 | Va a `<main>` | — | — |
| Menú lateral | 2–5 | Navega | — | — |
| Selector de evaluación | 6 | Abre la lista | Cierra | Cambia opción |
| Chips de series | 8–9 | Activa/desactiva (`aria-pressed`) | — | — |
| Puntos del radar | 10–13 | Abre el dominio | Oculta tooltip | — |
| Barras por criticidad | siguiente | Filtra el listado | Oculta tooltip | — |
| Encabezados ordenables | en la tabla | Ordena, conserva el foco (`aria-sort`) | — | — |

### Lector de pantalla
| Elemento | Se anuncia como |
|---|---|
| Punto del radar | "Gestión de Riesgos: tu empresa 46,2 de 100, nivel En desarrollo. Industria 52,4, −6,2 pts bajo el promedio. Presiona Enter para ver el detalle." (botón) |
| Barra de criticidad | "Criticidad Alta: 5 brechas, 56 % del total. Presiona Enter para ver el listado." (botón) |
| Contador del menú | "Brechas 9 brechas abiertas" |
| Resultado de filtros | Región `aria-live="polite"`: "Mostrando 5 de 9 brechas" |
| Carga / error | `role="status"` / `role="alert"` |

### Otras comprobaciones automáticas
- Zoom 200 % (viewport 640 px): sin scroll horizontal en las tres pantallas (1.4.10).
- Todos los controles tienen nombre accesible; ningún objetivo mide menos de 24 px y los principales miden 44 px (2.5.5).
- Un solo `h1` por página, ids únicos, `lang="es-CL"`, todos los `select` con `label`.
- `prefers-reduced-motion` desactiva animaciones (2.3.3).

### Pendiente antes del cierre
1. **Prueba manual con NVDA (Windows) y VoiceOver (iPad)** — la auditoría automática no reemplaza al lector real.
2. **Revisión con usuarios en tablet** — validar que el tooltip de la barra compacta y las áreas táctiles se sienten bien.
