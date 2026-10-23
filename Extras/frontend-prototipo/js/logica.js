// ============================================================================
// Motor de aplicabilidad y de scoring, en JavaScript puro (sin dependencias).
// Es una réplica exacta de las reglas del backend real (Python):
//   - backend/app/services/aplicabilidad.py
//   - backend/app/services/scoring.py
// ============================================================================
window.Therion = window.Therion || {};

Therion.logica = (function () {
  "use strict";

  // ---- Aplicabilidad ----
  function calcularAplicabilidad(gates, respuestas, universo) {
    var ordenados = gates.slice().sort(function (a, b) { return a.orden - b.orden; });
    var raiz = ordenados.filter(function (g) { return g.es_raiz; })[0] || ordenados[0];
    var raizRespuesta = respuestas[raiz.orden];

    if (raizRespuesta === false) {
      return {
        aplicables: {},
        na: universo.reduce(function (acc, c) { acc[c] = true; return acc; }, {}),
        cerradoPorRaizNo: true,
        siguienteGate: null,
      };
    }

    var aplicables = {};
    if (raizRespuesta === true) {
      raiz.controles_si.forEach(function (c) { aplicables[c] = true; });
      ordenados.forEach(function (gate) {
        if (gate.es_raiz) return;
        if (respuestas[gate.orden] === true) {
          gate.controles_si.forEach(function (c) { aplicables[c] = true; });
        }
      });
    }

    var siguienteGate = null;
    if (raizRespuesta === undefined) {
      siguienteGate = raiz.orden;
    } else {
      for (var i = 0; i < ordenados.length; i++) {
        var gate = ordenados[i];
        if (gate.es_raiz) continue;
        if (!(gate.orden in respuestas)) {
          siguienteGate = gate.orden;
          break;
        }
      }
    }

    var na = {};
    universo.forEach(function (c) { if (!aplicables[c]) na[c] = true; });

    return { aplicables: aplicables, na: na, cerradoPorRaizNo: false, siguienteGate: siguienteGate };
  }

  // ---- Scoring ----
  var DIMENSIONES = ["Gobernanza de IA", "Gestión de Riesgos", "Protección de Datos", "Uso Responsable"];

  var PESO_ESTADO = { cumplido: 100, parcial: 50, revision: 50, no: 0 };
  var PESO_SIN_EVIDENCIA = { cumplido: 50, parcial: 25 };

  function peso(e) {
    var p = PESO_ESTADO[e.estado];
    if (PESO_SIN_EVIDENCIA.hasOwnProperty(e.estado) && !e.evidencia_texto) {
      p = PESO_SIN_EVIDENCIA[e.estado];
    }
    return p;
  }

  function redondear(v) {
    return Math.round(v * 10) / 10;
  }

  function calcularScoring(evaluaciones) {
    var computables = evaluaciones.filter(function (e) { return PESO_ESTADO.hasOwnProperty(e.estado); });

    var porDimension = {};
    var conteoPorDimension = {};
    DIMENSIONES.forEach(function (dimension) {
      var valores = computables.filter(function (e) { return e.dominio === dimension; }).map(peso);
      conteoPorDimension[dimension] = valores.length;
      porDimension[dimension] = valores.length
        ? redondear(valores.reduce(function (a, b) { return a + b; }, 0) / valores.length)
        : null;
    });

    var valoresGenerales = computables.map(peso);
    var puntajeGeneral = valoresGenerales.length
      ? redondear(valoresGenerales.reduce(function (a, b) { return a + b; }, 0) / valoresGenerales.length)
      : null;

    return {
      puntajeGeneral: puntajeGeneral,
      nEvaluados: valoresGenerales.length,
      porDimension: porDimension,
      conteoPorDimension: conteoPorDimension,
    };
  }

  function priorizarBrechas(evaluaciones) {
    var ordenCriticidad = { Alta: 0, Media: 1, Baja: 2 };
    var ordenEstado = { no: 0, revision: 1, parcial: 2 };
    return evaluaciones
      .filter(function (e) { return ["no", "parcial", "revision"].indexOf(e.estado) !== -1; })
      .sort(function (a, b) {
        var ca = ordenCriticidad.hasOwnProperty(a.criticidad) ? ordenCriticidad[a.criticidad] : 3;
        var cb = ordenCriticidad.hasOwnProperty(b.criticidad) ? ordenCriticidad[b.criticidad] : 3;
        if (ca !== cb) return ca - cb;
        var ea = ordenEstado.hasOwnProperty(a.estado) ? ordenEstado[a.estado] : 3;
        var eb = ordenEstado.hasOwnProperty(b.estado) ? ordenEstado[b.estado] : 3;
        return ea - eb;
      });
  }

  function clasificarRiesgoGeneral(puntaje) {
    if (puntaje === null || puntaje === undefined) return "Sin evaluar";
    if (puntaje >= 75) return "Riesgo bajo";
    if (puntaje >= 40) return "Riesgo moderado";
    return "Riesgo alto";
  }

  function clasificarDimension(puntaje) {
    if (puntaje === null || puntaje === undefined) return "No evaluado";
    if (puntaje >= 75) return "Adecuado";
    if (puntaje >= 40) return "Parcial";
    return "Débil";
  }

  return {
    DIMENSIONES: DIMENSIONES,
    calcularAplicabilidad: calcularAplicabilidad,
    calcularScoring: calcularScoring,
    priorizarBrechas: priorizarBrechas,
    clasificarRiesgoGeneral: clasificarRiesgoGeneral,
    clasificarDimension: clasificarDimension,
  };
})();
