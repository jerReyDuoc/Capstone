// ============================================================================
// Utilidades de interfaz compartidas por todas las páginas.
// API retrocompatible con la versión anterior + helpers nuevos.
// Sin referencias a personas: el sidebar muestra el correo de la cuenta.
// ============================================================================
window.Therion = window.Therion || {};

Therion.ui = (function () {
  "use strict";

  // ---------- Escapes y helpers básicos ----------
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function attr(name, value) {
    if (value === undefined || value === null) return "";
    return " " + name + '="' + escapeHtml(value) + '"';
  }

  // ---------- Colores semánticos ----------
  var COLOR_RIESGO = {
    "Riesgo bajo": "var(--verify)",
    "Riesgo moderado": "var(--partial)",
    "Riesgo alto": "var(--gap)",
    "Sin evaluar": "var(--na)",
  };
  var COLOR_DIMENSION = {
    Adecuado: "var(--verify)",
    Parcial: "var(--partial)",
    "Débil": "var(--gap)",
    "No evaluado": "var(--na)",
  };
  var COLOR_CRITICIDAD = { Alta: "var(--gap)", Media: "var(--partial)", Baja: "var(--na)" };
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
    na: "No aplica",
    revision: "Requiere revisión",
  };
  var COLOR_DOMINIO_PREFIJO = {
    GOB: "var(--dom-gob)", RIE: "var(--dom-rie)",
    DAT: "var(--dom-dat)", SEG: "var(--dom-seg)",
  };

  // ---------- Sidebar ----------
  function seccionesSidebar(rol) {
    var secciones = [
      {
        titulo: "Evaluación",
        enlaces: [
          { href: "dashboard.html",     label: "Panel" },
          { href: "diagnostico.html",   label: "Autodiagnóstico" },
          { href: "informe.html",       label: "Informe de madurez" },
        ],
      },
      {
        titulo: "Desarrollo",
        enlaces: [
          { href: "formacion-mapa.html", label: "Mapa formativo" },
        ],
      },
      {
        titulo: "Benchmark",
        enlaces: [
          { href: "panel-sectorial.html", label: "Panel sectorial" },
        ],
      },
    ];
    if (rol === "admin_therion") {
      secciones.push({
        titulo: "Administración",
        enlaces: [
          { href: "admin-matriz.html", label: "Matriz de controles" },
          { href: "admin-arbol.html",  label: "Árbol de aplicabilidad" },
        ],
      });
    }
    return secciones;
  }

  function renderSidebar(me) {
    var paginaActual = window.location.pathname.split("/").pop();
    var secciones = seccionesSidebar(me.rol);

    var html = '<aside class="sidebar" id="therion-sidebar" aria-label="Navegación principal">';
    html += '<div class="sidebar-header">';
    html +=   '<div class="brand font-editorial">ComplainceIA</div>';
    html +=   '<div class="user">' + escapeHtml(me.email) + '</div>';
    if (me.organizacion_id) {
      html += '<div class="org">' + escapeHtml(me.organizacion_id) + '</div>';
    }
    html += '</div>';

    html += '<nav class="sidebar-nav">';
    secciones.forEach(function (sec) {
      html += '<div class="nav-group">';
      html +=   '<div class="nav-group-title">' + escapeHtml(sec.titulo) + '</div>';
      sec.enlaces.forEach(function (l) {
        var activo = paginaActual === l.href;
        html += '<a href="' + l.href + '"' +
                (activo ? ' class="active" aria-current="page"' : "") + '>' +
                escapeHtml(l.label) + '</a>';
      });
      html += '</div>';
    });
    html += '</nav>';

    html += '<div class="sidebar-footer">';
    html +=   '<button type="button" onclick="Therion.ui.cerrarSesion()" class="btn-logout">Cerrar sesión</button>';
    html += '</div></aside>';

    html += '<div class="sidebar-backdrop" id="therion-sidebar-backdrop" onclick="Therion.ui.toggleSidebar(false)"></div>';
    return html;
  }

  function renderMobileTopbar() {
    return (
      '<div class="mobile-topbar">' +
        '<span class="brand font-editorial">ComplainceIA</span>' +
        '<button type="button" class="menu-btn" aria-label="Abrir menú" ' +
                'onclick="Therion.ui.toggleSidebar(true)">Menú</button>' +
      '</div>'
    );
  }

  function toggleSidebar(open) {
    var sb = document.getElementById("therion-sidebar");
    var bd = document.getElementById("therion-sidebar-backdrop");
    if (!sb || !bd) return;
    sb.classList.toggle("open", !!open);
    bd.classList.toggle("open", !!open);
  }

  function cerrarSesion() {
    Therion.store.clearToken();
    window.location.href = "login.html";
  }

  // ---------- Aviso de entorno (sin la palabra "demo") ----------
  function renderDemoBanner() {
    return (
      '<div class="demo-banner" role="note">' +
        '<span>Entorno de pruebas. Los datos se guardan solo en este navegador.</span>' +
      '</div>'
    );
  }

  // ---------- Guardia de página ----------
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
        if (mountSidebar) {
          mountSidebar.innerHTML = renderMobileTopbar() + renderSidebar(me);
        }
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

  // ---------- Tags y badges ----------
  function statusTag(label, color) {
    return '<span class="status-tag" style="background:' + color + '">' +
           escapeHtml(label) + '</span>';
  }
  function statusTagEstado(estado) {
    var color = COLOR_ESTADO[estado] || "var(--na)";
    var label = LABEL_ESTADO[estado] || estado;
    return statusTag(label, color);
  }
  function controlBadge(controlId) {
    var prefijo = (controlId || "").split("-")[0];
    var color = COLOR_DOMINIO_PREFIJO[prefijo] || "var(--accent)";
    return '<span class="control-badge" style="border-color:' + color +
           '; color:' + color + '">' + escapeHtml(controlId) + '</span>';
  }

  // ---------- Ring ----------
  function ring(porcentaje, color, opciones) {
    opciones = opciones || {};
    var size = opciones.size || 140;
    var thickness = opciones.thickness || 16;
    var centerLabel = opciones.centerLabel || "";
    var centerSubLabel = opciones.centerSubLabel || "";
    var valor = (porcentaje === null || porcentaje === undefined) ? 0 : porcentaje;
    var track = "rgba(107,119,133,0.25)";
    var bg = (porcentaje === null || porcentaje === undefined)
      ? track
      : "conic-gradient(" + color + " " + (valor * 3.6) + "deg, " + track + " " + (valor * 3.6) + "deg)";
    var innerSize = size - thickness * 2;

    var html = '<div class="ring" style="width:' + size + 'px; height:' + size + 'px; background:' + bg + '">';
    html += '<div class="ring-inner" style="width:' + innerSize + 'px; height:' + innerSize + 'px">';
    if (centerLabel) html += '<span class="big" style="font-size:' + Math.max(14, innerSize / 5) + 'px">' + escapeHtml(centerLabel) + '</span>';
    if (centerSubLabel) html += '<span class="small">' + escapeHtml(centerSubLabel) + '</span>';
    html += '</div></div>';
    return html;
  }

  // ---------- Modal con focus trap ----------
  var _modalReturnFocus = null;

  function mostrarModal(titulo, contenidoHtml) {
    cerrarModal();
    _modalReturnFocus = document.activeElement;

    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.id = "therion-modal-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-label", titulo);
    backdrop.onclick = function (e) { if (e.target === backdrop) cerrarModal(); };
    backdrop.innerHTML =
      '<div class="modal-box">' +
        '<div class="modal-title">' +
          '<h3>' + escapeHtml(titulo) + '</h3>' +
          '<button type="button" class="modal-close" aria-label="Cerrar" ' +
                  'onclick="Therion.ui.cerrarModal()">&times;</button>' +
        '</div>' +
        '<div>' + contenidoHtml + '</div>' +
      '</div>';
    document.body.appendChild(backdrop);

    document.addEventListener("keydown", _onKeydownModal);

    var focusables = backdrop.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    (focusables[0] || backdrop.querySelector(".modal-close")).focus();
  }

  function _onKeydownModal(e) {
    if (e.key === "Escape") { cerrarModal(); return; }
    if (e.key !== "Tab") return;
    var backdrop = document.getElementById("therion-modal-backdrop");
    if (!backdrop) return;
    var focusables = Array.prototype.slice.call(
      backdrop.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    );
    if (focusables.length === 0) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }

  function cerrarModal() {
    var el = document.getElementById("therion-modal-backdrop");
    if (el) el.remove();
    document.removeEventListener("keydown", _onKeydownModal);
    if (_modalReturnFocus && typeof _modalReturnFocus.focus === "function") {
      try { _modalReturnFocus.focus(); } catch (e) {}
    }
    _modalReturnFocus = null;
  }

  // ---------- Mensajes ----------
  function mostrarError(elId, mensaje) {
    var el = document.getElementById(elId);
    if (!el) return;
    if (!mensaje) {
      el.textContent = "";
      el.classList.add("hidden");
      el.removeAttribute("role");
      el.removeAttribute("aria-live");
      return;
    }
    el.className = el.className.replace(/\balert\b|\balert--\w+\b/g, "").trim();
    if (!el.classList.contains("alert")) el.classList.add("alert");
    el.classList.remove("hidden", "error-text");
    el.classList.add("alert--error");
    el.setAttribute("role", "alert");
    el.setAttribute("aria-live", "assertive");
    el.innerHTML = '<span class="icon" aria-hidden="true">!</span><span>' + escapeHtml(mensaje) + '</span>';
  }

  function mostrarExito(elId, mensaje) {
    var el = document.getElementById(elId);
    if (!el) return;
    if (!mensaje) { el.textContent = ""; el.classList.add("hidden"); return; }
    el.className = el.className.replace(/\balert\b|\balert--\w+\b/g, "").trim();
    if (!el.classList.contains("alert")) el.classList.add("alert");
    el.classList.remove("hidden");
    el.classList.add("alert--success");
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML = '<span class="icon" aria-hidden="true">✓</span><span>' + escapeHtml(mensaje) + '</span>';
  }

  // ---------- Helpers de página ----------
  function breadcrumb(items) {
    var html = '<nav class="breadcrumb" aria-label="Ruta de navegación">';
    items.forEach(function (it, i) {
      if (i > 0) html += '<span class="sep" aria-hidden="true">/</span>';
      if (it.href && i < items.length - 1) {
        html += '<a href="' + it.href + '">' + escapeHtml(it.label) + '</a>';
      } else {
        html += '<span>' + escapeHtml(it.label) + '</span>';
      }
    });
    html += '</nav>';
    return html;
  }

  function pageHeader(opts) {
    var html = "";
    if (opts.breadcrumb) html += breadcrumb(opts.breadcrumb);
    html += '<header class="flex justify-between items-start gap-4 mb-6 wrap">';
    html +=   '<div>';
    if (opts.eyebrow) html += '<p class="text-caption u-upper mb-1">' + escapeHtml(opts.eyebrow) + '</p>';
    html +=     '<h1 class="text-h1">' + escapeHtml(opts.title) + '</h1>';
    if (opts.subtitle) html += '<p class="text-sm text-muted mt-2">' + escapeHtml(opts.subtitle) + '</p>';
    html +=   '</div>';
    if (opts.actions) html += '<div class="flex gap-2 wrap">' + opts.actions + '</div>';
    html += '</header>';
    return html;
  }

  function campo(etiqueta, valor) {
    return (
      '<div class="mb-3">' +
        '<p class="text-caption u-upper">' + escapeHtml(etiqueta) + '</p>' +
        '<p class="text-sm mt-1">' + (valor ? escapeHtml(valor) : '<span class="text-faint">—</span>') + '</p>' +
      '</div>'
    );
  }

  function emptyState(opts) {
    return (
      '<div class="empty-state">' +
        '<h3>' + escapeHtml(opts.title || "Sin datos") + '</h3>' +
        (opts.description ? '<p class="text-sm mt-1">' + escapeHtml(opts.description) + '</p>' : "") +
        (opts.actionHtml ? '<div class="mt-4">' + opts.actionHtml + '</div>' : "") +
      '</div>'
    );
  }

  function skeletonList(rows) {
    var html = "";
    for (var i = 0; i < (rows || 3); i++) {
      html += '<div class="card mb-3">' +
              '<div class="skeleton" style="width:30%;height:12px;margin-bottom:10px;"></div>' +
              '<div class="skeleton" style="width:100%;height:14px;margin-bottom:6px;"></div>' +
              '<div class="skeleton" style="width:80%;height:14px;"></div>' +
              '</div>';
    }
    return html;
  }

  function formatFecha(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
    } catch (e) { return "—"; }
  }

  // ---------- Exports ----------
  return {
    escapeHtml: escapeHtml,
    attr: attr,
    renderSidebar: renderSidebar,
    renderMobileTopbar: renderMobileTopbar,
    toggleSidebar: toggleSidebar,
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
    mostrarExito: mostrarExito,
    breadcrumb: breadcrumb,
    pageHeader: pageHeader,
    campo: campo,
    emptyState: emptyState,
    skeletonList: skeletonList,
    formatFecha: formatFecha,
    COLOR_RIESGO: COLOR_RIESGO,
    COLOR_DIMENSION: COLOR_DIMENSION,
    COLOR_CRITICIDAD: COLOR_CRITICIDAD,
    COLOR_ESTADO: COLOR_ESTADO,
    LABEL_ESTADO: LABEL_ESTADO,
  };
})();