# Handoff · Auditoría UX/UI de ComplianceAI (16-nov-2026) + T-11 a T-14

**Fecha:** 18-nov-2026 · **Alcance:** `Proyecto/frontend-next` (Fases 1 a 10 de la auditoría; Fase 11 como propuesta) y `Proyecto/backend` (tareas T-11, T-12, T-13 y T-14).
**Sin commits ni push.** Todo va en el zip: en `Proyecto/` solo código, configuración, tests y README; documentación y evidencias en `Extras/`.

> ⚠ **Aviso de tamaño:** el cambio agrega **~275 KB de texto nuevo dentro de `Proyecto/`** (≈130 KB en archivos modificados y ≈145 KB en archivos nuevos; el set de ataques `ataques_asistente.jsonl` pesa ≈20 KB). Supera el umbral de ~50 KB.
>
> ⚠ **Archivo a eliminar:** `Proyecto/frontend-next/components/charts/RadarMadurez.tsx` (el radar se reemplazó por barras; un zip no puede representar un borrado: hay que borrarlo a mano al aplicar el cambio).
>
> ⚠ **`package-lock.json`:** no se generó uno nuevo; se **actualizó el existente** (+64 líneas) para agregar `@playwright/test@1.52.0` como dependencia de desarrollo. Es imprescindible para que `npm ci` (Docker y CI) siga funcionando.

---

## 1. Estado por fase y punto

Leyenda: ✅ hecho · 🟡 parcial · ⏳ pendiente.

### Fase 1 — Desborde horizontal en móvil

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 1.1 KPI que se cortan | ✅ | `app/globals.css` (bloque "Fase 1": `min-width:0` en hijos de grid, `overflow-wrap:anywhere`, KPI a 1 columna < 600 px, `.select` sin `min-width` fijo) | 390 px: `/panel` sin scroll lateral |
| 1.2 Matriz "Cómo se prioriza" | ✅ | `MatrizPriorizacion.tsx`, `.scroll-x` en `globals.css` (scroll interno contenido + sombra que indica que hay más) | `/panel/brechas` a 390 px |
| 1.2 Tabla → tarjetas < 600 px | ✅ | `VistaBrechas.tsx` (`.table-tarjetas` + `data-label` por celda) | Cada brecha es una tarjeta con prioridad, severidad, descripción, acción y ruta |
| 1.2 Barras por dominio | ✅ | `.domain-filter` < 600 px: etiqueta arriba, barra a todo el ancho, valor visible | |
| 1.3 Cerrar brechas | ✅ | `globals.css` (botones a todo el ancho, nombres de archivo que se cortan de línea) | `/panel/remediacion` a 390 px con un archivo de nombre largo |
| 1.4 Barrido general | ✅ | Se encontró y corrigió una causa general: textos `.sr-only` (absolutos) que escapaban de los contenedores con scroll (`position: relative` en `.scroll-x` y `.table-wrap`) | Prueba nueva en verde en 24 rutas |
| 1.5 Prueba de regresión | ✅ | `tests/e2e/desborde-movil.spec.ts`, `tests/e2e/simulacion.ts`, `tests/e2e/fixtures/*`, `playwright.config.ts`, script `npm run test:e2e` | Ver §5. Se comprobó que **falla** al reintroducir un ancho fijo (`h1.page-title` de 560 px) e indica el elemento culpable |

### Fase 2 — Color y vocabulario de severidad

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| Regla de color (verde solo marca y "Cumplido") | ✅ | Tokens `--severity-*`, `--nivel-*`, `--barra-neutra` en `globals.css`; `--bajo` ya no es verde; `lib/madurez.ts` (tonos `nivel-*`), `MisEvaluaciones.tsx`, `VistaDominios.tsx`, `sector.module.css`, `EstadoProteccionDatos.tsx` (tenía "Baja" en verde) | `grep "tone-ok"` ya no aparece en severidades; barras de brechas por dominio en gris |
| Escala única con forma propia | ✅ | `.sev-forma-*` (crítica = octágono sobre insignia sólida, alta = triángulo, media = rombo, baja = círculo hueco, sin clasificar = punteado); `claseBadgeSeveridad()` en `lib/severidad.ts`; `BadgeSeveridad` | Se distinguen en escala de grises; prueba `tests/auditoria_ux.test.ts` |
| Vocabulario único | ✅ | `lib/severidad.ts` (diccionario central `VOCABULARIO_SEVERIDAD`, `IMPACTO_TEXTO/TONO`); `lib/planFormativo.ts` (`PRIORIDAD_TEXTO` = Crítica/Alta/Media/Baja); `PasoControl.tsx` ("Impacto alto" en vez de "Criticidad alta") | Cuestionario, Brechas y Capacitación dicen lo mismo |

