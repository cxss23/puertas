// Reproductor de pantallas. Solo pinta: qué se ve y qué primer paso sale lo decide Python (story.py).

const params = new URLSearchParams(location.search);
const person = params.get("person");
const day = params.get("day") || "0";

const $ = (sel) => document.querySelector(sel);
const sceneEl = $("#scene");
let scenes = [];
let index = 0;
let people = {};

// ---------- Utilidades ----------

async function api(path, body) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ person, ...body }) }
    : {};
  const reply = await fetch(path, options);
  return reply.json();
}

// Crea un elemento: el("p", "text", "Hola")
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, className, onClick) {
  const node = el("button", className, label);
  node.addEventListener("click", (event) => { event.stopPropagation(); onClick(node); });
  return node;
}

// Pide al servidor una pantalla que depende de lo que han hecho los dos.
async function dynamic(type, extra = "") {
  const here = index;
  const data = await api(`/api/dynamic?person=${person}&type=${type}${extra}`);
  return here === index ? data : null;      // null: la persona ya ha pasado de pantalla
}

// ---------- Inicio ----------

async function start() {
  people = await api("/api/people");
  if (!person) return showHome();
  await loadStory();
  show(0);
}

async function loadStory() {
  scenes = (await api(`/api/story?person=${person}&day=${day}`)).scenes;
}

function showHome() {
  $("#progress").replaceChildren();
  sceneEl.replaceChildren(
    el("p", "kicker", "Un plan, dos recorridos"),
    el("p", "text", "Cada uno entra desde su móvil. ¿Quién eres?"),
  );
  const options = el("div", "options");
  let jump = "0";
  for (const [id, info] of Object.entries(people)) {
    options.append(button(info.name, "", () => { location.href = `?person=${id}&day=${jump}`; }));
  }
  // Salto de tiempo para la demo: enseña qué pasa cuando vuelven otro día.
  const days = el("div", "row");
  for (const [value, label] of [["0", "Hoy"], ["3", "3 días después"], ["30", "Un mes después"]]) {
    days.append(button(label, value === jump ? "primary" : "ghost", (node) => {
      jump = value;
      days.querySelectorAll("button").forEach((other) => { other.className = other === node ? "primary" : "ghost"; });
    }));
  }
  const links = el("div", "home-links");
  const advisor = el("a", "", "Resumen del asesor"); advisor.href = "/advisor";
  links.append(advisor, button("Reiniciar la demo", "", async () => { await api("/api/reset", {}); location.reload(); }));
  sceneEl.append(options, el("p", "hint", "Salto de tiempo para la demo"), days, links);
}

// ---------- Navegación ----------

function show(i) {
  index = Math.max(0, Math.min(i, scenes.length - 1));
  const scene = scenes[index];

  $("#progress").replaceChildren(...scenes.map((_, n) => el("i", n <= index ? "done" : "")));
  sceneEl.replaceChildren();
  sceneEl.style.animation = "none"; sceneEl.offsetHeight; sceneEl.style.animation = "";
  $("#btn-detail").hidden = !scene.detail;
  $("#btn-ask").hidden = scene.type !== "card";

  renderers[scene.type](scene);
  api("/api/event", { kind: "seen", scene: scene.id });
}

const next = () => index < scenes.length - 1 && show(index + 1);
const back = () => index > 0 && show(index - 1);

// Tocar la parte derecha avanza y la izquierda retrocede, solo en pantallas de lectura.
sceneEl.addEventListener("click", (event) => {
  if (!["card", "intro"].includes(scenes[index]?.type)) return;
  const box = sceneEl.getBoundingClientRect();
  (event.clientX - box.left < box.width * 0.3) ? back() : next();
});
document.addEventListener("keydown", (event) => {
  if (event.target.matches("textarea, input")) return;
  if (event.key === "ArrowRight") next();
  if (event.key === "ArrowLeft") back();
});

// ---------- Visuales ----------

