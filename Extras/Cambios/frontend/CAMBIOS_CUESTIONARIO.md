# Cuestionario adaptativo conectado al backend (HU-01 / HU-02 en frontend-next)

`/encuesta` ya no es solo la portada de la evaluación: ahí vive el cuestionario completo, igual que en el prototipo `Proyecto/frontend/cuestionario.html`, pero hablando con FastAPI real a través del BFF. Al completar la evaluación, el encuestado pasa directo al panel de resultados (`/panel?evaluacion=ID`), que ahora sabe cargar su evaluación por el BFF.

No hay cambios en el backend ni dependencias nuevas.

## Flujo

```
/encuesta
  ├─ Preguntas iniciales F1–F7 (una por pantalla)     GET/POST /evaluaciones/{id}/filtro
  │     F1 = No  → ningún control aplica, se salta F2..F7 y se confirma
  │     F2..F7 = Sí suman controles (se muestra cuántos en vivo)
  ├─ Controles aplicables, uno por uno                GET /evaluaciones/{id}/controles-aplicables
  │     5 estados · justificación · evidencia         POST /respuestas (upsert) · POST /respuestas/{id}/evidencias
  │     índice por dominio con el estado de cada uno  GET /evaluaciones/{id}/progreso
  ├─ Revisión final (mismas reglas que /completar)    GET /respuestas/{id} · GET /evidencias/{id}
  └─ Completar                                        POST /evaluaciones/{id}/completar
        ↓
/panel?evaluacion=ID   (diagnóstico, dominios y brechas, leídos por /bff/api)
```

Se retoma siempre donde quedó: `GET /progreso` dice la etapa (`filtro`, `cuestionario`, `completo`, `cerrada`) y el siguiente control pendiente. Cada respuesta se guarda al avanzar, así que cerrar la pestaña no pierde nada.

## Comportamiento por pantalla

**Preguntas iniciales.** Cada pregunta muestra su descripción y cuántos controles aplican hasta ahora (y cuántos sumaría responder Sí). Al final hay un resumen con "Cambiar" en cada respuesta. Si el usuario ya había respondido controles y rehace el filtro, se le avisa que los que dejen de aplicar no contarán. El número definitivo de controles es el que devuelve el backend; el que se ve mientras se responde es un espejo de `control_tree.py` (`lib/cuestionario/modelo.ts`, con prueba que lo verifica).

**Control.** Código, criticidad, dominio, pregunta, "Qué se exige", "Evidencia esperada" y la base normativa desplegable. Los cinco estados de HU-02, con "Requiere revisión" explicado como "¿no estás seguro?". La justificación es obligatoria (≥ 20 caracteres con letras, igual que `validar_justificacion()`) en *Parcialmente cumplido* y *Requiere revisión*, con contador. La evidencia aparece solo en los estados que la admiten; en *Requiere revisión* se avisa que es necesaria para completar. Al volver a un control respondido se cargan su estado, la justificación (ya anonimizada) y sus evidencias con el resultado de la IA. Mientras una evidencia está en cola o validando se consulta sola con espera creciente.

**Revisión final.** Avance por dominio y la lista de lo que impide completar: controles sin responder, evidencias aún en validación y *Requiere revisión* sin evidencia, cada uno con "Ir al control". Exige marcar que entiende que la evaluación se cierra. Si igual el backend rechaza (`CUESTIONARIO_INCOMPLETO`, `EVIDENCIAS_EN_PROCESO`, `REVISION_SIN_EVIDENCIA`), se muestra su mensaje, que dice qué controles faltan.

**Panel del encuestado.** `usePanel` pregunta a `/bff/encuesta/sesion` si hay sesión de encuestado. Si la hay (y la URL no pide otra evaluación), el panel entra en modo `encuestado`: muestra solo su evaluación y lee todo por `/bff/api/*`, que agrega el token desde la cookie httpOnly. Sin sesión, sigue igual que antes (`/api/*`, equipo interno). En modo encuestado el menú lateral suma "Mi evaluación" y, si la evaluación aún no tiene resultados, ofrece "Continuar mi cuestionario".

## Archivos