Contrastes de la escala nueva (sobre `--surface #0a100e` / sobre su fondo suave): crítica `#ff4d5e` 5,9:1 / 5,1:1 · alta `#ff8a3d` 8,2:1 / 6,7:1 · media `#f5c542` 11,8:1 / 9,1:1 · baja `#8fb0d9` 8,6:1 / 6,9:1 · sin clasificar `#93a0a8` 7,2:1 / 5,9:1 · texto sobre insignia crítica sólida 6,1:1 · "Gestionado" `#7fb2ff` 8,9:1 · barra neutra `#6f8a99` 4,6:1 sobre `--surface-3` (1.4.11).

### Fase 3 — Estado desactivado inconfundible

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| Estilo desactivado | ✅ | `.btn:disabled, .btn[aria-disabled="true"]` en `globals.css`: fondo gris, texto gris 6,4:1, sin marca, sin hover, `cursor:not-allowed` | Comparar "Seguir" activo/desactivado |
| Motivo visible + accesibilidad | ✅ | Componente nuevo `components/ui/BotonConMotivo.tsx` (`aria-disabled`, sigue enfocable, motivo conectado con `aria-describedby`) aplicado en "Seguir", "Crear empresa y traspasar", "Guardar plazo", "Completar y ver resultados", "Revisar y publicar", veredicto/decisión de la bandeja, "Agregar flujo", "Nueva evaluación", "Dejar vigente", "Generar borrador", "Usar mi registro como evidencia" | |
| Informes sin actividades | ✅ | `RegistroActividades.tsx`: "Informe del registro", "Informe RoPA" y "Revisión interna" desactivados con el motivo | Con 0 actividades no se puede abrir ningún informe |
| Una sola acción principal | ✅ | Sin "Nueva actividad" mientras el estado vacío muestra "Registrar la primera actividad" | |

Nota: los botones que se desactivan solo **mientras** se guarda (el propio botón dice "Guardando…") y la paginación (anterior/siguiente en la primera/última página) quedaron con `disabled` normal: el motivo ya es evidente.

### Fase 4 — Header del admin y alineación del cuestionario

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 4.A Menú de cuenta | ✅ | `components/ui/MenuCuenta.tsx` (teclado: Enter/Espacio/↓ abren, ↑/↓/Inicio/Fin recorren, Esc cierra y devuelve el foco); `BarraAdmin.tsx`, `admin.module.css` | Medido: header de **64 px (una línea)** a 1280 y 1440 px |
| 4.A Móvil compacto | ✅ | Marca + "Secciones" (desplegable) + cuenta | |
| 4.A "Actualizar" | ✅ | Reemplazado por "Actualizado hace X" + ícono (Fase 5.D) | |
| 4.B Contenedor compartido | ✅ | `Marco.tsx` (`ancho="amplio"` para encabezado, contenido y pie) y `app/encuesta/page.tsx`. **Causa** (historial): HU-30 (eb836c0, 28-oct) agregó `.contenedorAncho` (1440 px) solo al contenido para poner pregunta y respuesta lado a lado; encabezado y pie siguieron en 1180 px | Medido a 1440 px: borde izquierdo de logo, título y tarjeta = 20 px los tres |

