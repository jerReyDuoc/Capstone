# Propuesta de identidad visual · ComplianceAI (Fase 11, para validar)

**Estado:** propuesta. No está aplicada en el producto: la auditoría pide validarla antes de implementarla a gran escala. Las capturas se tomaron inyectando `propuesta_tema_claro.css` (solo tokens) sobre la versión actual.

## Problema

El producto se ve como una plantilla SaaS de IA genérica (fondo negro con resplandor y cuadrícula, verde menta neón, eyebrows en mayúsculas espaciadas, filas de 4 tarjetas con ícono). En un producto de **cumplimiento legal** eso resta credibilidad.

## Propuesta

| Decisión | Hoy | Propuesta |
|---|---|---|
| Tema por defecto | Oscuro (`#050807`) con resplandor radial y cuadrícula | **Claro** cálido (`#f7f6f2` fondo, `#ffffff` tarjetas), sin decoración de fondo. El oscuro queda como opción |
| Títulos | Space Grotesk | **Serif editorial** (Source Serif 4, vía `next/font`) solo en títulos |
| Cuerpo | Inter | Inter (se mantiene: muy legible). Máximo dos familias |
| Acento | Verde menta neón `#14d89e` | Verde sobrio **`#0d6b52`**, solo como acento puntual (botón principal, estado activo, "Cumplido") |
| Eyebrow verde en mayúsculas | Sobre cada título | Se elimina |
| Íconos de IA | "Chispa" para todo | Ícono descriptivo de la acción (mensaje, lupa, documento) |

### Paleta y contraste (WCAG 2.1 AA)

Calculado con la fórmula de luminancia relativa de WCAG. "Suave" = el fondo tintado de la insignia (10 % del color sobre blanco).

| Token | Color | Sobre blanco | Sobre fondo `#f7f6f2` | Sobre su fondo suave |
|---|---|---|---|---|
| `--text` | `#1c1f1d` | 16,6:1 | 15,4:1 | — |
| `--text-muted` | `#4a4f4b` | 8,4:1 | 7,7:1 | — |
| `--text-subtle` | `#5f645c` | 6,1:1 | 5,6:1 | — |
| `--accent` | `#0d6b52` | 6,5:1 | 6,0:1 | 5,6:1 |
| Texto blanco sobre `--accent` (botón) | — | 6,5:1 | — | — |
| `--severity-critical` | `#b4123a` | 6,8:1 | 6,3:1 | 5,7:1 |
| `--severity-high` | `#a8460a` | 5,9:1 | 5,5:1 | 5,1:1 |
| `--severity-medium` | `#7d5800` | 6,4:1 | 5,9:1 | 5,6:1 |
| `--severity-low` | `#355a8c` | 7,0:1 | 6,5:1 | 6,1:1 |
| `--severity-none` | `#56606b` | 6,4:1 | 5,9:1 | 5,6:1 |
| `--nivel-gestionado` | `#2f5fa8` | 6,3:1 | 5,8:1 | 5,5:1 |
| `--line-control` (bordes de controles) | `#7c7a70` | 4,3:1 | 4,0:1 | ≥ 3:1 (WCAG 1.4.11) |
| Desactivado: texto `#5f645c` sobre `#ecebe6` | — | — | — | 5,1:1 |

La escala de severidad conserva la **forma** de cada nivel (octágono, triángulo, rombo, círculo hueco) de la Fase 2, así que se distingue también en escala de grises.

### Portada (pendiente de diseño de contenido)

- Quitar la píldora con punto brillante y las olas animadas.
- Reorganizar alrededor del contenido: **vista previa real del resultado** del diagnóstico (bloque de puntaje + barras por dominio, con datos de ejemplo) y **cuánto demora** completarlo (en el orden de 15–20 minutos según el número de preguntas; confirmar el dato con el PO).
- Evitar la estructura de plantilla (3 pasos + 4 íconos + checklist + CTA final).

## Capturas (prototipo por tokens)

En `propuesta_capturas/`:

- `propuesta_diagnostico_1440.png`
- `propuesta_brechas_1440.png`
- `propuesta_brechas-movil_390.png`
- `propuesta_portada_1440.png` (solo cambia la paleta: la reorganización de la portada está pendiente)

> En las capturas los títulos usan la serif disponible en el equipo (Georgia como respaldo); con `next/font` se cargaría Source Serif 4.

## Cómo se implementaría (si se aprueba)

1. Pasar los valores de `propuesta_tema_claro.css` a `:root` en `app/globals.css` y mover el tema oscuro actual a `[data-tema="oscuro"]` (con selector en el menú de cuenta y `prefers-color-scheme`).
2. Cambiar `Space_Grotesk` por `Source_Serif_4` en `app/layout.tsx` (`next/font/google`, o mejor `next/font/local` para evitar la falla intermitente de descarga que documenta el Dockerfile).
3. Quitar `.eyebrow` de `PageHeader` y de los encabezados propios de cada página.
4. Revisar los colores fijos que quedan fuera de tokens (`.tooltip`, `.dialogo::backdrop`, gráficos SVG).
5. Recalcular contraste del tema oscuro si se conserva como opción.

**Validar con:** PO y 3–5 usuarios (¿transmite más confianza?, ¿se lee mejor en pantallas con mucho brillo?).
