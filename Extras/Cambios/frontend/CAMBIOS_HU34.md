# HU-34 · Mapa de datos personales (frontend)

Nueva página **`/empresa/mapa-datos`** en el espacio de la empresa, con acceso desde la barra lateral (grupo «Privacidad», antes de «Mis derechos») y una tarjeta en «Mi empresa». Es parte del servicio contratado: sin contrato vigente la página lo explica y ofrece «Mis documentos» si sigue el plazo de gracia. En la interfaz no aparecen códigos internos ni de historias.

## Archivos

| Archivo | Qué hace |
|---|---|
| `app/empresa/(espacio)/mapa-datos/page.tsx` | Ruta (protegida por `middleware.ts` como todo `/empresa/*`) |
| `components/empresa/mapa/MapaDatos.tsx` | Página: carga, indicadores, pestañas, filtros, exportación, diálogos y avisos |
| `components/empresa/mapa/GrafoMapa.tsx` | Mapa navegable en SVG |
| `components/empresa/mapa/PanelDetalle.tsx` | Ficha del elemento o flujo elegido |
| `components/empresa/mapa/FormElemento.tsx` · `FormFlujo.tsx` | Formularios de alta y edición |
| `components/empresa/mapa/Dialogos.tsx` | Diálogo base, confirmaciones, envío por correo y selector de categorías |
| `components/empresa/mapa/Inventario.tsx` | Vista de tabla (alternativa accesible al diagrama) |
| `components/empresa/mapa/Secciones.tsx` | Riesgos, Sugerencias y plantillas, Historial e inicio con el mapa vacío |
| `components/empresa/mapa/mapa.module.css` | Estilos (solo tokens de `globals.css`) |
| `lib/mapaDatos.ts` | Tipos, llamadas al BFF y lógica pura (disposición, filtros, SVG/PNG, CSV) |
| `tests/mapa_datos.test.ts` | Pruebas de la lógica pura y de la lista blanca del proxy |

Cambios en archivos existentes: `Sidebar.tsx` (entrada «Mapa de datos»), `EspacioEmpresa.tsx` (tarjeta), `Icon.tsx` (íconos `mapa`, `baseDatos`, `sistemaApp`, `globo`, `filtro`, `imagen`, `lupaMas`, `lupaMenos`, `ajustar`, `editar`, `flujo`), `lib/servidor/proxyCliente.ts` (rutas `mapa-datos/*`, el PDF como binario) y `lib/servidor/proxy.ts` (parámetros `version`, `pagina` y los filtros del informe).

## Experiencia

- **Inicio** (mapa vacío): tres caminos — usar la plantilla recomendada para el rubro, partir de las sugerencias de la evaluación o agregar el primer elemento — con una ilustración del mapa y los pasos.
- **Indicadores**: sistemas, bases, terceros, flujos, transferencias internacionales (y cuántas sin garantía), elementos con datos sensibles y con NNA, riesgos críticos o altos, y la barra de completitud con la versión y la fecha.
- **Mapa**: disposición por capas en el sentido de los datos (mismo algoritmo que el PDF del servidor, con puntos de paso para que las flechas no pasen detrás de los nodos). Colores con significado y además forma: sistemas verdes, bases lavanda, terceros naranjas; flujos rosados con datos sensibles y **ámbar punteados** si son transferencias internacionales; borde punteado = por confirmar; insignias «SENSIBLE» y «NNA»; país en cada nodo (ámbar si está fuera de Chile).
- **Navegación**: arrastrar para moverse (mouse o un dedo), pellizcar o Ctrl + rueda para acercar (la rueda sola sigue desplazando la página), botones acercar/alejar/ajustar e indicador de zoom. Con teclado: flechas, `+`, `−`, `0`, Tab por elementos y flujos, Enter para elegir y Esc para soltar.
- **Filtros** (criterio 3): datos sensibles, NNA, transferencias internacionales, tercero, país y tipo. Lo que no cumple queda atenuado (se conserva el contexto) y al elegir un elemento se resaltan sus flujos. Los mismos filtros aplican al inventario y a las exportaciones.
- **Ficha**: datos del elemento o flujo, a dónde envía y de dónde recibe (navegables), riesgos que lo afectan y acciones (editar, agregar flujo desde aquí, confirmar, eliminar).
- **Formularios**: tipo con tarjetas, país con «Aún no lo sé», responsable como cargo o área, rol y contrato para terceros, selector de categorías agrupado con búsqueda y marcas «SENSIBLE», «NNA» y «¿NNA?»; la casilla de NNA se marca sola si se elige ese titular. En los flujos se avisa al instante si es una **transferencia internacional** (con su garantía), si el destino no tiene país o no tiene contrato, y si viajan datos sensibles sin cifrar; botón «Copiar las categorías del origen». Los errores del servidor se muestran en su campo.
- **Riesgos**: hallazgos con severidad, qué hacer, referencia y «Ver en el mapa»; tabla de lo que falta completar con «Completar» y «Confirmar todo lo revisado».
- **Sugerencias y plantillas**: tarjetas con el motivo («En tu evaluación indicaste que…»), qué se agregará y la opción de elegir el sistema de origen; descartar y volver a mostrar; plantillas con lo que incluyen y la recomendada destacada.
- **Historial**: versiones con su acción, fecha y tamaño; al elegir una, sus cambios, la huella con la verificación de integridad y «Volver a esta versión» (crea una nueva).
- **Exportar**: informe PDF (servidor), imagen PNG en alta resolución (SVG para papel convertido en el navegador, con título, leyenda y pie), inventario CSV (BOM, «;» y protección contra fórmulas) y envío por correo (a mi correo o a otro).

## Robustez y seguridad

- Todo cambio manda la versión del mapa; si el servidor responde que cambió, se recarga la última versión y se avisa sin perder el contexto.
- Lo que escribe la empresa se pinta como texto con React; el SVG del PNG se arma escapando cada texto.
- Antes de enviar se avisan los correos, RUT o teléfonos en los textos (el backend igual los rechaza).
- Responsivo: el detalle pasa bajo el mapa bajo 1100 px, formularios a una columna bajo 700 px, pestañas desplazables, tablas con desplazamiento horizontal y lienzo con alto adaptable; `prefers-reduced-motion` respetado.
- Accesible: pestañas con `tablist` y flechas, diálogos nativos (`<dialog>`, foco atrapado y Esc), nodos y flujos con `role="button"` y etiquetas descriptivas, contraste AA y el inventario como alternativa en tabla al diagrama.