function visual(spec) {
  if (!spec || spec.type === "none") return null;
  if (spec.type === "number") {
    const box = el("div", "number", spec.value);
    box.append(el("small", "", spec.label));
    return box;
  }
  if (spec.type === "blocks") {
    const box = el("div", "blocks");
    for (let n = 0; n < spec.total; n++) {
      const block = el("i", n < spec.on ? "" : "extra");
      block.style.animationDelay = `${n * 40}ms, 1s`;
      box.append(block);
    }
    return box;
  }
  if (spec.type === "bars") {
    const box = el("div", "bars");
    const max = Math.max(...spec.bars.map((bar) => bar.value));
    for (const bar of spec.bars) {
      const row = el("div");
      const label = el("label");
      label.append(el("span", "", bar.label), el("span", "", bar.text));
      const track = el("div", "track");
      const fill = el("div", "fill");
      track.append(fill);
      row.append(label, track);
      box.append(row);
      setTimeout(() => { fill.style.width = `${(bar.value / max) * 100}%`; }, 150);
    }
    return box;
  }
  return null;
}

// Pantalla de espera mientras falta la pareja.
function waiting(data) {
  const link = `${location.origin}/?person=${data.partner}`;
  sceneEl.append(
    el("p", "kicker", "Falta la otra mitad"),
    el("p", "text", data.text),
    button(`Copiar el enlace para ${data.partner_name}`, "primary", (node) => {
      navigator.clipboard?.writeText(link);
      node.textContent = "Enlace copiado";
    }),
    button("Comprobar otra vez", "ghost", () => show(index)),
  );
}

// ---------- Tipos de pantalla ----------