### Fase 5 — Quitar repeticiones en el panel

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 5.A Bloque único de resultado | ✅ | `VistaDiagnostico.tsx` (puntaje + nivel + una línea de brechas) | |
| 5.A Una acción principal | ✅ | Queda "Descargar PDF" (principal) y "Enviar por correo" (secundaria); se quitó "Actualizar" | |
| 5.A Callout del sector debajo del gráfico | ✅ | `AvisoCohorte` va después de los gráficos | |
| 5.A Radar → barras | ✅ | Nuevo `components/charts/BarrasComparadas.tsx` (empresa sólida vs. rubro rayado, meta como marca punteada; resumen en texto y "Ver como tabla"); también en Cerrar brechas | No queda radar en el producto |
| 5.A Frase de remate | ✅ | Eliminada | |
| 5.B Resumen compacto que filtra | ✅ | `TarjetasSeveridad.tsx` → `ChipsSeveridad` (una fila) | |
| 5.B Tabla visible sin desplazar | ✅ | | Medido: primera fila en y = 622 px a 1440 × 900 |
| 5.B "¿Cómo se prioriza?" cerrado | ✅ | Matriz dentro de `ComoSeCalcula` | |
| 5.C Primer módulo sin desplazar | ✅ | `VistaCapacitacion.tsx`: una línea de resumen + filtros; tira de flujo y niveles en "¿Cómo se calcula?"; el avance de la empresa pasa debajo del plan; el tutor como botón | Medido: primer módulo en y = 801 px |
| 5.C Texto ≥ 14 px | ✅ | Metadatos de módulo, chips de brecha, leyendas a `--fs-sm` | |
| 5.D "¿Cómo se calcula?" compartido | ✅ | `components/ui/ComoSeCalcula.tsx` (`<details>/<summary>`) | |
| 5.D Actualización automática | ✅ | `hooks/useActualizacionAutomatica.ts` (`visibilitychange`/`focus`, mín. 30 s), `components/ui/Actualizado.tsx`, `usePanel.recargarSilencioso` (sin esqueleto al volver), `PageHeader.tsx` | No queda "Actualizar" por página |

### Fase 6 — Errores técnicos y siglas

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 6.1 Mensaje de bloqueo | ✅ | "No pudimos analizar este archivo. Revisa que no contenga instrucciones o texto inusual y súbelo de nuevo." | Captura `fase6_cerrar-brechas_1440_despues.png` |
| 6.2 Mapeo central | ✅ | Nuevo `lib/mensajesUsuario.ts` (`textoSeguro`, `mensajeEvidencia`, `mensajePorEstado`); usado en `lib/api.ts` (ya no "Error 502 al consultar /api/…"), `lib/remediacion.ts`, `lib/cuestionario/modelo.ts`, `VistaRemediacion.tsx` | `tests/mensajes_usuario.test.ts` |
| 6.3 Siglas | 🟡 | `components/ui/Sigla.tsx` + `lib/siglas.ts` (RoPA, RAT, PIA, ARCOP, DPO, NNA; nombre completo visible con foco y mouse, y para lector de pantalla). Aplicado en Registro de actividades, Informe RoPA y bandeja ARCOP; el pie público dice "Mis derechos sobre tus datos" | Quedan apariciones de siglas en textos largos de pantallas no tocadas (mapa, borradores): aplicar `<Sigla>` al pasar por ellas |
| 6.4 "F1 macro" | ✅ | `BandejaRevision.tsx`: "nivel de acuerdo con la revisión humana" + desplegable que lo explica | |
| 6.5 Nombre de empresa en ARCOP | 🟡 | `lib/arcop.ts`: usa `empresa_razon_social` si llega; si no, "Usuario de una empresa cliente" (sin IDs) | **Dependencia del backend** (§3) |
| 6.6 Horas con zona | ✅ | `lib/fechas.ts` (`horaConZonas`): "mañana 00:00 (Chile) · 03:00 UTC"; `PanelRetencion.tsx` | |

### Fase 7 — Navegación móvil inferior

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| Barra inferior 4 destinos + "Más" | ✅ | `components/shell/Sidebar.tsx` (`NavInferior`), `lib/navegacion.ts`, CSS "Fases 7 y 8.A" | 390 px: Diagnóstico · Plan · Privacidad · Documentos · Más |
| Cerrar sesión en menú de cuenta | ✅ | Barra superior compacta: marca + cuenta | |
| Área segura, 44 px, `aria-current`, teclado | ✅ | `env(safe-area-inset-bottom)`, hoja con Esc y foco | |
| Contenido no tapado | ✅ | `padding-bottom` del `.main` | |

