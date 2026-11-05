# HU-22 · Bandeja de revisión (frontend-next)

Nueva página del panel interno: **`/admin/revision`** ("Bandeja de revisión" en la barra de
navegación, junto a Empresas cliente y Matriz normativa). Solo con sesión de admin (middleware).

## Diseño

La pantalla responde la pregunta con que entra el oficial: *¿qué decidió la IA que tengo que validar?*

- **Verdad de referencia, en una frase.** Arriba: "La IA coincidió con tu revisión en 72 % de 25
  preguntas que evaluó", con la barra de confirmadas/corregidas y los veredictos de seguridad.
- **Dos paneles.** A la izquierda la lista priorizada (bloqueos de seguridad, divergencias,
  sin resolver, baja confianza, decididas por la IA); a la derecha el elemento abierto.
- **La cadena de decisión** es el elemento protagonista: *Declaró la organización → Propuso la IA
  → Vigente hoy*. Cada voz tiene un color fijo en toda la pantalla (organización gris azulado,
  IA lavanda, oficial menta; rojo solo para seguridad). Si la IA no coincide con lo declarado,
  el conector entre ambas se corta en lavanda (y en la lista aparece "≠"). La confianza de la IA
  se muestra como barra con una marca en el umbral.
- **Decidir sin perder el hilo.** El formulario está justo bajo la cadena: cuatro opciones de
  clasificación (preseleccionada la vigente) y comentario obligatorio con contador. El botón
  dice exactamente qué pasa ("Confirmar «No cumplido»" / "Corregir a «Parcialmente cumplido»").
  Al guardar, se abre solo el siguiente pendiente y se anuncia el resultado.
- Debajo, la justificación de la organización, la evidencia esperada, cada evidencia con el
  razonamiento de la IA, los eventos de seguridad y el **historial de revisiones leído del audit log**.
- **Eventos de seguridad** en su pestaña: el extracto (ya anonimizado) destacado en rojo, veredicto
  *Ataque confirmado / Falso positivo* con comentario y un enlace para revisar la clasificación
  de la pregunta afectada.

## Accesibilidad (WCAG 2.1 AA)

Pestañas con `role="tablist"`, filtros con `aria-pressed`, fila abierta con `aria-current`, foco
al título del detalle al abrirlo, radios nativos de 44 px de alto, textarea con etiqueta,
`aria-invalid` y ayuda asociada, avisos en `role="status"`, el "≠" y la barra de confianza con
texto equivalente para lectores de pantalla. Colores de los tokens ya validados (≥ 4,5:1).
Bajo 1100 px el detalle reemplaza a la lista (botón "Volver a la lista"); bajo 720 px la
cadena se apila en vertical y el conector cortado pasa a ser un borde punteado.

## Archivos

| Archivo | Cambio |
|---|---|
| `app/admin/revision/page.tsx` | **Nuevo.** Ruta `/admin/revision`. |
| `components/admin/BandejaRevision.tsx` | **Nuevo.** Página completa. |
| `components/admin/revision.module.css` | **Nuevo.** Estilos (tokens de `globals.css`). |
| `lib/admin/revision.ts` | **Nuevo.** Tipos, llamadas y lógica pura. |
| `lib/servidor/proxyAdmin.ts` | Lista blanca: rutas de la bandeja, las dos decisiones, `/dominios` y los filtros de la query. |
| `components/admin/PanelClientes.tsx`, `MantenedorMatriz.tsx` | Enlace "Bandeja de revisión" en la navegación. |
| `tests/hu22_revision.test.ts` | **Nuevo.** Decisión confirmar/corregir, comentario, cadena, siguiente pendiente, query y proxy. |

En esta pantalla interna sí se muestran los códigos de control (DAT-001): el cliente nunca la ve.
