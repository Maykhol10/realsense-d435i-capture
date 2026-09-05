const estadoEl = document.getElementById("estado");
const btnCapturar = document.getElementById("btn-capturar");
const btnIniciar = document.getElementById("btn-iniciar");
const btnDetener = document.getElementById("btn-detener");
const btnDescargarTodas = document.getElementById("btn-descargar-todas");
const galeria = document.getElementById("galeria");
const distribucion = document.getElementById("distribucion");
const inputClase = document.getElementById("input-clase");
const badgeClase = document.getElementById("badge-clase");
const chkRafaga = document.getElementById("chk-rafaga");
const selIntervalo = document.getElementById("sel-intervalo");
const datasetHeader = document.querySelector(".conteo-total");

let rafagaTimer = null;

function claseActual() {
  return (inputClase.value || "").trim() || "sin_clase";
}

function mostrarFlash(mensaje) {
  let flash = document.querySelector(".flash");
  if (!flash) {
    flash = document.createElement("div");
    flash.className = "flash";
    document.body.appendChild(flash);
  }
  flash.textContent = mensaje;
  flash.classList.add("mostrar");
  clearTimeout(flash._t);
  flash._t = setTimeout(() => flash.classList.remove("mostrar"), 2000);
}

async function actualizarEstado() {
  try {
    const res = await fetch("/api/estado");
    const data = await res.json();
    if (!data.pyrealsense2_disponible) {
      estadoEl.className = "chip-estado error";
      estadoEl.querySelector(".texto").textContent = "pyrealsense2 no instalado";
    } else if (data.error) {
      estadoEl.className = "chip-estado error";
      estadoEl.querySelector(".texto").textContent = "Error: " + data.error;
    } else if (data.activa) {
      estadoEl.className = "chip-estado ok";
      estadoEl.querySelector(".texto").textContent = "Cámara activa";
    } else {
      estadoEl.className = "chip-estado";
      estadoEl.querySelector(".texto").textContent = "Cámara detenida";
    }
  } catch (e) {
    estadoEl.className = "chip-estado error";
    estadoEl.querySelector(".texto").textContent = "Sin conexión con el servidor";
  }
}

function actualizarBadgeClase() {
  badgeClase.textContent = claseActual();
}

function actualizarContadorTotal() {
  const total = galeria.querySelectorAll(".miniatura").length;
  const clases = galeria.querySelectorAll(".grupo-clase").length;
  datasetHeader.textContent =
    `${total} foto${total !== 1 ? "s" : ""} · ${clases} clase${clases !== 1 ? "s" : ""}`;
  if (total > 0) {
    btnDescargarTodas.removeAttribute("aria-disabled");
  } else {
    btnDescargarTodas.setAttribute("aria-disabled", "true");
  }
}

function actualizarBarraDistribucion() {
  const conteos = {};
  galeria.querySelectorAll(".grupo-clase").forEach((grupo) => {
    const clase = grupo.querySelector(".miniaturas").dataset.clase;
    conteos[clase] = grupo.querySelectorAll(".miniatura").length;
  });
  const total = Object.values(conteos).reduce((a, b) => a + b, 0);

  distribucion.innerHTML = "";
  Object.keys(conteos)
    .sort()
    .forEach((clase) => {
      const cantidad = conteos[clase];
      const pct = total ? (cantidad / total) * 100 : 0;
      const div = document.createElement("div");
      div.className = "barra-clase";
      div.dataset.clase = clase;
      div.innerHTML = `
        <div class="barra-etiqueta"><span>${clase}</span><span class="barra-cantidad">${cantidad}</span></div>
        <div class="barra-fondo"><div class="barra-relleno" style="width:${pct}%"></div></div>`;
      distribucion.appendChild(div);
    });
}

function crearGrupoClase(clase) {
  const details = document.createElement("details");
  details.className = "grupo-clase";
  details.open = true;
  details.innerHTML = `
    <summary>
      <span class="grupo-titulo">${clase}</span>
      <span class="grupo-badge">0</span>
      <span class="grupo-acciones" onclick="event.stopPropagation()">
        <a class="btn-mini" href="/api/descargar_clase/${encodeURIComponent(clase)}" title="Descargar esta clase">⬇️</a>
        <button class="btn-mini btn-eliminar-clase" data-clase="${clase}" title="Eliminar clase completa">🗑️</button>
      </span>
    </summary>
    <div class="miniaturas" data-clase="${clase}"></div>`;
  return details;
}

function agregarMiniatura(clase, nombre) {
  const vacio = galeria.querySelector(".vacio");
  if (vacio) vacio.remove();

  let grupo = Array.from(galeria.querySelectorAll(".grupo-clase")).find(
    (g) => g.querySelector(".miniaturas").dataset.clase === clase
  );
  if (!grupo) {
    grupo = crearGrupoClase(clase);
    galeria.prepend(grupo);
  }

  const contenedor = grupo.querySelector(".miniaturas");
  const div = document.createElement("div");
  div.className = "miniatura";
  div.dataset.clase = clase;
  div.dataset.nombre = nombre;
  const urlFoto = `/capturas/${encodeURIComponent(clase)}/${encodeURIComponent(nombre)}`;
  div.innerHTML = `
    <a href="${urlFoto}" target="_blank">
      <img src="${urlFoto}" alt="${nombre}" loading="lazy" />
    </a>
    <div class="miniatura-pie">
      <span>${nombre}</span>
      <div class="miniatura-acciones">
        <a class="btn-descargar" href="/api/descargar/${encodeURIComponent(clase)}/${encodeURIComponent(nombre)}" title="Descargar">⬇️</a>
        <button class="btn-eliminar" data-clase="${clase}" data-nombre="${nombre}" title="Eliminar">🗑️</button>
      </div>
    </div>`;
  contenedor.prepend(div);
  grupo.querySelector(".grupo-badge").textContent = contenedor.querySelectorAll(".miniatura").length;

  actualizarContadorTotal();
  actualizarBarraDistribucion();
}

