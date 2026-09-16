// frontend/js/app.js

let userId = localStorage.getItem("wm_user_id");
if (!userId) {
  userId = crypto.randomUUID();
  localStorage.setItem("wm_user_id", userId);
}

let sesionActivaId = null;
let pronombreSeleccionado = "neutro";
let nombreAgenteGlobal = "Asistente Técnico";
let datosUsuarioCache = null;

// Control de Sesión a exportar / contextual
let sesionExportarId = null;
let sesionExportarTitulo = "consulta";
let sesionRenombrarId = null;
let menuContextualActivo = null;

// Sistema de Diálogo Personalizado
function mostrarDialogo({
  icono = "⚠️",
  titulo = "Confirmación",
  mensaje = "¿Deseas continuar?",
  textoConfirmar = "Confirmar",
  textoCancelar = "Cancelar",
  esPeligroso = false,
  soloAlerta = false
}) {
  return new Promise((resolve) => {
    const modal = document.getElementById("custom-dialog-modal");
    const iconEl = document.getElementById("custom-dialog-icon");
    const titleEl = document.getElementById("custom-dialog-title");
    const msgEl = document.getElementById("custom-dialog-msg");
    const btnConfirm = document.getElementById("custom-dialog-confirm-btn");
    const btnCancel = document.getElementById("custom-dialog-cancel-btn");

    iconEl.innerText = icono;
    titleEl.innerText = titulo;
    msgEl.innerText = mensaje;
    btnConfirm.innerText = textoConfirmar;

    if (esPeligroso) {
      btnConfirm.classList.add("danger");
    } else {
      btnConfirm.classList.remove("danger");
    }

    if (soloAlerta) {
      btnCancel.style.display = "none";
      btnConfirm.style.flex = "1";
    } else {
      btnCancel.style.display = "block";
      btnCancel.innerText = textoCancelar;
      btnConfirm.style.flex = "2";
    }

    function cerrar(resultado) {
      modal.style.display = "none";
      btnConfirm.onclick = null;
      btnCancel.onclick = null;
      resolve(resultado);
    }

    btnConfirm.onclick = () => cerrar(true);
    btnCancel.onclick = () => cerrar(false);

    modal.style.display = "flex";
  });
}

// Inicialización de Tema
function inicializarTema() {
  const guardado = localStorage.getItem("wm_theme") || "light";
  document.documentElement.setAttribute("data-theme", guardado);

  const check = document.getElementById("theme-toggle-check");
  const label = document.getElementById("theme-status-text");
  if (check) check.checked = guardado === "dark";
  if (label) label.innerText = guardado === "dark" ? "Modo oscuro" : "Modo claro";
}

function alternarTema(esOscuro) {
  const nuevoTema = esOscuro ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", nuevoTema);
  localStorage.setItem("wm_theme", nuevoTema);

  const label = document.getElementById("theme-status-text");
  if (label) label.innerText = esOscuro ? "Modo oscuro" : "Modo claro";
}

function seleccionarPronombre(valor, btn) {
  pronombreSeleccionado = valor;
  document.querySelectorAll('.btn-choice').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

async function inicializar() {
  inicializarTema();

  document.addEventListener("click", (e) => {
    if (menuContextualActivo && !menuContextualActivo.contains(e.target)) {
      cerrarMenuContextual();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      cerrarMenuContextual();
    }
  });

  try {
    const res = await fetch(`/api/user/${userId}`);
    datosUsuarioCache = await res.json();

    if (!datosUsuarioCache.disclaimer_aceptado) {
      const modal = document.getElementById("disclaimer-modal");
      if (modal) modal.style.display = "flex";
    } else {
      procederPostDisclaimer();
    }
  } catch (err) {
    console.error("Error consultando usuario:", err);
    const modal = document.getElementById("disclaimer-modal");
    if (modal) modal.style.display = "flex";
  }
}

async function aceptarDisclaimer() {
  const check = document.getElementById("dont-show-disclaimer-check");
  const noVolverAMostrar = check ? check.checked : false;

  try {
    await fetch('/api/user/disclaimer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        no_volver_a_mostrar: noVolverAMostrar
      })
    });
  } catch (e) {
    console.error("Error guardando preferencia de disclaimer:", e);
  }

  const modal = document.getElementById("disclaimer-modal");
  if (modal) modal.style.display = "none";

  procederPostDisclaimer();
}

