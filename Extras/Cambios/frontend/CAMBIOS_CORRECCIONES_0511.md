# Correcciones de interfaz del 05-11-2026 (frontend-next + ajustes de backend)

Este paquete reúne las mejoras pedidas por el equipo después de recorrer la plataforma vista por vista. Casi todo es frontend; cuatro puntos necesitaban también al backend (tutor IA, cuestionario, rubros y la verificación de Turnstile), y se dejaron con sus pruebas.

## Espacio de la empresa

**Borradores pasa a "Gobernanza de IA".** En la barra lateral del cliente, Borradores deja el grupo "Mi empresa" y queda junto a Cerrar brechas, que es donde se usa: son documentos que nacen de las brechas. La URL sigue siendo `/empresa/borradores`, así que no se rompe ningún enlace guardado ni el acceso directo de "Mi empresa".

**Mis evaluaciones** solo muestra el gráfico de evolución cuando hay al menos dos evaluaciones completadas. Con una sola no hay evolución que mirar y el gráfico era un punto suelto.

## Panel de resultados

**Diagnóstico** ya no repite la comparativa meta/rubro, que vive en Dominios. Las brechas prioritarias quedan a todo el ancho.

**Dominios**: el gráfico de barras ocupa todo el ancho de la tarjeta. El problema era que el SVG tenía un viewBox de 600 de ancho y un alto máximo de 420 px, así que en una tarjeta ancha quedaba centrado con márgenes vacíos. Ahora `BarrasDominio` acepta `ancho` (viewBox de 1100 y sin alto máximo); en las tarjetas de media columna sigue igual.

**Sector**: el subtítulo dice ahora que los promedios aparecen solo cuando hay suficientes empresas, así ningún resultado individual queda expuesto. Se quitó la sobreexplicación: antes el mismo mensaje aparecía en el aviso, en la frase del resumen, en un sello "Grupo de menos de 5 empresas", en un sello "Oculto" dentro de cada tira, en la leyenda y en cada cifra. Queda un solo aviso breve arriba ("Aún no hay suficientes empresas de tu sector") y las cifras sin dato muestran "—". La explicación de fondo sigue disponible, plegada, en "Cómo protegemos a las empresas de tu sector".

**Tutor IA**: conversa más simple y nunca nombra códigos internos. Es un arreglo desde la raíz, como se había decidido:

- El prompt sube a `tutor/1.3.0` con una sección "Lenguaje con el usuario": frases cortas, tuteo, respuestas de 2 a 4 frases por defecto, brechas nombradas por lo que significan y estados escritos como texto ("no cumplido", no `no_cumplido`). Los códigos solo van en `brechas_referenciadas`, que el sistema usa para enlazar.
- Por si el modelo igual escribe un código, el agente lo reemplaza antes de mostrar o guardar la respuesta (`agente/salida.py: humanizar_codigos`, aplicado en `nodo_anclar_contexto`): un código conocido pasa a ser el nombre de su brecha entre comillas, uno desconocido pasa a "esta brecha", y los estados del sistema pasan a texto. No toca "Ley 21.719", "ISO/IEC 42001" ni "NIST AI RMF 100-1".
- En el chat, las brechas citadas se muestran por su descripción en vez del código, y las preguntas sugeridas al abrir el tutor ya no incluyen códigos ("Explícame mi brecha más urgente en Protección de Datos").

En una segunda ronda el prompt pasó a `tutor/1.4.0` con una sección "Charla simple": un saludo, un "¿cómo estás?", un gracias o una despedida se responden como una persona, en 1 o 2 frases, sin resumir la evaluación ni proponer planes. Antes, un "hola" devolvía el estado completo de la empresa. Luego (`tutor/1.4.1`) se corrigió que un "adiós" apareciera como "[NOMBRE_ANON], recuerda...": el NER que revisa la respuesta del modelo marcaba la palabra de despedida como nombre. El prompt pide no llamar al usuario por su nombre y `sin_vocativos_anonimizados` (agente/salida.py) quita esas etiquetas cuando se usan como vocativo; las que son parte del contenido se conservan. En el chat, el encabezado ya no muestra el número interno de la evaluación ni "tus 0 brechas", el nivel sugerido se marca con un punto (el texto "· sugerido" se cortaba) y los saludos o despedidas no llevan la etiqueta "Recomendación".

