// ============================================================================
// Sesión + estado persistido (localStorage) + "API" simulada. Reemplaza al
// backend real: cada función devuelve una Promise, igual que si fuera un
// fetch(), para que el código de cada página no tenga que distinguir entre
// la versión con backend y esta versión estática.
// ============================================================================
window.Therion = window.Therion || {};

Therion.store = (function () {
  "use strict";

  var TOKEN_KEY = "therion_token";
  var ESTADO_KEY = "therion_demo_state";
  var RETRASO_MS = 200;

  var PERSONAS = {
    nuevo: { nombre: "Usuario Nuevo", email: "nuevo@demo.cl", rol: "referente", organizacionId: "demo-org-nuevo" },
    completo: { nombre: "Camila Rojas", email: "completo@demo.cl", rol: "referente", organizacionId: "demo-org-completo" },
    admin: { nombre: "Admin Demo", email: "admin@demo.cl", rol: "admin_therion", organizacionId: null },
  };

  var ESTADOS_VALIDOS = ["cumplido", "parcial", "no", "na", "revision"];
  var ESTADOS_QUE_EXIGEN_EVIDENCIA = ["cumplido", "parcial"];

  function personaDesdeEmail(email) {
    var e = (email || "").toLowerCase();
    if (e.indexOf("nuevo") !== -1) return "nuevo";
    if (e.indexOf("admin") !== -1) return "admin";
    return "completo";
  }

  function getToken() {
    return window.localStorage.getItem(TOKEN_KEY);
  }
  function setToken(token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  }
  function clearToken() {
    window.localStorage.removeItem(TOKEN_KEY);
  }
  function resetDemo() {
    window.localStorage.removeItem(ESTADO_KEY);
    window.localStorage.removeItem(TOKEN_KEY);
    window.location.href = "login.html";
  }

  function personaActual() {
    var token = getToken();
    if (!token || token.indexOf("demo:") !== 0) return null;
    var persona = token.slice(5);
    return PERSONAS.hasOwnProperty(persona) ? persona : null;
  }

  function requerirPersona() {
    var persona = personaActual();
    if (!persona) throw new Error("No autenticado. Vuelve a iniciar sesión.");
    return persona;
  }

  function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms || RETRASO_MS); });
  }

  function generarId() {
    return "demo-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  function diagnosticoPrecargado(persona) {
    var ahora = new Date();
    var cerrado = new Date(ahora.getTime() - 9 * 24 * 3600 * 1000);
    var respuestas = {};
    Therion.data.GATES.forEach(function (g) { respuestas[g.orden] = true; });
    var evaluaciones = {};
    Therion.data.EVALUACIONES_PRECARGADAS.forEach(function (e) {
      evaluaciones[e.control_id] = {
        estado: e.estado,
        evidencia_texto: e.evidencia_texto,
        evidencia_archivo_nombre: e.evidencia_texto ? "evidencia-demo.pdf" : null,
      };
    });
    return {
      id: "demo-diag-" + persona,
      organizacion_id: PERSONAS[persona].organizacionId,
      estado: "cerrado",
      iniciado_en: new Date(cerrado.getTime() - 24 * 3600 * 1000).toISOString(),
      cerrado_en: cerrado.toISOString(),
      respuestas: respuestas,
      evaluaciones: evaluaciones,
    };
  }

  function estadoInicial() {
    return {
      controles: JSON.parse(JSON.stringify(Therion.data.CONTROLES)),
      progreso: {},
      diagnosticos: {
        nuevo: [],
        completo: [diagnosticoPrecargado("completo")],
        admin: [diagnosticoPrecargado("admin")],
      },
    };
  }

  function cargarEstado() {
    var crudo = window.localStorage.getItem(ESTADO_KEY);
    if (!crudo) {
      var inicial = estadoInicial();
      guardarEstado(inicial);
      return inicial;
    }
    try {
      return JSON.parse(crudo);
    } catch (err) {
      var reinicio = estadoInicial();
      guardarEstado(reinicio);
      return reinicio;
    }
  }

  function guardarEstado(estado) {
    window.localStorage.setItem(ESTADO_KEY, JSON.stringify(estado));
  }

  function universoControles(estado) {
    return estado.controles.map(function (c) { return c.control_id; });
  }

  function buscarDiagnostico(estado, persona, diagnosticoId) {
    var lista = estado.diagnosticos[persona] || [];
    for (var i = 0; i < lista.length; i++) {
      if (lista[i].id === diagnosticoId) return lista[i];
    }
    throw new Error("Diagnóstico no encontrado.");
  }

  function construirInforme(estado, diag) {
    var universo = universoControles(estado);
    var aplicabilidad = Therion.logica.calcularAplicabilidad(Therion.data.GATES, diag.respuestas, universo);

    var controlPorId = {};
    estado.controles.forEach(function (c) { controlPorId[c.control_id] = c; });

    var scoringInput = [];
    Object.keys(aplicabilidad.aplicables).forEach(function (controlId) {
      var ev = diag.evaluaciones[controlId];
      var control = controlPorId[controlId];
      if (!ev || !control) return;
      scoringInput.push({
        control_id: controlId,
        dominio: control.dominio,
        estado: ev.estado,
        criticidad: control.criticidad,
        evidencia_texto: ev.evidencia_texto,
      });
    });

    var scoring = Therion.logica.calcularScoring(scoringInput);
    var brechasPriorizadas = Therion.logica.priorizarBrechas(scoringInput);

    var brechas = brechasPriorizadas.map(function (b) {
      var control = controlPorId[b.control_id];
      if (!control) return null;
      var fuente = control.articulo_referencia
        ? control.framework_fuente + " — " + control.articulo_referencia
        : control.framework_fuente;
      return {
        control_id: b.control_id,
        dominio: b.dominio,
        criticidad: b.criticidad,
        estado: b.estado,
        fuente: fuente,
        brecha_asociada: control.brecha_asociada,
        evidencia_entregada: b.evidencia_texto || null,
        evidencia_esperada: control.evidencia_esperada,
        recomendacion: control.recomendacion,
        ruta_formativa: control.ruta_formativa,
      };
    }).filter(function (b) { return b !== null; });

    var porDimension = Object.keys(scoring.porDimension).map(function (dimension) {
      return {
        dimension: dimension,
        puntaje: scoring.porDimension[dimension],
        n_evaluados: scoring.conteoPorDimension[dimension],
        clasificacion: Therion.logica.clasificarDimension(scoring.porDimension[dimension]),
      };
    });

    return {
      diagnostico_id: diag.id,
      puntaje_general: scoring.puntajeGeneral,
      riesgo_general: Therion.logica.clasificarRiesgoGeneral(scoring.puntajeGeneral),
      n_evaluados: scoring.nEvaluados,
      n_aplicables: Object.keys(aplicabilidad.aplicables).length,
      por_dimension: porDimension,
      brechas: brechas,
    };
  }

  // ---- "API" pública (misma forma que el cliente real basado en fetch) ----
  var api = {
    login: function (email) {
      return delay().then(function () {
        var persona = personaDesdeEmail(email);
        return { access_token: "demo:" + persona, token_type: "bearer" };
      });
    },

    me: function () {
      return delay().then(function () {
        var persona = requerirPersona();
        var cfg = PERSONAS[persona];
        var estado = cargarEstado();
        var tieneCerrado = (estado.diagnosticos[persona] || []).some(function (d) { return d.estado === "cerrado"; });
        return {
          id: "demo-user-" + persona,
          nombre: cfg.nombre,
          email: cfg.email,
          rol: cfg.rol,
          organizacion_id: cfg.organizacionId,
          tiene_diagnostico_cerrado: tieneCerrado,
        };
      });
    },

    listarControles: function (params) {
      params = params || {};
      return delay().then(function () {
        var estado = cargarEstado();
        return estado.controles.filter(function (c) {
          return (!params.dominio || c.dominio === params.dominio) &&
            (!params.framework || c.framework_fuente === params.framework) &&
            (!params.tipo_fuente || c.tipo_fuente === params.tipo_fuente);
        });
      });
    },

    obtenerControl: function (controlId) {
      return delay().then(function () {
        var estado = cargarEstado();
        var control = estado.controles.filter(function (c) { return c.control_id === controlId; })[0];
        if (!control) throw new Error("Control no encontrado");
        return control;
      });
    },

    actualizarControl: function (controlId, payload) {
      return delay().then(function () {
        var persona = requerirPersona();
        if (PERSONAS[persona].rol !== "admin_therion") {
          throw new Error("No autorizado para esta acción (requiere rol admin_therion)");
        }
        var estado = cargarEstado();
        var idx = -1;
        for (var i = 0; i < estado.controles.length; i++) {
          if (estado.controles[i].control_id === controlId) { idx = i; break; }
        }
        if (idx === -1) throw new Error("Control no encontrado");
        var actual = estado.controles[idx];
        var actualizado = Object.assign({}, actual, payload, { version: actual.version + 1 });
        estado.controles[idx] = actualizado;
        guardarEstado(estado);
        return actualizado;
      });
    },

    reglasAplicabilidad: function () {
      return delay().then(function () {
        return JSON.parse(JSON.stringify(Therion.data.GATES));
      });
    },

    crearDiagnostico: function () {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var enCurso = (estado.diagnosticos[persona] || []).filter(function (d) { return d.estado === "en_curso"; })[0];
        if (!enCurso) {
          enCurso = {
            id: generarId(),
            organizacion_id: PERSONAS[persona].organizacionId,
            estado: "en_curso",
            iniciado_en: new Date().toISOString(),
            cerrado_en: null,
            respuestas: {},
            evaluaciones: {},
          };
          estado.diagnosticos[persona].push(enCurso);
          guardarEstado(estado);
        }
        return {
          id: enCurso.id,
          organizacion_id: enCurso.organizacion_id || "",
          estado: enCurso.estado,
          iniciado_en: enCurso.iniciado_en,
        };
      });
    },

    ultimoDiagnosticoCerrado: function () {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var cerrados = (estado.diagnosticos[persona] || [])
          .filter(function (d) { return d.estado === "cerrado"; })
          .sort(function (a, b) { return (b.cerrado_en || "").localeCompare(a.cerrado_en || ""); });
        if (cerrados.length === 0) throw new Error("La organización todavía no tiene diagnósticos cerrados");
        var diag = cerrados[0];
        return {
          id: diag.id,
          organizacion_id: diag.organizacion_id || "",
          estado: diag.estado,
          iniciado_en: diag.iniciado_en,
        };
      });
    },

    responderGate: function (diagnosticoId, orden, respuesta) {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var diag = buscarDiagnostico(estado, persona, diagnosticoId);
        if (diag.estado !== "en_curso") throw new Error("El diagnóstico ya está cerrado");

        diag.respuestas[orden] = respuesta;
        var universo = universoControles(estado);
        var resultado = Therion.logica.calcularAplicabilidad(Therion.data.GATES, diag.respuestas, universo);

        if (resultado.cerradoPorRaizNo) {
          diag.estado = "cerrado";
          diag.cerrado_en = new Date().toISOString();
        }
        guardarEstado(estado);

        var gate = Therion.data.GATES.filter(function (g) { return g.orden === orden; })[0];
        var controlesActivados = (respuesta && gate) ? gate.controles_si : [];

        return {
          orden: orden,
          controles_activados: controlesActivados,
          aplicables_totales: Object.keys(resultado.aplicables).sort(),
          siguiente_gate: resultado.siguienteGate,
          cerrado_por_raiz_no: resultado.cerradoPorRaizNo,
        };
      });
    },

    controlesAplicables: function (diagnosticoId) {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var diag = buscarDiagnostico(estado, persona, diagnosticoId);
        var universo = universoControles(estado);
        var resultado = Therion.logica.calcularAplicabilidad(Therion.data.GATES, diag.respuestas, universo);
        return {
          aplicables: Object.keys(resultado.aplicables).sort(),
          na: Object.keys(resultado.na).sort(),
          cerrado_por_raiz_no: resultado.cerradoPorRaizNo,
          siguiente_gate: resultado.siguienteGate,
        };
      });
    },

    registrarEvaluacion: function (diagnosticoId, controlId, estadoControl, archivo) {
      return delay().then(function () {
        if (ESTADOS_VALIDOS.indexOf(estadoControl) === -1) throw new Error("Estado inválido");
        var persona = requerirPersona();
        var estado = cargarEstado();
        var diag = buscarDiagnostico(estado, persona, diagnosticoId);
        if (diag.estado !== "en_curso") throw new Error("El diagnóstico ya está cerrado");

        var previa = diag.evaluaciones[controlId];
        var tieneEvidenciaPrevia = !!(previa && previa.evidencia_texto);

        if (ESTADOS_QUE_EXIGEN_EVIDENCIA.indexOf(estadoControl) !== -1 && !archivo && !tieneEvidenciaPrevia) {
          throw new Error("Los estados 'cumplido' y 'parcial' requieren adjuntar evidencia en PDF.");
        }
        if (archivo && archivo.type !== "application/pdf") {
          throw new Error("La evidencia debe subirse en formato PDF.");
        }

        var evidenciaTexto = previa ? previa.evidencia_texto : null;
        var evidenciaArchivoNombre = previa ? previa.evidencia_archivo_nombre : null;
        if (archivo) {
          evidenciaTexto = 'Evidencia extraída del PDF "' + archivo.name + '" (simulado, sin backend real).';
          evidenciaArchivoNombre = archivo.name;
        }

        diag.evaluaciones[controlId] = {
          estado: estadoControl,
          evidencia_texto: evidenciaTexto,
          evidencia_archivo_nombre: evidenciaArchivoNombre,
        };
        guardarEstado(estado);

        return {
          id: "demo-eval-" + controlId,
          control_id: controlId,
          estado: estadoControl,
          evidencia_texto: evidenciaTexto,
          evidencia_archivo_nombre: evidenciaArchivoNombre,
          evaluado_en: new Date().toISOString(),
        };
      });
    },

    cerrarDiagnostico: function (diagnosticoId) {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var diag = buscarDiagnostico(estado, persona, diagnosticoId);
        diag.estado = "cerrado";
        diag.cerrado_en = new Date().toISOString();
        guardarEstado(estado);
        return { id: diag.id, organizacion_id: diag.organizacion_id || "", estado: diag.estado, iniciado_en: diag.iniciado_en };
      });
    },

    informe: function (diagnosticoId) {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var diag = buscarDiagnostico(estado, persona, diagnosticoId);
        return construirInforme(estado, diag);
      });
    },

    mapaFormativo: function () {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var mapa = {};
        Therion.data.MODULOS.forEach(function (modulo) {
          var key = persona + ":" + modulo.id;
          var estadoModulo = estado.progreso[key] || "bloqueado";
          if (!mapa[modulo.dimension]) mapa[modulo.dimension] = [];
          mapa[modulo.dimension].push({ id: modulo.id, nivel: modulo.nivel, titulo: modulo.titulo, estado: estadoModulo });
        });
        return mapa;
      });
    },

    obtenerModulo: function (dimension, nivel) {
      return delay().then(function () {
        var modulo = Therion.data.MODULOS.filter(function (m) { return m.dimension === dimension && m.nivel === nivel; })[0];
        if (!modulo) throw new Error("Módulo no encontrado");
        return modulo;
      });
    },

    actualizarProgreso: function (moduloId) {
      return delay().then(function () {
        var persona = requerirPersona();
        var estado = cargarEstado();
        var key = persona + ":" + moduloId;
        var actual = estado.progreso[key] || "bloqueado";
        var siguiente = actual === "bloqueado" ? "en_curso" : "completado";
        estado.progreso[key] = siguiente;
        guardarEstado(estado);
        return { modulo_id: moduloId, estado: siguiente };
      });
    },

    panelSectorial: function (rubro) {
      return delay().then(function () {
        return Therion.data.PANEL_SECTORIAL.filter(function (p) { return !rubro || p.rubro_id === rubro; });
      });
    },

    ejecutarJobAnonimizacion: function () {
      return delay().then(function () {
        var estado = cargarEstado();
        var total = 0;
        Object.keys(estado.diagnosticos).forEach(function (persona) {
          estado.diagnosticos[persona].forEach(function (d) { total += Object.keys(d.evaluaciones).length; });
        });
        return { tipo: "anonimizacion", estado: "exitoso", filas_procesadas: total };
      });
    },
  };

  return {
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    resetDemo: resetDemo,
    personaActual: personaActual,
    api: api,
  };
})();