async function procederPostDisclaimer() {
  if (!datosUsuarioCache || !datosUsuarioCache.registrado) {
    const onboarding = document.getElementById("onboarding-modal");
    if (onboarding) onboarding.style.display = "flex";
  } else {
    nombreAgenteGlobal = datosUsuarioCache.nombre_agente || "Asistente Técnico";
    actualizarTopbar(nombreAgenteGlobal);
    actualizarSidebarPerfil(datosUsuarioCache.nombre, datosUsuarioCache.pronombre);
    await cargarSesiones();
  }
}

function actualizarTopbar(nombre) {
  const nameEl = document.getElementById("topbar-agent-name");
  if (nameEl) nameEl.innerText = nombre;
  const avatar = document.getElementById("agent-avatar-icon");
  if (avatar) avatar.innerText = nombre.charAt(0).toUpperCase();
}

function actualizarSidebarPerfil(nombreUsuario, pronombre) {
  const nameEl = document.getElementById("sidebar-user-name");
  const pronounEl = document.getElementById("sidebar-user-pronoun");
  const avatarEl = document.getElementById("sidebar-user-avatar");

  if (nameEl && nombreUsuario) nameEl.innerText = nombreUsuario;
  if (pronounEl) {
    const etiquetas = { el: "Trato: Él", ella: "Trato: Ella", neutro: "Trato: Neutro" };
    pronounEl.innerText = etiquetas[pronombre] || "Configuración";
  }
  if (avatarEl && nombreUsuario) {
    avatarEl.innerText = nombreUsuario.charAt(0).toUpperCase();
  }
}

function abrirModalPerfil() {
  const modal = document.getElementById("onboarding-modal");
  const title = document.getElementById("modal-title");
  const desc = document.getElementById("modal-desc");
  const btnCancel = document.getElementById("btn-cancel-profile");

  if (title) title.innerText = "Editar perfil";
  if (desc) desc.innerText = "Modifica tus datos y el nombre de tu asistente.";
  if (btnCancel) btnCancel.style.display = "block";

  if (datosUsuarioCache) {
    document.getElementById("user-name-input").value = datosUsuarioCache.nombre || "";
    document.getElementById("agent-name-input").value = datosUsuarioCache.nombre_agente || "";
    const p = datosUsuarioCache.pronombre || "neutro";
    seleccionarPronombre(p, document.getElementById(`pronoun-${p}`));
  }

  modal.style.display = "flex";
}

function cerrarModalPerfil() {
  document.getElementById("onboarding-modal").style.display = "none";
}

async function guardarPerfil() {
  const nombreInput = document.getElementById("user-name-input").value.trim();
  const agenteInput = document.getElementById("agent-name-input").value.trim() || "Asistente Técnico";

  if (!nombreInput) {
    await mostrarDialogo({
      icono: "ℹ️",
      titulo: "Dato requerido",
      mensaje: "Por favor escribe tu nombre para continuar.",
      textoConfirmar: "Entendido",
      soloAlerta: true
    });
    return;
  }

  if (nombreInput.length > 30 || agenteInput.length > 25) {
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Límite excedido",
      mensaje: "El nombre personal no debe exceder 30 caracteres y el del agente 25.",
      textoConfirmar: "Corregir",
      soloAlerta: true
    });
    return;
  }

  await fetch('/api/user/onboarding', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      nombre: nombreInput,
      pronombre: pronombreSeleccionado,
      nombre_agente: agenteInput
    })
  });

  datosUsuarioCache = {
    registrado: true,
    nombre: nombreInput,
    pronombre: pronombreSeleccionado,
    nombre_agente: agenteInput,
    disclaimer_aceptado: true
  };

  nombreAgenteGlobal = agenteInput;
  actualizarTopbar(nombreAgenteGlobal);
  actualizarSidebarPerfil(nombreInput, pronombreSeleccionado);
  document.getElementById("onboarding-modal").style.display = "none";
  await cargarSesiones();
}