**Cerrar brechas → "Tu madurez ahora"** dejó de ser solo un número. Muestra el puntaje con su nivel, una frase con desde dónde partiste y en qué dimensiones subiste más, y una lista **por dimensión** con su barra frente a la meta, cuántos puntos aportó al total, cuántas preguntas mejoraron con evidencia y cuántas brechas siguen abiertas. Debajo van las **últimas mejoras**: la pregunta, su dimensión, el cambio de estado (por ejemplo "No cumplido → Cumplido"), la fecha y los puntos. Para esto el backend agrega a cada mejora de `GET /api/remediacion/evaluaciones/{id}` su `dominio`, `pregunta`, `estado_previo` y `estado_resultante` (campos nuevos y opcionales: el frontend anterior los ignora).

## Portada

Se quitó la vista previa con el resultado de ejemplo. El héroe queda solo con el texto y, detrás, las líneas tipo ola, que ahora se mueven como oleaje: cada línea avanza en bucle a su propia velocidad (las de atrás más lento) y sube y baja suavemente. Todo es CSS sobre el mismo SVG generado al compilar, sin JavaScript en el navegador. Para que el bucle no tenga salto, cada línea se calcula con un número entero de ciclos y se dibuja dos veces seguidas. Si el sistema tiene "reducir movimiento" activado (en Windows, con los efectos de animación desactivados, que es lo que pasaba en los equipos del equipo y por eso se veían quietas) las olas siguen moviéndose, pero solo con un desplazamiento horizontal muy lento y sin el vaivén vertical. Para dejarlas quietas en ese caso basta borrar el bloque `prefers-reduced-motion: reduce` de `heroe.module.css`.

## Comenzar evaluación: la verificación ya no exige F5

A algunas personas el desafío de Turnstile les fallaba ("no reconoce que es una persona") y solo salían recargando la página. Había dos causas posibles y se atacaron las dos:

1. **En el navegador**, cuando el widget avisaba un error nadie lo reiniciaba. Ahora se recupera solo: ante un error o un tiempo agotado se reinicia hasta 3 veces con espera creciente, y usa además los reintentos propios de Cloudflare. Si sigue fallando, o si en 25 segundos no llega el token, aparece "Reintentar verificación", que vuelve a crear el widget desde cero sin recargar la página. El formulario de contratación usa el mismo componente y gana lo mismo.
2. **En el servidor**, un corte de red puntual con Cloudflare daba la verificación por fallida. Ahora se reintenta una vez con la misma `idempotency_key`, que Cloudflare no cuenta como reutilización del token.

### Segunda corrección (misma fecha, tras la prueba del equipo)

Seguía siendo necesario el F5 y se encontró la causa real: la política de seguridad de contenido (CSP) es del **documento**, no de cada página. La portada y el panel usan la política base, que no permitía el script ni el frame de Cloudflare. Al pulsar "Comenzar autodiagnóstico" Next navegaba del lado del cliente, sin recargar, así que en `/comenzar` seguía rigiendo la política de la portada y el navegador bloqueaba Turnstile. Al recargar, `/comenzar` llegaba con su propia política y funcionaba. Ahora la política base también admite `challenges.cloudflare.com` (`middleware.ts`), el botón de la portada hace una carga completa de `/comenzar` y, si el script de Cloudflare no llegó a cargar, "Reintentar verificación" recarga la página por su cuenta. Lo mismo arregla `/panel/contratar` al llegar desde el panel.

## Encuesta