### Fase 8 — Menú por tareas, flujo único y "Mi empresa" (⚠ validar con 3–5 usuarios)

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 8.A Menú por tareas | ✅ | `lib/navegacion.ts` (Diagnóstico · Plan de acción · Privacidad y registro · Documentos + "Mi empresa"); Borradores → Documentos; mismas URL | A 1440 × 900 el menú cabe completo (13 entradas, una línea cada una) |
| 8.B Entrada única al registro | ✅ | Nueva ruta `/empresa/registro` (`EntradaRegistro.tsx`) que lleva al paso pendiente; `PasosRegistro.tsx` (indicador común + "Siguiente paso") en mapa, asistente y registro; `lib/flujoRegistro.ts` | |
| 8.C "Mi empresa" como tablero | ✅ | `TableroEmpresa.tsx` + `lib/tableroEmpresa.ts` (vencimiento del contrato, revisión interna vencida o por vencer, propuestas por revisar, brechas críticas, estado real del registro); ficha con RUT y contrato en **`/empresa/configuracion`** (enlace en el menú de cuenta) | Ver §3 para lo que faltaría del backend |

### Fase 9 — Pulir componentes

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 9.1 Campo de archivo propio | ✅ | `components/ui/CampoArchivo.tsx` (español, nombre con corte elegante, quitar, arrastrar y soltar, error) en Cerrar brechas y en el cuestionario | 390 px sin texto cortado |
| 9.2 Hover vs. elegida | ✅ | `cuestionario.module.css`: hover = solo fondo; elegida = relleno de color + check; la descripción solo de la opción elegida | `fase9_cuestionario-opcion-elegida_1440_*.png` |
| 9.3 "Requiere revisión" aparte | ✅ | Botón "No estoy seguro, que lo revise la IA". **Mismo valor enviado** (`estado_clasificacion = "requiere_revision"`) por la misma llamada `c.guardar` | |
| 9.4 Navegación | ✅ | Sin "Anterior" en la pregunta 1 (preguntas iniciales y controles); "Seguir" con motivo | |
| 9.5 Barra de pasos | ✅ | `PasoFiltro.tsx`: la barra y el resumen cuentan las mismas preguntas que aplican (si F1 = No, solo queda F1) | |
| 9.6 Números de atajo | ✅ | `components/ui/DeteccionTeclado.tsx` (`html[data-teclado]`): los números solo se ven navegando con teclado; la línea "Atajos" queda | |
| 9.7 "Tus respuestas" | ✅ | Aparece desde la primera respuesta y lista todas las preguntas (pendientes incluidas) | |
| 9.8 Estilos en línea | 🟡 | Utilidades por tokens en `globals.css`; módulos `components/ui/comunes.module.css` y `components/empresa/empresa.module.css`. **Las páginas de empresa ya no importan `admin.module.css`** (admin compone lo común con `composes`) | Ver §4 |

### Fase 10 — Admin

| Punto | Estado | Archivos | Cómo verificar |
|---|---|---|---|
| 10.1 Métrica de la IA con mínimo | ✅ | `MIN_REVISIONES_METRICA = 10` en `lib/admin/revision.ts`; antes del mínimo: "Aún no hay suficientes revisiones para medir el acuerdo (1 de 10)." | `fase10_admin-revision_1440_despues.png` |
| 10.2 Filtros en una fila | ✅ | Estado + Motivo + Orden + "Más filtros (n)"; chips de filtros activos que se quitan; nota explícita de que los conteos por motivo **no** aplican los demás filtros | |
| 10.3 Nombre coherente | ✅ | Título de página "Empresas cliente" = menú | |
| 10.4 Alta solo al elegir | 🟡 | El formulario aparece cuando hay solicitudes marcadas (no hay un panel de detalle en esa pantalla); la columna "Acciones" tiene acciones reales y muestra "Sin acciones" cuando no hay | |
| 10.5 KPI en cero | ✅ | ARCOP y Privacidad: línea de estado ("No hay solicitudes pendientes.") | |
| 10.6 Intros de una línea | ✅ | Retención y ARCOP con "Más información" | |

### Fase 11 — Identidad visual