async function capturarFoto({ silencioso = false } = {}) {
  if (btnCapturar.disabled) return;
  btnCapturar.disabled = true;
  try {
    const res = await fetch("/api/capturar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clase: claseActual() }),
    });
    const data = await res.json();
    if (data.ok) {
      agregarMiniatura(data.clase, data.archivo);
      if (!silencioso) mostrarFlash(`Foto guardada en "${data.clase}"`);

      const opcion = document.querySelector(`#lista-clases option[value="${CSS.escape(data.clase)}"]`);
      if (!opcion) {
        const nueva = document.createElement("option");
        nueva.value = data.clase;
        document.getElementById("lista-clases").appendChild(nueva);
      }
    } else {
      mostrarFlash("Error: " + data.error);
      detenerRafaga();
    }
  } catch (e) {
    mostrarFlash("Error al capturar la foto");
    detenerRafaga();
  } finally {
    btnCapturar.disabled = false;
  }
}

function iniciarRafaga() {
  detenerRafaga();
  const intervalo = parseInt(selIntervalo.value, 10);
  btnCapturar.classList.add("capturando");
  capturarFoto({ silencioso: true });
  rafagaTimer = setInterval(() => capturarFoto({ silencioso: true }), intervalo);
}

function detenerRafaga() {
  if (rafagaTimer) {
    clearInterval(rafagaTimer);
    rafagaTimer = null;
  }
  btnCapturar.classList.remove("capturando");
  chkRafaga.checked = false;
}

async function eliminarFoto(clase, nombre, elemento) {
  const res = await fetch(`/api/eliminar/${encodeURIComponent(clase)}/${encodeURIComponent(nombre)}`, {
    method: "POST",
  });
  const data = await res.json();
  if (data.ok) {
    const grupo = elemento.closest(".grupo-clase");
    elemento.remove();
    const restantes = grupo.querySelectorAll(".miniatura").length;
    if (restantes === 0) {
      grupo.remove();
    } else {
      grupo.querySelector(".grupo-badge").textContent = restantes;
    }
    if (!galeria.querySelector(".miniatura")) {
      const p = document.createElement("p");
      p.className = "vacio";
      p.textContent = 'Todavía no hay fotos. Escribe una clase y presiona "Tomar foto" para empezar.';
      galeria.appendChild(p);
    }
    mostrarFlash("Foto eliminada");
    actualizarContadorTotal();
    actualizarBarraDistribucion();
  }
}

async function eliminarClase(clase, elemento) {
  if (!confirm(`¿Eliminar TODA la clase "${clase}" y sus fotos? Esta acción no se puede deshacer.`)) {
    return;
  }
  const res = await fetch(`/api/eliminar_clase/${encodeURIComponent(clase)}`, { method: "POST" });
  const data = await res.json();
  if (data.ok) {
    elemento.closest(".grupo-clase").remove();
    if (!galeria.querySelector(".miniatura")) {
      const p = document.createElement("p");
      p.className = "vacio";
      p.textContent = 'Todavía no hay fotos. Escribe una clase y presiona "Tomar foto" para empezar.';
      galeria.appendChild(p);
    }
    mostrarFlash(`Clase "${clase}" eliminada`);
    actualizarContadorTotal();
    actualizarBarraDistribucion();
  } else {
    mostrarFlash("Error: " + data.error);
  }
}

inputClase.addEventListener("input", actualizarBadgeClase);

btnCapturar.addEventListener("click", () => capturarFoto());

btnIniciar.addEventListener("click", async () => {
  await fetch("/api/iniciar", { method: "POST" });
  actualizarEstado();
});

btnDetener.addEventListener("click", async () => {
  detenerRafaga();
  await fetch("/api/detener", { method: "POST" });
  actualizarEstado();
});

chkRafaga.addEventListener("change", () => {
  if (chkRafaga.checked) {
    iniciarRafaga();
  } else {
    detenerRafaga();
  }
});

selIntervalo.addEventListener("change", () => {
  if (chkRafaga.checked) iniciarRafaga();
});

btnDescargarTodas.addEventListener("click", (e) => {
  if (btnDescargarTodas.getAttribute("aria-disabled") === "true") {
    e.preventDefault();
    mostrarFlash("No hay fotos para descargar");
  }
});

galeria.addEventListener("click", (e) => {
  const btnDel = e.target.closest(".btn-eliminar");
  if (btnDel) {
    eliminarFoto(btnDel.dataset.clase, btnDel.dataset.nombre, btnDel.closest(".miniatura"));
    return;
  }
  const btnDelClase = e.target.closest(".btn-eliminar-clase");
  if (btnDelClase) {
    eliminarClase(btnDelClase.dataset.clase, btnDelClase);
  }
});

document.addEventListener("keydown", (e) => {
  const enCampoTexto = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (e.code === "Space" && !enCampoTexto) {
    e.preventDefault();
    capturarFoto();
  }
});

actualizarEstado();
actualizarBadgeClase();
actualizarContadorTotal();
setInterval(actualizarEstado, 4000);
