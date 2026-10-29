# HU-18 · Gobernanza del Agente IA (frontend-next)

El cambio en el frontend es pequeño, porque casi todo lo de HU-18 pasa en el backend. Los mensajes bloqueados ya se mostraban como "Mensaje bloqueado" desde HU-15; ahora el texto que llega es distinto según lo que se intentó (por ejemplo, un pedido de falsificar evidencia recibe una explicación ética con la alternativa legítima), y el chat no tuvo que cambiar para eso.

Lo nuevo es la advertencia por abuso. Cuando una empresa acumula tres mensajes bloqueados en diez minutos, la respuesta del API trae un campo `advertencia`. El chat lo muestra sobre el cuadro de texto, en un aviso de tono medio (amarillo, para distinguirlo del rojo de los errores) con `role="alert"`, de modo que un lector de pantalla lo anuncia en cuanto aparece. El aviso no deshabilita nada: el usuario puede seguir escribiendo y el siguiente envío lo limpia. También se limpia al abrir una conversación nueva.

| Archivo | Cambio |
|---|---|
| `lib/types.ts` | `RespuestaTutorApi.advertencia?` |
| `hooks/useTutor.ts` | Estado `advertencia`: se toma de la respuesta y se limpia al enviar o al abrir una conversación nueva. |
| `components/formacion/TutorIA.tsx` | Aviso sobre el composer. |
| `components/formacion/tutor.module.css` | Estilo `.advertencia`. |

El chequeo de tipos pasa sin errores y las pruebas de `tests/hu15_tutor.test.ts` siguen en verde.
