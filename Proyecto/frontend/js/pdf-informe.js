// ============================================================================
// Generación del PDF del informe usando jsPDF (cargado desde CDN en
// informe.html). Misma estructura que la versión Next.js de la demo.
// ============================================================================
window.Therion = window.Therion || {};

Therion.pdf = (function () {
  "use strict";

  var MARGEN = 15;
  var ANCHO_UTIL = 180;

  function saltoSiNecesario(doc, y, alto) {
    var altoPagina = doc.internal.pageSize.getHeight();
    if (y + alto > altoPagina - MARGEN) {
      doc.addPage();
      return MARGEN;
    }
    return y;
  }

  function parrafo(doc, texto, y, opciones) {
    opciones = opciones || {};
    var tamano = opciones.tamano || 10;
    doc.setFont("helvetica", opciones.negrita ? "bold" : "normal");
    doc.setFontSize(tamano);
    var lineas = doc.splitTextToSize(texto, ANCHO_UTIL);
    y = saltoSiNecesario(doc, y, lineas.length * (tamano * 0.42) + 2);
    doc.text(lineas, MARGEN, y);
    return y + lineas.length * (tamano * 0.42) + 3;
  }

  function generarInformePdf(informe, nombreOrganizacion) {
    var jsPDF = window.jspdf.jsPDF;
    var doc = new jsPDF({ unit: "mm", format: "a4" });
    var y = MARGEN;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text("Informe de madurez en gobernanza de IA", MARGEN, y);
    y += 8;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    if (nombreOrganizacion) {
      doc.text(nombreOrganizacion, MARGEN, y);
      y += 6;
    }
    doc.text("Diagnóstico: " + informe.diagnostico_id, MARGEN, y);
    y += 5;
    doc.text("Generado: " + new Date().toLocaleString("es-CL"), MARGEN, y);
    y += 10;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.text("Puntaje general", MARGEN, y);
    y += 7;
    doc.setFontSize(20);
    doc.text(informe.puntaje_general !== null ? informe.puntaje_general + "%" : "Sin datos", MARGEN, y);
    y += 6;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.text("Nivel de riesgo: " + informe.riesgo_general, MARGEN, y);
    y += 5;
    doc.setFontSize(9);
    doc.text(informe.n_evaluados + " de " + informe.n_aplicables + " controles aplicables evaluados", MARGEN, y);
    y += 10;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.text("Puntaje por dimensión", MARGEN, y);
    y += 7;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    informe.por_dimension.forEach(function (d) {
      y = saltoSiNecesario(doc, y, 6);
      var puntaje = d.puntaje !== null ? d.puntaje + "%" : "—";
      doc.text(d.dimension + ": " + puntaje + " — " + d.clasificacion + " (" + d.n_evaluados + " evaluados)", MARGEN, y);
      y += 6;
    });
    y += 4;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    y = saltoSiNecesario(doc, y, 8);
    doc.text("Brechas priorizadas (" + informe.brechas.length + ")", MARGEN, y);
    y += 8;

    if (informe.brechas.length === 0) {
      y = parrafo(doc, "No hay brechas: todos los controles evaluados están cumplidos.", y);
    }

    informe.brechas.forEach(function (b, i) {
      y = saltoSiNecesario(doc, y, 12);
      doc.setDrawColor(200, 195, 175);
      doc.line(MARGEN, y - 3, MARGEN + ANCHO_UTIL, y - 3);

      y = parrafo(doc, (i + 1) + ". " + b.brecha_asociada, y, { negrita: true, tamano: 11 });
      y = parrafo(doc, "Nivel de criticidad: " + b.criticidad, y);
      y = parrafo(doc, "Fuente: " + b.fuente, y);
      y = parrafo(doc, "Dimensión: " + b.dominio, y);
      y = parrafo(doc, "Evidencia entregada: " + (b.evidencia_entregada || "No se entregó evidencia."), y);
      y = parrafo(doc, "Evidencia esperada: " + b.evidencia_esperada, y);
      y = parrafo(doc, "Recomendación: " + b.recomendacion, y);
      y = parrafo(doc, "Ruta formativa vinculada: " + b.ruta_formativa, y);
      y += 4;
    });

    doc.save("informe-therion-labs-" + informe.diagnostico_id.slice(0, 8) + ".pdf");
  }

  return { generarInformePdf: generarInformePdf };
})();