**Preguntas iniciales (filtro)**: al marcar Sí o No la respuesta queda marcada y no se salta sola a la siguiente; se avanza con **Seguir** (o Enter). Así se puede corregir antes de continuar.

**Correo**: se quitó el bloque de correo opcional del pie de `/encuesta`, porque ya se pide al comenzar (paso "Tu clave").

**Preguntas del cuestionario**:

- **"Cumplido" exige evidencia.** "Guardar y continuar" no avanza sin un documento y lo explica junto al campo. Para completar la evaluación, el backend también lo exige (`409 CUMPLIDO_SIN_EVIDENCIA`), igual que ya hacía con "Requiere revisión", y la revisión final lo marca como "Cumplido sin evidencia".
- **Todas las justificaciones son opcionales.** El backend dejó de exigirla en "Parcialmente cumplido" y "Requiere revisión".

Las dos reglas son configurables en el `.env` del backend: `JUSTIFICACION_OBLIGATORIA` (por defecto `false`; con `true` vuelve la regla original de la HU-02) y `EVIDENCIA_OBLIGATORIA_CUMPLIDO` (por defecto `true`). Si usan el script de datos de prueba del panel y este completa evaluaciones con preguntas "cumplido" sin evidencia, pongan `EVIDENCIA_OBLIGATORIA_CUMPLIDO=false` mientras prueban.

## Panel interno (admin)

**Barra común con "Actualizar".** Las tres secciones (Empresas cliente, Matriz normativa, Bandeja de revisión) comparten ahora una barra (`components/admin/BarraAdmin.tsx`) en vez de tres copias. El botón **Actualizar** vuelve a pedir los datos de la sección abierta sin recargar la página: no se pierde la pestaña, el filtro ni lo que se está escribiendo, y al lado queda la hora de la última actualización. En Empresas cliente y en la Bandeja la sección también se actualiza sola al volver a la pestaña del navegador (como mínimo cada 30 segundos). La sección actual queda marcada en la barra.

**RUT con puntos y guion automáticos** al dar de alta una empresa: se escriben solo los números (y la K) y el campo se formatea mientras se escribe (`760864285` → `76.086.428-5`). El backend ya normalizaba el RUT, así que no cambió.

**Matriz normativa → Rubros**: pestaña nueva para agregar rubros y corregir su nombre, con cuántas evaluaciones y empresas usan cada uno. Los rubros no pasan por el borrador de la matriz porque no son parte de ella: el cambio rige de inmediato y queda en el audit log (`rubro.creado`, `rubro.renombrado`). No se eliminan, porque los ya usados sostienen evaluaciones y la comparación del sector. Endpoints nuevos (solo admin): `GET/POST /api/admin/rubros` y `PATCH /api/admin/rubros/{id}`. Como los rubros sembrados tienen id explícito y la secuencia de PostgreSQL no avanzó con ellos, el id del rubro nuevo se calcula en la aplicación. La lista pública que usa `/comenzar` se refresca cada 5 minutos (antes cada hora), así que un rubro nuevo aparece pronto.

**Se quitó el texto "Versión inicial: matriz sembrada por las migraciones (HU-24)"**, que el sistema guardó como nota de la primera versión. No se borra de la base (las versiones publicadas no se modifican); simplemente no se muestra.

**Hora de Chile.** El backend entrega las fechas en UTC sin zona y el navegador las tomaba como hora local, por eso el panel mostraba 3 horas de más (y la bitácora, la hora UTC en bruto). Ahora todas las fechas y horas del panel interno pasan por `lib/fechas.ts`, que las lee como UTC y las muestra en `America/Santiago`, con el horario de verano incluido. La bitácora muestra "Fecha (hora de Chile)" y las solicitudes y los eventos de revisión llevan la hora. "Hoy" en el formulario de alta también se calcula con el calendario de Chile (después de las 21:00 ya daba el día siguiente).

## Archivos

