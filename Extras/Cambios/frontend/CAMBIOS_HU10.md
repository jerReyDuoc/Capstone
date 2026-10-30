# HU-10 · Comparativa sectorial en el panel (frontend-next)

## Qué ve el usuario

Hay una página nueva, **Sector** (`/panel/sector`), en el grupo "Gobernanza de IA" de la barra lateral, tanto para quien hizo la evaluación sin cuenta como para la empresa cliente. Responde una sola pregunta: ¿cómo está mi empresa frente a las de mi rubro, sin que eso exponga a ninguna de ellas?

La página se arma así, de arriba hacia abajo:

1. **Advertencia (criterio 3)**, cuando corresponde, antes de los números para que se lean con ese contexto. Con cohorte insuficiente: "Comparación sectorial oculta para proteger a las empresas" (tono ámbar, candado). Con algunas dimensiones ocultas: "Una dimensión sin comparación sectorial". Sin rubro: aviso informativo. Nunca dice cuántas empresas hay, solo el umbral.
2. **Resumen del sector:** nombre del rubro, una frase de posición ("Estás en la mitad central del sector"), una tira 0–100 grande con tu punto, el promedio del sector y su mitad central, y cuatro cifras (tu puntaje, promedio, diferencia, mitad central).
3. **Por dimensión:** cada dimensión con su propia tira, ordenadas de mayor a menor distancia bajo el sector (lo que más conviene atender arriba). Las dimensiones ocultas van al final con la tira rayada.
4. **"Cómo protegemos a las empresas de tu sector"**, plegable, con las cuatro reglas en lenguaje simple.

Además, en **Diagnóstico** y **Dominios** aparece la advertencia en versión compacta, con el enlace "Ver cómo te comparas con tu sector", para que la ausencia del promedio en los gráficos no se lea como un error. La nota de `BarrasDominio` ya no dice "hoy hay 1, la tuya" (revelaba el tamaño de la cohorte).

## Decisión de diseño

La tira es el elemento central y el único con personalidad propia: lo oculto se dibuja como **oculto** (rayado diagonal con un sello de candado), no como vacío, para que el usuario entienda que la información existe pero está protegida. Todo lo demás reutiliza el sistema de la HU-13 (tarjetas, tipografía Space Grotesk / Inter, paleta TherionLabs) para que la página no se sienta pegada desde otro producto.

### Especificación para desarrollo (handoff)

| Marca | Forma | Token |
|---|---|---|
| Tu empresa | punto sólido 16 px (22 px en el resumen) con anillo | `--serie-empresa` |
| Promedio del sector | trazo vertical discontinuo 2 px | `--serie-industria` |
| Mitad central (p25–p75) | banda con borde, 16 % de opacidad | `--serie-industria` |
| Meta de cumplimiento | trazo vertical punteado 2 px | `--serie-meta` |
| Oculto (k < 5) | rayado 135° sobre `--surface-2`, borde `--line-control`, sello con candado | `--medio` en el icono |

Layout de cada fila: tres columnas (nombre 1fr · tira 2,6fr · valores) desde 1101 px; bajo 1100 px los valores pasan a una segunda línea; bajo 720 px todo se apila y el sello del rayado se oculta (lo cubren la etiqueta "Sin comparación", el valor "Oculto" y el `aria-label`). En el rayado, el sello se dibuja del lado opuesto a tu punto para no taparlo. Casos borde: backend previo sin bloque `sector` (se usa el panel sin comparación, sin romper), rubro nulo, cohorte suficiente pero sin percentiles (< 10 empresas: sin banda ni cifra "mitad central"), y valores fuera de 0–100 (se acotan a la tira).

### Revisión de accesibilidad (WCAG 2.1 AA)

Ninguna marca depende solo del color (1.4.1): punto, discontinuo, punteado, banda y rayado son formas distintas, y la leyenda lista solo las que aparecen. Cada tira es `role="img"` con un `aria-label` completo ("Datos: tu empresa 38 de 100; promedio del sector 60; mitad central del sector entre 47 y 72; meta 75."). Todos los textos usan tokens que ya pasan 4,5:1 sobre `--surface`; el borde del rayado usa `--line-control` (≥ 3:1, 1.4.11). El plegable es un `<details>` nativo con área táctil de 44 px y la flecha respeta `prefers-reduced-motion`. La advertencia es contenido estático (`<aside>` con `aria-label`), no `role="alert"`, porque no aparece como reacción a una acción.

### Textos (UX copy)

Se evitó la palabra "cohorte" y la "k" en todo lo que ve el cliente: se habla de "grupo", "empresas de tu sector" y "promedio". La advertencia dice qué pasa, por qué y cuándo cambia ("Aparecerá solo cuando 5 o más empresas de tu sector hayan completado la evaluación; mientras tanto, compárate con la meta"). No se muestran códigos internos.

## Archivos

Nuevos: `app/panel/sector/page.tsx`, `components/vistas/VistaSector.tsx`, `components/sector/TiraSector.tsx`, `components/sector/AvisoCohorte.tsx`, `components/sector/sector.module.css`, `lib/sector.ts`, `tests/hu10_sector.test.ts`.

Modificados: `lib/types.ts` (`SectorApi`, `SectorVista`, `PosicionSector`; campos nuevos en `DominioVista` y `PanelVista`), `lib/adaptadores.ts` (`construirSector`, defensa en profundidad: con cohorte insuficiente se descarta cualquier dato del sector aunque llegara; `notaIndustria` sin conteos), `lib/demo.ts` (sector con una dimensión oculta), `components/shell/Sidebar.tsx`, `components/ui/Icon.tsx` (icono `sector`), `components/vistas/VistaDiagnostico.tsx`, `components/vistas/VistaDominios.tsx`, `tests/hu12_capacitacion.test.ts`, `tests/adaptadores.test.ts`.

No hubo que tocar los BFF: la página usa `GET /evaluaciones/{id}/comparativa`, que ya estaba permitido en los tres proxys.
