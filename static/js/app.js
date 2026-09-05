const estadoEl = document.getElementById("estado");
const btnCapturar = document.getElementById("btn-capturar");
const btnIniciar = document.getElementById("btn-iniciar");
const btnDetener = document.getElementById("btn-detener");
const galeria = document.getElementById("galeria");

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
      estadoEl.textContent = "pyrealsense2 no instalado";
      estadoEl.className = "estado error";
    } else if (data.error) {
      estadoEl.textContent = "Error: " + data.error;
      estadoEl.className = "estado error";
    } else if (data.activa) {
      estadoEl.textContent = "Cámara activa";
      estadoEl.className = "estado ok";
    } else {
      estadoEl.textContent = "Cámara detenida";
      estadoEl.className = "estado";
    }
  } catch (e) {
    estadoEl.textContent = "Sin conexión con el servidor";
    estadoEl.className = "estado error";
  }
}

function agregarMiniatura(nombre) {
  const div = document.createElement("div");
  div.className = "miniatura";
  div.dataset.nombre = nombre;
  div.innerHTML = `
    <a href="/capturas/${nombre}" target="_blank">
      <img src="/capturas/${nombre}" alt="${nombre}" />
    </a>
    <div class="miniatura-pie">
      <span>${nombre}</span>
      <button class="btn-eliminar" data-nombre="${nombre}" title="Eliminar">🗑️</button>
    </div>`;
  const vacio = galeria.querySelector(".vacio");
  if (vacio) vacio.remove();
  galeria.prepend(div);
}

async function capturarFoto() {
  btnCapturar.disabled = true;
  try {
    const res = await fetch("/api/capturar", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      agregarMiniatura(data.archivo);
      mostrarFlash("Foto guardada: " + data.archivo);
    } else {
      mostrarFlash("Error: " + data.error);
    }
  } catch (e) {
    mostrarFlash("Error al capturar la foto");
  } finally {
    btnCapturar.disabled = false;
  }
}

async function eliminarFoto(nombre, elemento) {
  const res = await fetch("/api/eliminar/" + encodeURIComponent(nombre), { method: "POST" });
  const data = await res.json();
  if (data.ok) {
    elemento.remove();
    mostrarFlash("Foto eliminada");
  }
}

btnCapturar.addEventListener("click", capturarFoto);

btnIniciar.addEventListener("click", async () => {
  await fetch("/api/iniciar", { method: "POST" });
  actualizarEstado();
});

btnDetener.addEventListener("click", async () => {
  await fetch("/api/detener", { method: "POST" });
  actualizarEstado();
});

galeria.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-eliminar");
  if (!btn) return;
  const nombre = btn.dataset.nombre;
  eliminarFoto(nombre, btn.closest(".miniatura"));
});

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && document.activeElement.tagName !== "BUTTON") {
    e.preventDefault();
    capturarFoto();
  }
});

actualizarEstado();
setInterval(actualizarEstado, 4000);