Frontend (`Proyecto/frontend-next`), modificados: `app/page.tsx`, `app/comenzar/page.tsx`, `components/shell/Sidebar.tsx`, `components/empresa/MisEvaluaciones.tsx`, `components/vistas/VistaDiagnostico.tsx`, `components/vistas/VistaDominios.tsx`, `components/vistas/VistaSector.tsx`, `components/charts/BarrasDominio.tsx`, `components/sector/TiraSector.tsx`, `components/formacion/TutorIA.tsx`, `components/formacion/tutor.module.css`, `components/remediacion/VistaRemediacion.tsx`, `components/publico/HeroePortada.tsx`, `components/publico/heroe.module.css`, `components/inicio/Turnstile.tsx`, `components/inicio/FlujoInicio.tsx`, `components/inicio/inicio.module.css`, `components/encuesta/InicioEncuesta.tsx`, `components/cuestionario/PasoFiltro.tsx`, `components/cuestionario/PasoControl.tsx`, `components/cuestionario/RevisionFinal.tsx`, `components/cuestionario/cuestionario.module.css`, `components/admin/PanelClientes.tsx`, `components/admin/BandejaRevision.tsx`, `components/admin/MantenedorMatriz.tsx`, `components/admin/admin.module.css`, `components/admin/matriz.module.css`, `app/globals.css`, `lib/sector.ts`, `lib/tutor.ts`, `lib/remediacion.ts`, `lib/types.ts`, `lib/cuestionario/modelo.ts`, `lib/encuesta/errores.ts`, `lib/admin/api.ts`, `lib/admin/matriz.ts`, `lib/admin/revision.ts`, `lib/servidor/proxyAdmin.ts`, `tests/cuestionario.test.ts`, `tests/hu15_tutor.test.ts`. Nuevos: `components/admin/BarraAdmin.tsx`, `components/admin/RubrosMatriz.tsx`, `lib/admin/rubros.ts`, `lib/fechas.ts`, `tests/correcciones_0511.test.ts`.

Backend (`Proyecto/backend`), modificados: `app/application/ai/prompts/tutor.py`, `app/application/ai/agente/salida.py`, `app/application/ai/agente/grafo.py`, `app/application/use_cases/remediacion.py`, `app/application/use_cases/create_respuesta.py`, `app/application/use_cases/completar_evaluacion.py`, `app/core/config.py`, `app/infrastructure/security/captcha.py`, `app/infrastructure/repositories/bitacora_repository.py`, `app/main.py`, `tests/conftest.py`, `tests/test_hu18_gobernanza_agente.py`, `tests/test_hu20_autorizacion.py`. Nuevos: `app/api/routes/admin_rubros.py`, `tests/test_admin_rubros.py`, `tests/test_correcciones_cuestionario.py`, `tests/test_tutor_lenguaje_cliente.py`.

No hay migraciones nuevas.

## Pruebas

Frontend: `tests/correcciones_0511.test.ts` cubre el RUT automático, las fechas en hora de Chile, la validación de rubros y su lista blanca en el BFF, la nota sembrada oculta, el avance por dimensión de "Tu madurez ahora" y el nombre de las brechas en el tutor. Se actualizaron las reglas de justificación y evidencia en `tests/cuestionario.test.ts` y las sugerencias sin códigos en `tests/hu15_tutor.test.ts`.

Backend: `test_tutor_lenguaje_cliente.py` (prompt 1.3.0 y reemplazo de códigos), `test_correcciones_cuestionario.py` (justificación opcional y "cumplido" con evidencia) y `test_admin_rubros.py` (agregar, listar, renombrar, duplicados, audit log y rutas solo admin). `conftest.py` fuerza la regla antigua de justificación y evidencia para las suites ya escritas (HU-02, HU-12, HU-29…), igual que se hace con `EXIGIR_TOKEN_EVALUACIONES`; las reglas nuevas se prueban activándolas con monkeypatch. `test_hu20_autorizacion.py` clasifica las rutas de rubros.