async function cargarSesiones() {
  try {
    const res = await fetch(`/api/sessions/${userId}`);
    const sesiones = await res.json();
    const listEl = document.getElementById("session-list");
    listEl.innerHTML = "";

    if (sesiones.length === 0) {
      await crearSesion();
      return;
    }

    sesiones.forEach(s => {
      const li = document.createElement("li");
      li.className = `session-item ${s.id === sesionActivaId ? 'active' : ''}`;
      li.onclick = () => alternarSesion(s.id);

      const wrap = document.createElement("div");
      wrap.className = "session-content-wrap";

      if (s.fijado) {
        const pinIcon = document.createElement("span");
        pinIcon.className = "session-pin-icon";
        pinIcon.title = "Chat fijado";
        pinIcon.innerHTML = `
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="17" x2="12" y2="22"></line>
            <path d="M5 17h14v-2l-2-2V5a1 1 0 0 0-1-1h-8a1 1 0 0 0-1 1v8l-2 2v2z"></path>
          </svg>
        `;
        wrap.appendChild(pinIcon);
      }

      const titleSpan = document.createElement("span");
      titleSpan.className = "session-title-text";
      titleSpan.innerText = s.titulo;
      wrap.appendChild(titleSpan);

      const btnDots = document.createElement("button");
      btnDots.className = "btn-session-options";
      btnDots.innerHTML = "•••";
      btnDots.title = "Opciones";
      btnDots.onclick = (e) => {
        e.stopPropagation();
        abrirMenuContextual(e, s.id, s.titulo, Boolean(s.fijado), li);
      };

      li.appendChild(wrap);
      li.appendChild(btnDots);
      listEl.appendChild(li);
    });

    if (!sesionActivaId && sesiones.length > 0) {
      alternarSesion(sesiones[0].id);
    }
  } catch (e) {
    console.error("Error al cargar sesiones:", e);
  }
}

// Menú Contextual (3 Puntos)
function abrirMenuContextual(event, sessionId, sessionTitle, estaFijado, itemEl) {
  cerrarMenuContextual();

  itemEl.classList.add("options-open");

  const menu = document.createElement("div");
  menu.className = "chat-context-menu";

  const textoPin = estaFijado ? "Desfijar chat" : "Fijar chat";
  const iconoPin = estaFijado ? `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="2" y1="2" x2="22" y2="22"></line>
      <path d="M12 17v5"></path>
      <path d="M9 9l-4 4v2h14v-2l-1.5-1.5"></path>
      <path d="M9 4h6a1 1 0 0 1 1 1v7"></path>
    </svg>
  ` : `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="12" y1="17" x2="12" y2="22"></line>
      <path d="M5 17h14v-2l-2-2V5a1 1 0 0 0-1-1h-8a1 1 0 0 0-1 1v8l-2 2v2z"></path>
    </svg>
  `;

  menu.innerHTML = `
    <button class="context-menu-item" id="opt-export">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path>
        <polyline points="16 6 12 2 8 6"></polyline>
        <line x1="12" y1="2" x2="12" y2="15"></line>
      </svg>
      Exportar chat
    </button>
    <button class="context-menu-item" id="opt-pin">
      ${iconoPin}
      ${textoPin}
    </button>
    <button class="context-menu-item" id="opt-rename">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
      </svg>
      Cambiar nombre
    </button>
    <div class="context-menu-divider"></div>
    <button class="context-menu-item danger" id="opt-delete">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"></polyline>
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
      </svg>
      Borrar chat
    </button>
  `;

  document.body.appendChild(menu);

  const rect = event.currentTarget.getBoundingClientRect();
  const menuWidth = 175;
  let left = rect.left;
  if (left + menuWidth > window.innerWidth - 10) {
    left = window.innerWidth - menuWidth - 10;
  }
  menu.style.left = `${left}px`;
  menu.style.top = `${rect.bottom + 5}px`;

  menuContextualActivo = menu;

  menu.querySelector("#opt-export").onclick = (e) => {
    e.stopPropagation();
    cerrarMenuContextual();
    abrirModalExportar(sessionId, sessionTitle);
  };

  menu.querySelector("#opt-pin").onclick = async (e) => {
    e.stopPropagation();
    cerrarMenuContextual();
    await alternarFijarSesion(sessionId);
  };

  menu.querySelector("#opt-rename").onclick = (e) => {
    e.stopPropagation();
    cerrarMenuContextual();
    abrirModalRenombrar(sessionId, sessionTitle);
  };

  menu.querySelector("#opt-delete").onclick = async (e) => {
    e.stopPropagation();
    cerrarMenuContextual();
    await eliminarChatIndividual(sessionId, sessionTitle);
  };
}