⏳ **Pendiente de validación** (así lo pide la auditoría). Entregable previo listo: `propuesta_identidad_visual.md`, `propuesta_tema_claro.css` y 4 capturas en `propuesta_capturas/`. No se aplicó nada de la Fase 11 al producto (el eyebrow, el fondo con cuadrícula y la tipografía siguen igual).

---

## 2. Decisiones tomadas en los puntos ⚠ Validar

1. **Fase 8 (menú por tareas):** "Resultados" es la entrada del Diagnóstico (la página `/panel`); "Mis evaluaciones" va en Diagnóstico; el mapa, el asistente y el registro comparten **una** entrada ("Arma tu registro"), que se marca como actual en las tres pantallas. Rótulos cortos en la barra inferior ("Plan", "Privacidad") con el nombre completo en `aria-label`.
2. **Fase 8.B:** el paso pendiente se decide con `/registro-actividades/cumplimiento` (mapa sin elementos → paso 1; sin actividades → paso 2; si no, paso 3). El paso 2 abre el asistente con `?asistente=1` (navegación completa, porque el asistente lee el parámetro al cargar).
3. **Fase 9.3:** se mantiene el valor `requiere_revision` y su regla de evidencia obligatoria; solo cambió la presentación.
4. **Niveles de madurez:** "Gestionado" pasó de verde a azul (`--nivel-gestionado`) y solo "Optimizado" usa el verde, para respetar "verde solo marca y Cumplido".
5. **Fase 10.4:** sin panel de detalle en Empresas cliente, el formulario se muestra al marcar al menos una solicitud.
6. **T-11 (backend):** el plazo del contacto del RoPA es **por condición** y por eso va en un mapa aparte (`CONDICION_POR_CONSERVACION`), no en `AJUSTE_POR_CONSERVACION` (cuyos valores deben ser ajustes numéricos de `Settings`, lo exige la prueba de HU-41). Los otros dos plazos sí quedan en `AJUSTE_POR_CONSERVACION`.
7. **T-11:** las dos variables nuevas tienen valor por defecto en `Settings` (180 y 730), tal como pide la tarea; las demás reglas de retención siguen vacías por defecto. "Configuración por defecto" = la documentada en `.env.example` y en `_conf()` de la prueba de HU-41.
8. **T-14:** "protegido" significa: en la respuesta de la entrevista, **bloqueado** sin llamar al LLM; en documento y mapa, la línea **neutralizada** y el texto del ataque ausente de lo que ve el LLM.

---

## 3. Dependencias del backend detectadas

| Pantalla | Qué falta | Respaldo actual |
|---|---|---|
| Admin · ARCOP | Campo `empresa_razon_social` en cada solicitud (`/api/arcop/solicitudes` admin) | "Usuario de una empresa cliente" |
| Mi empresa (tablero) | Un endpoint que agrupe los próximos pasos (hoy son 3 llamadas: cumplimiento, registro y panel de la evaluación más reciente) | Se arma en el navegador con `Promise.allSettled` (si una fuente falla, se muestra el resto) |
| Mi empresa (tablero) | Vencimientos de solicitudes ARCOP propias y de borradores en revisión | No se muestran |
| Navegación | Nombre del usuario y empresa para el menú de cuenta en el panel | Texto genérico "Mi cuenta" |

---

## 4. Estilos en línea

| | Cantidad (`style={{`) |
|---|---|
| Antes (HEAD) | **289** |
| Después | **229** (−60) |

En las pantallas tocadas quedan solo valores que dependen de datos (ancho de una barra, posición de la meta, coordenadas del tooltip). Los que siguen están sobre todo en pantallas fuera del alcance de esta auditoría: `MapaDatos.tsx` (19), `rat/Pasos.tsx` (16), `PanelPrivacidadPlataforma.tsx` (15), `mapa/Secciones.tsx` (13), `rat/DetalleActividad.tsx` (11).

---

## 5. Resultados de pruebas

