// ============================================================================
// Utilidades de interfaz compartidas por todas las páginas: guardia de
// autenticación/onboarding (equivalente al AppShell de la versión Next.js),
// render del sidebar, modal, tarjeta de anillo y tags de estado.
// ============================================================================
window.Therion = window.Therion || {};

Therion.ui = (function () {
  "use strict";

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var ENLACES = [
    { href: "dashboard.html", label: "Panel" },
    { href: "diagnostico.html", label: "Autodiagnóstico" },
    { href: "informe.html", label: "Ver informe" },
    { href: "formacion-mapa.html", label: "Formación" },
    { href: "panel-sectorial.html", label: "Panel sectorial" },
    { href: "perfil.html", label: "Perfil" },
  ];

  function renderSidebar(me) {
    var paginaActual = window.location.pathname.split("/").pop();
    var enlaces = ENLACES.slice();
    if (me.rol === "admin_therion") {
      enlaces.push({ href: "admin-matriz.html", label: "Backoffice: matriz" });
      enlaces.push({ href: "admin-arbol.html", label: "Backoffice: árbol" });
    }

    var html = '<aside class="sidebar">';
    html += '<div class="sidebar-header">';
    html += '<div class="brand font-editorial">ComplainceIA</div>';
    html += '<div class="user">' + escapeHtml(me.nombre) + '</div>';
    html += '</div>';
    html += '<div class="demo-tag">Modo demo &middot; datos de ejemplo</div>';
    html += '<nav class="sidebar-nav">';
    enlaces.forEach(function (l) {
      var activo = paginaActual === l.href ? " active" : "";
      html += '<a class="' + activo.trim() + '" href="' + l.href + '">' + escapeHtml(l.label) + "</a>";
    });
    html += "</nav>";
    html += '<div class="sidebar-footer">';
    html += '<button onclick="Therion.ui.cerrarSesion()">Salir</button>';
    html += '<button onclick="Therion.store.resetDemo()" style="color:var(--accent); margin-top:4px;">Reiniciar demo</button>';
    html += "</div></aside>";
    return html;
  }

  function cerrarSesion() {
    Therion.store.clearToken();
    window.location.href = "login.html";
  }

  function renderDemoBanner() {
    return (
      '<div class="demo-banner">' +
      "<span>Modo demo: todos los datos son de ejemplo, no hay backend conectado. Lo que hagas se guarda solo en este navegador.</span>" +
      '<button onclick="Therion.store.resetDemo()">Reiniciar demo</button>' +
      "</div>"
    );
  }

  /**
   * Guardia de página, equivalente al AppShell de la versión con React:
   *  - Si no hay sesión, redirige a login.html.
   *  - Si la organización no tiene diagnóstico cerrado, solo deja pasar a las
   *    páginas marcadas con permitidoSinDiagnostico=true (el flujo del
   *    cuestionario) y oculta el sidebar en esas páginas.
   *  - Si se pide un rol específico (rolesPermitidos) y no coincide, redirige
   *    al dashboard.
   * Devuelve una Promise que resuelve con el objeto `me`.
   */
  function protegerPagina(opciones) {
    opciones = opciones || {};
    var token = Therion.store.getToken();
    if (!token) {
      window.location.href = "login.html";
      return Promise.reject(new Error("sin sesión"));
    }
    return Therion.store.api.me().then(function (me) {
      if (!me.tiene_diagnostico_cerrado && !opciones.permitidoSinDiagnostico) {
        window.location.href = "cuestionario.html";
        throw new Error("redirigiendo");
      }
      if (opciones.rolesPermitidos && opciones.rolesPermitidos.indexOf(me.rol) === -1) {
        window.location.href = "dashboard.html";
        throw new Error("redirigiendo");
      }

      var mountSidebar = document.getElementById("sidebar-mount");
      var wrapper = document.getElementById("content-wrapper");
      if (me.tiene_diagnostico_cerrado) {
        if (mountSidebar) mountSidebar.innerHTML = renderSidebar(me);
        if (wrapper) wrapper.classList.add("with-sidebar");
      } else if (mountSidebar) {
        mountSidebar.innerHTML = "";
      }

      var bannerMount = document.getElementById("demo-banner-mount");
      if (bannerMount) bannerMount.innerHTML = renderDemoBanner();

      return me;
    }).catch(function (err) {
      if (err && err.message !== "redirigiendo") {
        Therion.store.clearToken();
        window.location.href = "login.html";
      }
      throw err;
    });
  }

  // ---- Status tag (estado de evaluación / riesgo / clasificación) ----
  var COLOR_ESTADO = {
    cumplido: "var(--verify)",
    parcial: "var(--partial)",
    no: "var(--gap)",
    na: "var(--na)",
    revision: "var(--review)",
  };
  var LABEL_ESTADO = {
    cumplido: "Cumplido",
    parcial: "Parcial",
    no: "No cumplido",
    na: "N/A",
    revision: "Requiere revisión",
  };
  var COLOR_RIESGO = {
    "Riesgo bajo": "var(--verify)",
    "Riesgo moderado": "var(--partial)",
    "Riesgo alto": "var(--gap)",
    "Sin evaluar": "var(--na)",
  };
  var COLOR_DIMENSION = {
    Adecuado: "var(--verify)",
    Parcial: "var(--partial)",
    Débil: "var(--gap)",
    "No evaluado": "var(--na)",
  };
  var COLOR_CRITICIDAD = { Alta: "var(--gap)", Media: "var(--partial)", Baja: "var(--na)" };
  var COLOR_DOMINIO_PREFIJO = { GOB: "var(--dom-gob)", RIE: "var(--dom-rie)", DAT: "var(--dom-dat)", SEG: "var(--dom-seg)" };

  function statusTagEstado(estado) {
    var color = COLOR_ESTADO[estado] || "var(--na)";
    var label = LABEL_ESTADO[estado] || estado;
    return '<span class="status-tag" style="background:' + color + '">' + escapeHtml(label) + "</span>";
  }

  function statusTag(label, color) {
    return '<span class="status-tag" style="background:' + color + '">' + escapeHtml(label) + "</span>";
  }

  function controlBadge(controlId) {
    var prefijo = (controlId || "").split("-")[0];
    var color = COLOR_DOMINIO_PREFIJO[prefijo] || "var(--accent)";
    return '<span class="control-badge" style="border-color:' + color + "; color:" + color + '">' + escapeHtml(controlId) + "</span>";
  }

  // ---- Gráfico de anillo (conic-gradient, sin librerías) ----
  function ring(porcentaje, color, opciones) {
    opciones = opciones || {};
    var size = opciones.size || 140;
    var thickness = opciones.thickness || 16;
    var centerLabel = opciones.centerLabel || "";
    var centerSubLabel = opciones.centerSubLabel || "";
    var valor = porcentaje === null || porcentaje === undefined ? 0 : porcentaje;
    var track = "rgba(100, 116, 139, 0.25)";
    var bg = porcentaje === null || porcentaje === undefined
      ? track
      : "conic-gradient(" + color + " " + (valor * 3.6) + "deg, " + track + " " + (valor * 3.6) + "deg)";
    var innerSize = size - thickness * 2;

    var html = '<div class="ring" style="width:' + size + "px; height:" + size + "px; background:" + bg + '">';
    html += '<div class="ring-inner" style="width:' + innerSize + "px; height:" + innerSize + 'px">';
    if (centerLabel) html += '<span class="big" style="font-size:' + Math.max(14, innerSize / 5) + 'px">' + escapeHtml(centerLabel) + "</span>";
    if (centerSubLabel) html += '<span class="small">' + escapeHtml(centerSubLabel) + "</span>";
    html += "</div></div>";
    return html;
  }

  // ---- Modal simple ----
  function mostrarModal(titulo, contenidoHtml) {
    cerrarModal();
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.id = "therion-modal-backdrop";
    backdrop.onclick = function (e) { if (e.target === backdrop) cerrarModal(); };
    backdrop.innerHTML =
      '<div class="modal-box">' +
      '<div class="modal-title"><h3 class="font-editorial">' + escapeHtml(titulo) + '</h3>' +
      '<button class="modal-close" onclick="Therion.ui.cerrarModal()">&times;</button></div>' +
      '<div>' + contenidoHtml + "</div></div>";
    document.body.appendChild(backdrop);
    document.addEventListener("keydown", escCierraModal);
  }
  function escCierraModal(e) { if (e.key === "Escape") cerrarModal(); }
  function cerrarModal() {
    var el = document.getElementById("therion-modal-backdrop");
    if (el) el.remove();
    document.removeEventListener("keydown", escCierraModal);
  }

  function mostrarError(elId, mensaje) {
    var el = document.getElementById(elId);
    if (!el) return;
    el.textContent = mensaje || "";
    el.classList.toggle("hidden", !mensaje);
  }

  return {
    escapeHtml: escapeHtml,
    renderSidebar: renderSidebar,
    renderDemoBanner: renderDemoBanner,
    protegerPagina: protegerPagina,
    cerrarSesion: cerrarSesion,
    statusTagEstado: statusTagEstado,
    statusTag: statusTag,
    controlBadge: controlBadge,
    ring: ring,
    mostrarModal: mostrarModal,
    cerrarModal: cerrarModal,
    mostrarError: mostrarError,
    COLOR_RIESGO: COLOR_RIESGO,
    COLOR_DIMENSION: COLOR_DIMENSION,
    COLOR_CRITICIDAD: COLOR_CRITICIDAD,
  };
})();