const renderers = {
  // 1. El gancho: ¿coincidiréis?
  async intro() {
    const data = await dynamic("intro");
    if (!data) return;
    sceneEl.append(el("p", "kicker", data.kicker), el("p", "text big", data.text), el("p", "hint", data.sub),
      button("Empezar", "primary", next));
  },

  // 2. Qué te preocupa. Al responder, la IA escribe las tres pantallas siguientes.
  question(scene) {
    sceneEl.append(el("p", "kicker", scene.kicker), el("p", "text", scene.text));
    const options = el("div", "options");
    const save = async (worry, text) => {
      sceneEl.replaceChildren(el("p", "kicker", "Un momento"), el("p", "text", "Estamos leyendo vuestro plan pensando en ti…"),
        el("div", "loader"));
      await api("/api/worry", { worry, text });
      await loadStory();
      show(index + 1);
    };
    for (const option of scene.options) {
      options.append(button(option.text, "", () => {
        if (!option.free_text) return save(option.id);
        const input = el("textarea"); input.rows = 3; input.placeholder = "Cuéntalo con tus palabras";
        options.replaceChildren(input, button("Seguir", "primary", () => save(option.id, input.value)));
        input.focus();
      }));
    }
    sceneEl.append(options);
  },

  // 3. Tres cosas que tienes que saber: un dato por pantalla.
  card(scene) {
    if (scene.intro) sceneEl.append(el("p", "hint", scene.intro));
    sceneEl.append(el("p", "kicker", scene.kicker), el("p", "text", scene.text));
    const picture = visual(scene.visual);
    if (picture) sceneEl.append(picture);
  },

  // 4. ¿Qué va primero? Se tocan los frentes en orden.
  rank(scene) {
    sceneEl.append(el("p", "kicker", scene.kicker), el("p", "text", scene.text), el("p", "hint", scene.hint));
    const order = [];
    const list = el("div", "rank");
    const done = button("Este es mi orden", "primary", async () => {
      await api("/api/rank", { order });
      next();
    });
    const refresh = () => {
      list.querySelectorAll(".front").forEach((item) => {
        const position = order.indexOf(item.dataset.id);
        item.classList.toggle("picked", position >= 0);
        item.querySelector(".badge").textContent = position >= 0 ? position + 1 : "";
      });
      done.disabled = order.length < scene.fronts.length;
    };
    for (const front of scene.fronts) {
      const item = button("", "front", () => {
        const position = order.indexOf(front.id);
        if (position >= 0) order.splice(position, 1); else order.push(front.id);
        refresh();
      });
      item.dataset.id = front.id;
      const words = el("span", "words");
      words.append(el("b", "", front.title), el("span", "", front.fact));
      item.append(el("span", "badge"), words);
      list.append(item);
    }
    sceneEl.append(list, done);
    refresh();
  },

  // 5. El encuentro: los dos órdenes, lado a lado.
  async encounter() {
    const data = await dynamic("encounter");
    if (!data) return;
    if (data.waiting) return waiting(data);

    sceneEl.append(el("p", "kicker", "El encuentro"), el("p", "text", data.text));
    const table = el("div", "meet");
    const head = el("div", "line head");
    head.append(el("span", ""), el("span", "", "Tú"), el("span", "", data.partner_name));
    table.append(head);
    data.rows.forEach((row, n) => {
      const line = el("div", `line ${row.match ? "match" : ""}`);
      line.append(el("span", "badge", String(row.position)), el("span", "", row.mine), el("span", "", row.theirs));
      line.style.animationDelay = `${0.3 + n * 0.45}s`;      // se descubren de una en una
      table.append(line);
    });
    const insight = el("p", "detail show", data.insight);
    insight.style.animationDelay = `${0.3 + data.rows.length * 0.45}s`;
    sceneEl.append(table, insight, button("Ver nuestro primer paso", "primary", next));
  },

  // 6. La ficha de un paso: qué hacer, la parte de cada uno, cuánto cuesta y qué preguntar.
  async step(scene) {
    const data = await dynamic("step", `&which=${scene.which}`);
    if (!data) return;
    if (data.waiting) return waiting(data);

    scene.detail = data.detail;
    $("#btn-detail").hidden = false;
    const card = el("div", "mission");
    card.append(el("b", "", data.kicker), el("p", "", data.do));
    const parts = el("div", "parts");
    const part = (who, what) => { const row = el("div"); row.append(el("b", "", who), el("span", "", what)); return row; };
    parts.append(part("Tu parte", data.my_task), part(data.partner_name, data.partner_task),
      part("Cuánto cuesta", data.cost), part("Para vuestro asesor", data.ask));
    sceneEl.append(card, parts);

    if (data.with_date) {
      const date = el("input"); date.type = "date";
      date.value = data.reminder || new Date(Date.now() + 3 * 864e5).toISOString().slice(0, 10);
      const download = el("a", "primary", "Añadir mi parte al calendario");
      const setLink = () => { download.href = `/api/reminder.ics?person=${person}&date=${date.value}`; };
      date.addEventListener("change", setLink); setLink();
      sceneEl.append(el("p", "hint", "¿Qué día lo haces?"), date, download);
    }
    if (data.following) sceneEl.append(el("p", "hint", `Después: ${data.following.toLowerCase()}.`));
  },

  // Otro día: ¿has hecho tu parte? Y qué ha hecho el otro.
  async checkin() {
    const data = await dynamic("checkin");
    if (!data) return;
    const paint = (info) => {
      sceneEl.replaceChildren(el("p", "kicker", "De vuelta"), el("p", "text", info.text));
      if (!info.ready) return;
      sceneEl.append(el("p", "detail show", info.task), el("p", "hint", info.partner_line));
      if (info.message) { sceneEl.append(el("p", "text small", info.message)); }
      if (info.answered === true || (info.answered === false && info.message)) {
        sceneEl.append(button("Ver lo siguiente", "primary", next));
        return;
      }
      const answer = el("div", "options");
      if (info.answered === false) {
        answer.append(el("p", "hint", "¿Qué lo frenó?"));
        for (const blocker of info.blockers) {
          answer.append(button(blocker.text, "", async () => paint(await api("/api/checkin", { blocker: blocker.id }))));
        }
      } else {
        answer.append(
          button("Sí, hecho", "", async () => paint(await api("/api/checkin", { done: true }))),
          button("Todavía no", "", async () => paint(await api("/api/checkin", { done: false }))),
        );
      }
      sceneEl.append(answer);
    };
    paint(data);
  },
};

// ---------- Ver los números ----------

$("#btn-detail").addEventListener("click", () => {
  const scene = scenes[index];
  if (sceneEl.querySelector(".detail.numbers")) return;
  sceneEl.append(el("p", "detail numbers", scene.detail));
  sceneEl.scrollTo({ top: sceneEl.scrollHeight, behavior: "smooth" });
  api("/api/event", { kind: "detail", scene: scene.id });
});

// ---------- Tengo una duda ----------

$("#btn-ask").addEventListener("click", () => {
  $("#ask-answer").textContent = "";
  $("#ask-text").value = "";
  $("#sheet").hidden = false;
  $("#ask-text").focus();
});
$("#ask-close").addEventListener("click", () => { $("#sheet").hidden = true; });
$("#ask-send").addEventListener("click", async () => {
  const question = $("#ask-text").value.trim();
  if (!question) return;
  $("#ask-answer").textContent = "Buscando en vuestro plan…";
  const reply = await api("/api/ask", { scene: scenes[index].id, question });
  $("#ask-answer").textContent = reply.answer || reply.error;
});

start();