async function alternarFijarSesion(sessionId) {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/pin`, { method: "PATCH" });
    if (!res.ok) {
      const err = await res.json();
      await mostrarDialogo({
        icono: "📌",
        titulo: "Límite de fijados",
        mensaje: err.detail || "Solo puedes fijar un máximo de 3 consultas.",
        textoConfirmar: "Entendido",
        soloAlerta: true
      });
      return;
    }
    await cargarSesiones();
  } catch (err) {
    console.error("Error al fijar/desfijar sesión:", err);
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Error de red",
      mensaje: "Ocurrió un error al intentar fijar el chat. Verifica tu conexión.",
      textoConfirmar: "Aceptar",
      soloAlerta: true
    });
  }
}

// Modal Renombrar Chat
function abrirModalRenombrar(sessionId, sessionTitle) {
  sesionRenombrarId = sessionId;
  const inputEl = document.getElementById("rename-input");
  inputEl.value = sessionTitle;
  document.getElementById("rename-modal").style.display = "flex";
  inputEl.focus();
}

function cerrarModalRenombrar() {
  document.getElementById("rename-modal").style.display = "none";
  sesionRenombrarId = null;
}

async function guardarRenombrar() {
  if (!sesionRenombrarId) return;
  const inputEl = document.getElementById("rename-input");
  const nuevoTitulo = inputEl.value.trim();

  if (!nuevoTitulo) {
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Título requerido",
      mensaje: "El nombre de la consulta no puede estar vacío.",
      textoConfirmar: "Entendido",
      soloAlerta: true
    });
    return;
  }

  if (nuevoTitulo.length > 45) {
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Límite excedido",
      mensaje: "El título no puede exceder los 45 caracteres.",
      textoConfirmar: "Corregir",
      soloAlerta: true
    });
    return;
  }

  try {
    const res = await fetch(`/api/sessions/${sesionRenombrarId}/rename`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: nuevoTitulo })
    });

    if (!res.ok) throw new Error("No se pudo actualizar el nombre");

    cerrarModalRenombrar();
    await cargarSesiones();
  } catch (err) {
    console.error(err);
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Error",
      mensaje: "Hubo un problema al cambiar el nombre del chat. Intenta de nuevo.",
      textoConfirmar: "Aceptar",
      soloAlerta: true
    });
  }
}

async function eliminarChatIndividual(sessionId, sessionTitle) {
  const confirmado = await mostrarDialogo({
    icono: "🗑️",
    titulo: "Eliminar consulta",
    mensaje: `¿Deseas eliminar permanentemente "${sessionTitle}"? Esta acción no se puede deshacer.`,
    textoConfirmar: "Eliminar",
    textoCancelar: "Cancelar",
    esPeligroso: true
  });

  if (!confirmado) return;

  try {
    const res = await fetch(`/api/sessions/single/${sessionId}`, { method: "DELETE" });
    if (!res.ok) {
      await mostrarDialogo({
        icono: "⚠️",
        titulo: "Error",
        mensaje: "No se pudo eliminar la consulta. Intenta nuevamente.",
        textoConfirmar: "Aceptar",
        soloAlerta: true
      });
      return;
    }

    const scrollEl = document.getElementById("chat-scroll");
    if (scrollEl) scrollEl.innerHTML = "";
    sesionActivaId = null;

    await crearSesion();
  } catch (err) {
    console.error("Error eliminando chat individual:", err);
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Error de red",
      mensaje: "Ocurrió un error de conexión al intentar eliminar la consulta.",
      textoConfirmar: "Aceptar",
      soloAlerta: true
    });
  }
}

function cerrarMenuContextual() {
  if (menuContextualActivo) {
    const m = menuContextualActivo;
    m.classList.add("closing");
    document.querySelectorAll(".session-item.options-open").forEach(el => el.classList.remove("options-open"));
    setTimeout(() => {
      if (m.parentNode) m.parentNode.removeChild(m);
    }, 120);
    menuContextualActivo = null;
  }
}

// Modal y Procesos de Exportación
function abrirModalExportar(sessionId, sessionTitle) {
  sesionExportarId = sessionId;
  sesionExportarTitulo = sessionTitle || "consulta";
  document.getElementById("export-modal").style.display = "flex";
}

function cerrarModalExportar() {
  document.getElementById("export-modal").style.display = "none";
  sesionExportarId = null;
}

async function ejecutarExportacion(formato) {
  if (!sesionExportarId) return;

  try {
    const res = await fetch(`/api/messages/${sesionExportarId}`);
    const mensajes = await res.json();

    const nombreUsuario = (datosUsuarioCache && datosUsuarioCache.nombre) || "Usuario";
    const nombreAgente = nombreAgenteGlobal || "Asistente Técnico";

    if (formato === "json") {
      exportarComoJSON(mensajes, nombreUsuario, nombreAgente);
    } else if (formato === "html") {
      exportarComoHTML(mensajes, nombreUsuario, nombreAgente);
    }

    cerrarModalExportar();
  } catch (err) {
    console.error("Error al exportar:", err);
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Error de exportación",
      mensaje: "Ocurrió un problema preparando la descarga del archivo.",
      textoConfirmar: "Entendido",
      soloAlerta: true
    });
  }
}

function descargarArchivo(contenido, nombreArchivo, mimeType) {
  const blob = new Blob([contenido], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportarComoJSON(mensajes, nombreUsuario, nombreAgente) {
  const data = {
    titulo: sesionExportarTitulo,
    fecha_exportacion: new Date().toISOString(),
    usuario: nombreUsuario,
    agente: nombreAgente,
    mensajes: mensajes.map(m => ({
      remitente: m.rol === "user" ? nombreUsuario : nombreAgente,
      rol: m.rol,
      contenido: m.contenido,
      fuentes: m.fuentes || []
    }))
  };

  const nombreLimpio = sesionExportarTitulo.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  descargarArchivo(JSON.stringify(data, null, 2), `${nombreLimpio}.json`, "application/json");
}

function exportarComoHTML(mensajes, nombreUsuario, nombreAgente) {
  const temaActual = document.documentElement.getAttribute("data-theme") || "light";
  const esOscuro = temaActual === "dark";

  const colorFondo = esOscuro ? '#15181C' : '#F8F9FC';
  const colorTexto = esOscuro ? '#EDEDED' : '#12161A';
  const colorBorde = esOscuro ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 30, 96, 0.1)';
  const colorBurbujaAsistente = esOscuro ? '#20242A' : '#FFFFFF';
  const colorTextoAsistente = esOscuro ? '#F0F2F5' : '#12161A';
  const colorTagTexto = esOscuro ? '#4DBDF5' : '#001E60';

  // Configuración de marked global para exportación
  marked.setOptions({ breaks: true });

  let filasHtml = "";
  mensajes.forEach(m => {
    const esUser = m.rol === "user";
    const remitente = esUser ? nombreUsuario : nombreAgente;
    let fuentesHtml = "";

    if (m.fuentes && m.fuentes.length > 0) {
      const tags = m.fuentes.map(f => '<span class="source-tag">' + f + '</span>').join("");
      fuentesHtml = '<div class="sources-box"><strong>Fuentes:</strong> ' + tags + '</div>';
    }

    const contenidoHtml = marked.parse(m.contenido);

    filasHtml += `
      <div class="msg-row ${esUser ? 'user' : 'assistant'}">
        <div class="msg-sender">${remitente}</div>
        <div class="msg-bubble">
          <div class="msg-text">${contenidoHtml}</div>
          ${fuentesHtml}
        </div>
      </div>
    `;
  });

  const cssReglas = [
    "* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }",
    "body { background-color: " + colorFondo + "; color: " + colorTexto + "; display: flex; justify-content: center; padding: 40px 20px; }",
    ".chat-container { width: 100%; max-width: 840px; display: flex; flex-direction: column; gap: 22px; }",
    ".chat-header { padding-bottom: 20px; border-bottom: 1px solid " + colorBorde + "; }",
    ".chat-header h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }",
    ".chat-header span { font-size: 13px; color: #8898AA; }",
    ".msg-row { display: flex; flex-direction: column; width: 100%; }",
    ".msg-row.user { align-items: flex-end; }",
    ".msg-row.assistant { align-items: flex-start; }",
    ".msg-sender { font-size: 11.5px; font-weight: 600; color: #8898AA; margin-bottom: 5px; padding: 0 4px; }",
    ".msg-bubble { max-width: 75%; padding: 16px 20px; font-size: 14.5px; line-height: 1.6; border-radius: 18px; box-shadow: 0 4px 14px rgba(0,0,0,0.04); }",
    ".msg-row.user .msg-bubble { background: #0053E2; color: #FFFFFF; border-bottom-right-radius: 4px; }",
    ".msg-row.assistant .msg-bubble { background: " + colorBurbujaAsistente + "; color: " + colorTextoAsistente + "; border: 1px solid " + colorBorde + "; border-bottom-left-radius: 4px; }",
    ".sources-box { margin-top: 12px; padding-top: 10px; border-top: 1px solid " + colorBorde + "; font-size: 12px; }",
    ".source-tag { display: inline-block; background: rgba(77, 189, 245, 0.18); color: " + colorTagTexto + "; border-radius: 6px; padding: 3px 8px; margin: 3px 4px 3px 0; font-weight: 600; }",
    ".msg-bubble p { margin-bottom: 10px; } .msg-bubble p:last-child { margin-bottom: 0; }",
    ".msg-bubble ul, .msg-bubble ol { margin-left: 22px; margin-bottom: 12px; }",
    ".msg-bubble li { margin-bottom: 4px; }",
    ".msg-bubble h1, .msg-bubble h2, .msg-bubble h3 { margin: 16px 0 8px 0; font-weight: 700; line-height: 1.3; }",
    ".msg-bubble pre { background: rgba(0,0,0,0.08); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 12px 0; font-family: monospace; border: 1px solid " + colorBorde + "; }",
    ".msg-bubble code { font-family: monospace; background: rgba(0,0,0,0.08); padding: 2px 4px; border-radius: 4px; }",
    ".msg-bubble pre code { background: transparent; padding: 0; }",
    ".msg-bubble blockquote { border-left: 4px solid #0053E2; padding-left: 14px; margin: 12px 0; font-style: italic; background: rgba(0, 83, 226, 0.05); padding: 8px 14px; border-radius: 0 8px 8px 0; }"
  ].join("\n");

  const encabezadoHtml = '<!DOCTYPE html>\n<html lang="es">\n<head>\n  <meta charset="UTF-8">\n  <title>'
    + sesionExportarTitulo + ' | Consulta Técnica</title>\n  <style>\n'
    + cssReglas + '\n  </style>\n</head>\n<body>\n  <div class="chat-container">\n    <div class="chat-header">\n      <h1>'
    + sesionExportarTitulo + '</h1>\n      <span>Exportado el ' + new Date().toLocaleDateString() + ' • Asistente: ' + nombreAgente + '</span>\n    </div>\n';

  const pieHtml = '  </div>\n</body>\n</html>';
  const plantillaHtml = encabezadoHtml + filasHtml + pieHtml;

  const nombreLimpio = sesionExportarTitulo.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  descargarArchivo(plantillaHtml, `${nombreLimpio}.html`, "text/html");
}

async function crearSesion() {
  const res = await fetch(`/api/sessions/${userId}`, { method: 'POST' });
  const nueva = await res.json();
  sesionActivaId = nueva.id;
  await cargarSesiones();
  alternarSesion(nueva.id);
}

async function alternarSesion(sessionId) {
  sesionActivaId = sessionId;
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  await cargarHistorial(sessionId);
  await cargarSesiones();
}

async function cargarHistorial(sessionId) {
  try {
    const res = await fetch(`/api/messages/${sessionId}`);
    const mensajes = await res.json();
    const scrollEl = document.getElementById("chat-scroll");
    scrollEl.innerHTML = "";

    mensajes.forEach(m => renderizarBurbuja(m.contenido, m.rol, m.fuentes || []));
  } catch (e) {
    console.error("Error al cargar historial:", e);
  }
}

async function eliminarTodosLosChats() {
  const confirmado = await mostrarDialogo({
    icono: "🚨",
    titulo: "¿Vaciar todo el historial?",
    mensaje: "Se eliminarán todas las consultas guardadas de forma permanente. Esta acción no se puede deshacer.",
    textoConfirmar: "Eliminar todo",
    textoCancelar: "Cancelar",
    esPeligroso: true
  });

  if (!confirmado) return;

  try {
    const res = await fetch(`/api/sessions/${userId}/clear-all`, {
      method: "DELETE"
    });

    if (res.ok) {
      const listEl = document.getElementById("session-list");
      const scrollEl = document.getElementById("chat-scroll");
      if (listEl) listEl.innerHTML = "";
      if (scrollEl) scrollEl.innerHTML = "";
      sesionActivaId = null;

      await crearSesion();
    } else {
      await mostrarDialogo({
        icono: "⚠️",
        titulo: "Error",
        mensaje: "No se pudo vaciar el historial. Intenta nuevamente.",
        textoConfirmar: "Aceptar",
        soloAlerta: true
      });
    }
  } catch (err) {
    console.error("Error al vaciar chats:", err);
    await mostrarDialogo({
      icono: "⚠️",
      titulo: "Error de red",
      mensaje: "Ocurrió un error al intentar vaciar las consultas.",
      textoConfirmar: "Aceptar",
      soloAlerta: true
    });
  }
}

function mostrarIndicadorPensando() {
  const scrollEl = document.getElementById("chat-scroll");
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = "thinking-bubble";

  row.innerHTML = `
    <div class="typing-indicator">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>
  `;
  scrollEl.appendChild(row);
  scrollEl.scrollTop = scrollEl.scrollHeight;
}

function removerIndicadorPensando() {
  const thinking = document.getElementById("thinking-bubble");
  if (thinking) thinking.remove();
}

async function renderizarBurbuja(texto, rol, fuentes = []) {
  const scrollEl = document.getElementById("chat-scroll");
  const row = document.createElement("div");
  row.className = `message-row ${rol}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  marked.setOptions({ breaks: true });
  bubble.innerHTML = marked.parse(texto);

  row.appendChild(bubble);
  scrollEl.appendChild(row);

  if (fuentes && fuentes.length > 0) {
    const fuentesDiv = document.createElement("div");
    fuentesDiv.className = "sources-container";
    fuentesDiv.innerHTML = "<strong>Fuentes:</strong> ";
    fuentes.forEach(f => {
      const tag = document.createElement("span");
      tag.className = "source-tag";
      tag.innerText = f;
      fuentesDiv.appendChild(tag);
    });
    bubble.appendChild(fuentesDiv);
  }

  scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
}

async function enviarMensaje() {
  const input = document.getElementById("query-input");
  const texto = input.value.trim();
  if (!texto || !sesionActivaId) return;

  input.value = "";
  renderizarBurbuja(texto, "user", []);
  mostrarIndicadorPensando();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        session_id: sesionActivaId,
        pregunta: texto
      })
    });
    const data = await res.json();

    removerIndicadorPensando();
    await renderizarBurbuja(data.respuesta, "assistant", data.fuentes);
    await cargarSesiones();
  } catch (err) {
    removerIndicadorPensando();
    renderizarBurbuja("Ocurrió un error al enviar el mensaje. Intenta de nuevo.", "assistant", []);
  }
}

function alPresionarTecla(e) {
  if (e.key === "Enter") enviarMensaje();
}

window.onload = inicializar;