| Suite | Resultado |
|---|---|
| Frontend · `npm run typecheck` | ✅ sin errores |
| Frontend · vitest | ✅ **31 archivos, 333 pruebas** (antes: 29 / 315; nuevas: `auditoria_ux.test.ts`, `mensajes_usuario.test.ts`; una aserción de `verificacion_ia.test.ts` se ajustó al texto acordado del bloqueo) |
| Frontend · `next build` | ✅ |
| Frontend · prueba móvil 390 × 844 (Playwright) | ✅ **24/24** en desarrollo y en producción (`next start`); falla correctamente si se reintroduce un desborde |
| Backend · pytest completo | ✅ **1537 aprobadas, 5 omitidas, 0 fallas** (en la imagen del backend, Python 3.13) |
| Backend · import-linter | ✅ 3 contratos respetados, 0 rotos |
| Backend · T-14 (protección del asistente) | ✅ 100 % en inyección (24/24), fuga del prompt (24/24), jailbreak (24/24), cambio de rol (24/24) y ofuscados (24/24); **0/45 falsos positivos** |

Nota de entorno: con Node 20 local, `vitest` no arranca (`ERR_REQUIRE_ESM` al cargar `vitest.config.ts`); en CI se usa Node 22 y funciona. Las pruebas se corrieron con una copia temporal del config en `.mts` (no incluida).

**La prueba móvil aún no está en el CI:** `.github/workflows/ci.yml` queda fuera de `Proyecto/`. Para agregarla, en el job `frontend`:

```yaml
      - name: Prueba visual móvil (Playwright, 390 × 844)
        run: |
          npx playwright install --with-deps chromium
          npm run test:e2e
```

T-14 corre en el CI sin cambios: está en `tests/ia/` y el job del backend ejecuta `pytest tests`.

---

## 6. Backend · T-11 a T-14

### T-11 · Completar los plazos del registro de la plataforma ✅

- `config.py`: `RETENCION_SOLICITUDES_DESCARTADAS_DIAS = 180` y `RETENCION_ARCOP_SEGUIMIENTO_DIAS = 730` (validados ≥ 1 o vacío); documentados en `.env.example`.
- Retención: **R5** borra las solicitudes de contratación descartadas hace más del plazo (un registro por solicitud en el audit log, acción `retencion.contratacion_descartada_eliminada`); **R6** retira el código de seguimiento ARCOP (lo reemplaza por uno aleatorio `RET-…`, que nadie conoce) y quita el actor del historial, después del plazo desde el cierre (`retencion.arcop_seguimiento_retirado`). Las dos cuentan en el registro de cada ejecución.
- Inventario: `C_CONTRATACION`, `C_CONTRATACION_PRUEBA` y `C_ARCOP_SEGUIMIENTO` nombran su ajuste y quedan en `AJUSTE_POR_CONSERVACION`; el contacto del RoPA tiene plazo por condición ("mientras ejerza el cargo"). El dominio del RAT acepta un plazo por condición (`catalogo.plazo_definido`), que solo usa el registro de la plataforma: la API del cliente no lo acepta (su normalizador no lo deja pasar).
- "Solicitudes de contratación descartadas" deja de ser un plazo pendiente del PO en la revisión interna.
- **Criterio:** con la configuración por defecto el registro sale **oficial**; una solicitud descartada hace 181 días se borra en la corrida y queda en el audit log; la prueba de HU-41 que compara plazos y ajustes sigue pasando (se le agregaron los dos ajustes nuevos a su configuración de prueba). Pruebas: `tests/integracion/test_t11_plazos_registro.py` (9).

### T-12 · Aceptar una propuesta del asistente sin dejarla colgada ✅

- `decisiones.py::aceptar`: crea el elemento, flujo o actividad y cierra la propuesta en **un solo commit**; la propuesta se bloquea (`FOR UPDATE`).
- `MapaDatosCasos` y `RegistroActividadesCasos` aceptan `confirmar=False` (hacen `flush` y dejan el commit a quien llama).
- Aceptar dos veces devuelve lo ya aceptado (sin duplicar ni `NOMBRE_DUPLICADO`); si en un reintento ya existe el objeto con `propuesta_ia_id`, la propuesta se marca aceptada sin crear otra vez (detalle `reintento: true` en el audit log).
- Pruebas: `tests/ia/test_t12_aceptar_propuesta.py` (4): falla en el segundo paso → nada creado y la propuesta sigue "por revisar"; doble aceptación; reintento; una sola versión del mapa y un solo registro en el audit log.

### T-13 · No sobrescribir una respuesta cambiada durante la validación ✅

