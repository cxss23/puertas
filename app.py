"""Servidor de la app.

Arrancar:  python app.py   y abrir http://localhost:5000

Este archivo solo recibe peticiones del navegador y llama a:
  - story.py  -> la lógica (qué ve cada uno, el encuentro, el primer paso)
  - ai.py     -> la IA que escribe las pantallas personales
"""
import os
from datetime import date, datetime

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

load_dotenv()                    # lee .env antes de cargar los módulos que usan la clave

import ai                        # noqa: E402
import story                     # noqa: E402

app = Flask(__name__, static_folder="static", static_url_path="")
app.json.sort_keys = False       # respeta el orden del guion (Timothy, Melanie)

NOT_IN_PLAN = "Eso no está en vuestro plan. Se lo paso a vuestro asesor."


def person_arg():
    person = request.values.get("person") or (request.get_json(silent=True) or {}).get("person")
    if person not in story.load_scenes()["people"]:
        raise ValueError("Falta ?person= o no existe")
    return person


@app.errorhandler(ValueError)
def bad_request(error):
    return jsonify({"error": str(error)}), 400


# ---------- Páginas ----------

@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/advisor")
def advisor():
    return render_template("advisor.html", s=story.advisor_summary())


# ---------- La historia ----------

@app.get("/api/people")
def people():
    return jsonify(story.load_scenes()["people"])


@app.get("/api/story")
def get_story():
    day = int(request.args.get("day", 0))
    return jsonify({"scenes": story.build_story(person_arg(), day)})


@app.get("/api/dynamic")
def dynamic():
    """Pantallas cuyo contenido depende de lo que han hecho los dos."""
    person, kind = person_arg(), request.args.get("type")
    if kind == "intro":
        return jsonify(story.intro(person))
    if kind == "encounter":
        return jsonify(story.encounter(person))
    if kind == "step":
        return jsonify(story.step(person, int(request.args.get("which", 0))))
    if kind == "checkin":
        return jsonify(story.checkin(person))
    raise ValueError("Tipo de pantalla desconocido")


# ---------- Lo que hace la persona ----------

@app.post("/api/worry")
def worry():
    """Guarda la preocupación y pide a la IA las tres pantallas personales."""
    body, person = request.get_json(), person_arg()

    def change(state):
        state["people"][person]["worry"] = body["worry"]
        state["people"][person]["worry_text"] = body.get("text", "")
    story.update_state(change)
    source, note = ai.generate(person)
    return jsonify({"ok": True, "source": source, "note": note})


@app.post("/api/rank")
def rank():
    body, person = request.get_json(), person_arg()
    order = body["order"]
    if sorted(order) != sorted(story.fronts_by_id()):
        raise ValueError("El orden tiene que incluir todos los frentes, una vez cada uno")
    story.update_state(lambda s: s["people"][person].update({"order": order}))
    return jsonify({"ok": True})


@app.post("/api/event")
def event():
    """Registra qué pantallas vio y en cuáles abrió 'ver los números'."""
    body, person = request.get_json(), person_arg()
    kind = "details" if body["kind"] == "detail" else "seen"

    def change(state):
        seen = state["people"][person][kind]
        if body["scene"] not in seen:
            seen.append(body["scene"])
    story.update_state(change)
    return jsonify({"ok": True})


@app.post("/api/checkin")
def checkin():
    """Otro día: ¿has hecho tu parte? Si no, qué lo frenó."""
    body, person = request.get_json(), person_arg()

    def change(state):
        if "done" in body:
            state["household"]["done"][person] = bool(body["done"])
        if "blocker" in body:
            state["household"]["blockers"][person] = body["blocker"]
    story.update_state(change)
    return jsonify(story.checkin(person))


@app.post("/api/reset")
def reset():
    story.reset_state()
    return jsonify({"ok": True})


# ---------- Recordatorio: un evento de calendario, sin notificaciones ----------

@app.get("/api/reminder.ics")
def reminder():
    person = person_arg()
    day = date.fromisoformat(request.args["date"])
    step = story.step(person, 0)
    if step["waiting"]:
        raise ValueError("Aún no hay primer paso")
    story.update_state(lambda s: s["household"].update({"reminder": day.isoformat()}))
    link = f"{request.host_url}?person={person}&day=3"
    esc = lambda text: text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Un plan dos recorridos//ES",
        "BEGIN:VEVENT",
        f"UID:{stamp}-{person}@plan",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"SUMMARY:{esc(step['my_task'])}",
        f"DESCRIPTION:{esc(step['do'] + '. Cuando lo hagas, vuelve aquí: ')}{link}",
        f"URL:{link}",
        "END:VEVENT", "END:VCALENDAR", "",
    ])
    return Response(ics, mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=primer-paso.ics"})


# ---------- Dudas: el modelo responde solo con el plan ----------

def scene_by_id(person, scene_id):
    scenes = story.load_scenes()
    cards = story.personal_scenes(person) + scenes["fronts"] + scenes["later"]["dated"]
    return next((card for card in cards if card["id"] == scene_id), {})


def ask_model(scene, question):
    """Llama al proxy de IA con la parte del plan que corresponde a lo que está en pantalla."""
    narrative = story.load_plan()["narrative"]
    sections = ["summary_main"] + scene.get("plan_sections", [])
    plan_text = "\n\n".join(narrative[k] for k in sections if k in narrative)
    shown = " ".join(str(scene.get(k, "")) for k in ("text", "fact", "do", "cost", "detail"))
    system = (
        "Explicas a una familia su plan financiero ya existente, en español y con palabras sencillas. "
        "Responde en tres frases como máximo. Usa SOLO el plan de abajo y no inventes ninguna cifra. "
        "Si la pregunta pide algo que el plan no calcula (precios de seguros, otros escenarios, "
        f"consejos nuevos), responde exactamente: {NOT_IN_PLAN}\n\n"
        f"Lo que la familia está viendo en pantalla: {shown}\n\nPLAN:\n{plan_text}"
    )
    reply = requests.post(
        f"{ai.LLM_PROXY_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('TEAM_KEY', '')}"},
        json={"model": ai.MODEL, "messages": [{"role": "system", "content": system},
                                              {"role": "user", "content": question}]},
        timeout=60,
    )
    reply.raise_for_status()
    return reply.json()["choices"][0]["message"]["content"].strip()


@app.post("/api/ask")
def ask():
    body, person = request.get_json(), person_arg()
    question = body["question"].strip()
    if not question:
        raise ValueError("Pregunta vacía")
    for_advisor = True      # si el modelo no puede responder con el plan, la duda va al asesor
    if not os.environ.get("TEAM_KEY"):
        answer = "Las dudas con IA no están configuradas (falta TEAM_KEY en .env). La apunto para vuestro asesor."
    else:
        try:
            answer = ask_model(scene_by_id(person, body.get("scene")), question)
            for_advisor = "no está en vuestro plan" in answer.lower()
        except requests.RequestException:
            answer = "Ahora mismo no puedo responder. He apuntado tu duda para vuestro asesor."

    def change(state):
        state["people"][person]["questions"].append(
            {"scene": body.get("scene"), "question": question, "for_advisor": for_advisor})
    story.update_state(change)
    return jsonify({"answer": answer, "for_advisor": for_advisor})


if __name__ == "__main__":
    # host 0.0.0.0 para poder abrirlo desde el móvil en la misma wifi.
    app.run(host="0.0.0.0", port=5000, debug=True)