| Archivo | Qué hace |
|---|---|
| `lib/cuestionario/modelo.ts` | Contratos de la API, árbol F1–F7 (vista previa), estados HU-02, validación de justificación y archivo, bloqueos para completar |
| `lib/cuestionario/api.ts` | Llamadas al BFF (filtro, controles, progreso, respuestas, evidencias, completar) |
| `hooks/useCuestionario.ts` | Estado del cuestionario: etapa, controles, progreso, navegación, guardar, completar |
| `components/cuestionario/Cuestionario.tsx` | Orquesta las etapas |
| `components/cuestionario/PasoFiltro.tsx` | Preguntas F1–F7 |
| `components/cuestionario/PasoControl.tsx` | Un control: estado, justificación, evidencia |
| `components/cuestionario/Evidencias.tsx` | Lista de evidencias y seguimiento de la validación con IA |
| `components/cuestionario/IndiceControles.tsx` | Índice por dominio (columna fija ≥ 1024 px; debajo de la pregunta en pantallas angostas) |
| `components/cuestionario/RevisionFinal.tsx` | Revisión, completar y paso al panel |
| `components/cuestionario/cuestionario.module.css` | Estilos con los tokens existentes |
| `components/encuesta/InicioEncuesta.tsx` | Monta el cuestionario (antes solo mostraba el progreso) |
| `app/encuesta/page.tsx` | Contenedor ancho para el índice + pregunta |
| `lib/api.ts`, `hooks/usePanel.tsx` | Panel con base `/api` o `/bff/api` según quién mira |
| `components/shell/Sidebar.tsx`, `components/ui/Basicos.tsx` | "Mi evaluación" y "Continuar mi cuestionario" para el encuestado |
| `lib/encuesta/errores.ts` | Mensajes para los códigos del cuestionario (justificación, prompt injection, control no aplicable, cierre, archivo…) |
| `tests/cuestionario.test.ts` | 14 pruebas: árbol, F1 = No, cuerpo del filtro, justificación, formatos, orden, bloqueos, rutas del BFF, mensajes |

## Verificación hecha

- Las 4 suites (`adaptadores`, `brechas_hu11`, `cuestionario`, `encuesta`) pasan: 53 pruebas.
- Los archivos nuevos y modificados pasan `tsc --strict` con los tipos reales de React 19.
- Recorrido completo en navegador (Chromium) contra un backend simulado con el catálogo real de la migración (40 controles, 7 preguntas): filtro con F3 y F4 en Sí → 30 controles; error de justificación corta; rechazo de PDF; evidencia `.txt` en *Requiere revisión* que la IA resuelve como parcial; navegación atrás conservando la respuesta; revisión; completar → panel con radar, comparativa y 16 brechas. Cero errores de consola y **ninguna llamada directa a `/api/*`** desde el encuestado.

**Falta correrlo en el Docker del equipo** (no pude instalar dependencias de npm en mi entorno): `npm test`, `npm run typecheck`, `npm run build` y el checklist de abajo.

## Checklist en Docker

`docker compose up -d --build`, luego crear una evaluación desde http://localhost:3000/comenzar.

- [ ] `/encuesta` muestra "Pregunta 1 de 7". Con F1 = No aparece "Tu organización no utiliza IA", Confirmar y Completar terminan sin ir al panel.
- [ ] En otra evaluación, F1 Sí + F3 Sí + F4 Sí → el resumen dice 30 y el cuestionario "0 de 30".
- [ ] *Parcialmente cumplido* con "muy corto" no guarda y muestra el error; con 20+ caracteres avanza.
- [ ] Un `.txt` en *Requiere revisión* pasa de "En cola" a "Validada" (worker + Groq) y el punto del índice cambia al color del estado que decidió la IA.
- [ ] Cerrar la pestaña, volver con `/retomar`: sigue en el siguiente control pendiente.
- [ ] Completar → `/panel?evaluacion=ID` con datos. En DevTools → Network solo hay llamadas a `/bff/...`.
- [ ] Volver a `/encuesta` → "Tu evaluación está completada" con "Ver mis resultados".
- [ ] `docker compose exec worker pytest tests -v -rxX` sigue en verde (el backend no cambió).

## Pendientes y decisiones a validar

1. **Evidencias en PDF.** El worker (`process_evidence.py`) lee el archivo como texto UTF-8, así que un PDF o un Word llegarían ilegibles al LLM. Por eso el cuestionario acepta solo `.txt`, `.md`, `.csv` y `.json`. Cuando el backend extraiga texto de PDF, basta con ampliar `EXTENSIONES_EVIDENCIA` en `lib/cuestionario/modelo.ts`. El prototipo pedía PDF obligatorio en *Cumplido* y *Parcial*; el backend actual no lo exige, así que aquí la evidencia es opcional salvo en *Requiere revisión* (regla de `/completar`).
2. **Etiqueta "Requiere revisión".** Se mantuvo el nombre que aprobó el PO, con la ayuda "¿No estás seguro? Adjunta una evidencia…".
3. **Mismo navegador para equipo y encuestado.** Si alguien del equipo abre `/panel` en un navegador con sesión de encuestado y sin `?evaluacion=`, verá el modo encuestado. Con `?evaluacion=<otra>` vuelve al modo interno. Se resuelve del todo cuando el panel interno tenga login.