- `flujo_validacion_evidencia.py`: guarda estado y justificación antes del LLM; después relee la respuesta con bloqueo (`RespuestaRepository.releer_bloqueada`, `FOR UPDATE` + `populate_existing`). Si cambió, no aplica la clasificación: la evidencia queda rechazada con "Tu respuesta cambió mientras revisábamos el documento; vuelve a subirlo." y el descarte queda en el audit log (`evidencia.clasificacion_descartada`, inyectado por el worker).
- Con repositorios que no tienen `releer_bloqueada` (dobles de prueba) el comportamiento es el de siempre.
- Pruebas: `tests/integracion/test_t13_respuesta_cambiada.py` (3), incluida la de cambiar a "Cumplido" durante la validación; HU-07 y HU-17 (con remediación) siguen pasando.

### T-14 · Medir la protección del asistente ✅

- `tests/data/ataques_asistente.jsonl`: **120 ataques** (inyección, fuga del prompt, jailbreak, cambio de rol, ofuscados: base64, hex, letras separadas, leetspeak, invisibles, homoglifos, puntos intercalados) repartidos en respuesta, documento y mapa, y **45 legítimas** (RR. HH., TI y marketing, con palabras trampa como "aprueba", "reglas", "ignora el spam", "administrador").
- `tests/ia/test_asistente_ataques.py` con umbrales (100 % / ≥ 95 % / ≤ 5 % de falsos positivos).
- **La primera medición dio 108/120** (fallaban 12, sobre todo en documentos). Se reforzó el filtro sin tocar `seguridad.py` (que se copia de otro repositorio): `filtro_agente.py` (`evaluar_documento`: reglas propias del agente de alta certeza para documentos, sin el respaldo estricto que confundiría vocabulario formal; reglas nuevas de asistente que nunca se niega, rol privilegiado, "repite lo que te escribieron antes"; "tu nuevo rol es…", "deja de lado la guía"; homoglifos extra y puntos intercalados) y `grafo.py` (usa `evaluar_documento` además del detector con contexto). Resultado: 120/120 y 0/45 falsos positivos; el resto de la suite (incluidos los umbrales del tutor y HU-33) sigue en verde.

---

## 7. Riesgos y qué revisar a mano

1. **Validar con usuarios** la Fase 8 (menú por tareas y flujo único) y la Fase 11 antes de seguir.
2. **Actualización automática:** al volver a la pestaña se recargan los datos sin esqueleto. En el admin, la Matriz normativa **no** se recarga sola (para no pisar un borrador en edición), como antes.
3. **Tablas en tarjetas < 600 px:** se aplicó a la tabla de brechas; otras tablas siguen con scroll horizontal **contenido** (no desbordan la página). Revisar si conviene pasarlas a tarjetas.
4. **Retención R5 y R6 activas por defecto:** al desplegar, la primera corrida diaria borrará las solicitudes descartadas hace más de 180 días y retirará los códigos de seguimiento de solicitudes ARCOP cerradas hace más de 730 días. Si se quiere otro comportamiento, fijar las variables (vacío = regla desactivada).
5. **Filtro del asistente más estricto en documentos:** 0 falsos positivos en el set; vigilar en la bandeja de seguridad si aparecen documentos legítimos neutralizados.
6. **Rutas nuevas:** `/empresa/registro` y `/empresa/configuracion` (las existentes no cambian).
7. Revisar a mano con lector de pantalla: menú de cuenta, hoja "Más" de la barra inferior, siglas y el campo de archivo.

---

## 8. Evidencias

`Extras/Evidencias/antes_despues/<fase>_<pantalla>_<1440|390>_<antes|despues>.png` — **45 capturas** (22 pares + "navegación Más" solo después, porque antes no existía).

- "Antes" = el código de HEAD (a819b79) en un `git worktree`; "después" = el árbol de trabajo. Ambos con las **mismas respuestas simuladas** de `tests/e2e/simulacion.ts`: la carpeta `frontend-next/docs/capturas/auditoria_ux/` que citaba el encargo **no existe en el repositorio**, y no se crearon usuarios en la base local, así que no se usaron datos reales.
- Capturas de la propuesta de identidad: `Extras/Cambios/propuesta_capturas/`.
