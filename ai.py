"""La IA escribe las tres pantallas personales de cada miembro de la pareja.

Tres protecciones para que nunca falle delante de la familia:
  1. Solo puede usar cifras que existan en el plan: `check_numbers` lo comprueba.
  2. Si la respuesta no vale (formato, cifras, tiempo de espera), se usan los textos fijos del guion.
  3. Lo generado se guarda, así que solo se llama al modelo una vez por persona.
"""
import json
import os
import re

import requests
from dotenv import load_dotenv

import story

load_dotenv()          # por si este módulo se usa sin pasar por app.py

LLM_PROXY_URL = os.environ.get("LLM_PROXY_URL", "https://llm-hackathon.sherpaswealth.com")
MODEL = os.environ.get("MODEL", "gpt-5-mini")
TIMEOUT_SECONDS = 60

# Secciones del análisis de Sherpas que se le pasan al modelo.
NARRATIVE_SECTIONS = [
    "summary_main", "summary_recommendations", "debt_short_observations",
    "protection_life_insurance_short_observations", "protection_umbrella_short_observations",
    "protection_emergency_fund_short_observations", "savings_short_observations",
]

TONES = {
    "Growth": "directo, con la cifra por delante",
    "Aggressive": "directo, con la cifra por delante",
    "Moderate": "tranquilo: primero lo que está a salvo y después la cifra",
    "Conservative": "tranquilo: primero lo que está a salvo y después la cifra",
}


# ---------- Comprobación de cifras ----------

def allowed_numbers(*sources):
    """Todas las cifras que aparecen en el plan (números del JSON y números dentro de sus textos)."""
    found = set()

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(float(node))
        elif isinstance(node, str):
            # Formato inglés del plan: 150,800 o 22.8
            for match in re.findall(r"\d[\d,]*(?:\.\d+)?", node):
                found.add(float(match.replace(",", "")))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for source in sources:
        walk(source)
    return found


def numbers_in(text):
    """Cifras de un texto en formato español: 150.800 / 84.577,50 / 22,8."""
    return [float(m.replace(".", "").replace(",", ".")) for m in re.findall(r"\d[\d.]*\d(?:,\d+)?|\d(?:,\d+)?", text)]


def check_numbers(text, allowed):
    """Devuelve las cifras del texto que NO están en el plan. Lista vacía = todo correcto."""
    bad = []
    for number in numbers_in(text):
        if number <= 10 and number == int(number):
            continue                      # números pequeños de uso normal: "tres cosas", "los dos"
        ok = any(
            abs(a - number) < 0.051                         # la misma cifra (o redondeada a un decimal)
            or round(a) == number                           # redondeada a entero
            or (0 < a < 1 and abs(a * 100 - number) < 0.51)  # 0.228 en el plan, 22,8 % en el texto
            for a in allowed
        )
        if not ok:
            bad.append(number)
    return bad


# ---------- Lo que se le envía al modelo ----------

def build_messages(person):
    scenes = story.load_scenes()
    plan = story.load_plan()
    me = story.read_state()["people"][person]
    name = scenes["people"][person]["name"]
    partner_name = scenes["people"][scenes["people"][person]["partner"]]["name"]
    profile = next((h.get("risk_profile") for h in plan["case"]["household"] if h["first_name"] == name), None)
    worry = next((o["text"] for o in scenes["question"]["options"] if o["id"] == me["worry"]), "")
    if me["worry_text"]:
        worry = me["worry_text"]

    system = f"""Explicas a {name} el plan financiero de su familia. Escribes en español, con palabras sencillas y sin jerga.

Escribe exactamente 3 pantallas de móvil para {name}. Le preparan para decidir qué frente del plan va primero
(los frentes son: {', '.join(f['title'] for f in scenes['fronts'])}).

Reglas:
1. Cada pantalla tiene una sola idea y como mucho una cifra en "text" (máximo 170 caracteres).
2. Háblale de tú. Usa lo que es SUYO: su seguro, sus cuentas, su perfil de riesgo. A su pareja llámala {partner_name}.
3. Empieza por lo que le preocupa: «{worry}».
4. Usa SOLO cifras que aparezcan en los datos. No sumes, restes ni calcules cifras nuevas.
5. Formato de cifras en español: 150.800 $, 22,8 %, septiembre de 2039.
6. "detail": una o dos frases con las cifras de apoyo, para quien sabe de finanzas (máximo 260 caracteres).
7. "kicker": título de 2 a 5 palabras.
8. "number": la cifra grande de la pantalla, con "value" (por ejemplo "140.000 $") y "label" (qué es, en pocas palabras).
9. Tono: {TONES.get(profile, 'claro y cercano')}.
10. No des consejos que no estén en el plan, ni precios que el plan no trae.

Devuelve SOLO este JSON, sin texto antes ni después:
{{"scenes": [{{"kicker": "...", "text": "...", "detail": "...", "number": {{"value": "...", "label": "..."}}}}, ...]}}"""

    data = {
        "familia": plan["case"]["household"],
        "hechos_del_plan": plan["key_metrics"]["facts"],
        "movimientos_y_notas": {"nota": plan["score"]["published_score"],
                                "movimientos": plan["score"]["top_moves"],
                                "combinaciones": plan["score"]["combined_moves"]},
        "analisis": {k: plan["narrative"][k] for k in NARRATIVE_SECTIONS if k in plan["narrative"]},
        "frentes": [{"titulo": f["title"], "dato": f["fact"], "detalle": f["detail"]} for f in scenes["fronts"]],
        "perfil_de_la_familia": (story.BASE / "cases" / story.CASE / "persona.md").read_text(encoding="utf-8"),
    }
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]


# ---------- Leer y validar la respuesta ----------

def parse_scenes(reply_text, allowed):
    """Convierte la respuesta del modelo en pantallas. Lanza ValueError si algo no vale."""
    start, end = reply_text.find("{"), reply_text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("la respuesta no es JSON")
    cards = json.loads(reply_text[start:end + 1]).get("scenes")
    if not isinstance(cards, list) or len(cards) != 3:
        raise ValueError("no hay exactamente 3 pantallas")

    result = []
    for n, card in enumerate(cards, start=1):
        kicker, text, detail = (str(card.get(k, "")).strip() for k in ("kicker", "text", "detail"))
        if not kicker or not text:
            raise ValueError(f"pantalla {n} incompleta")
        if len(text) > 220:
            raise ValueError(f"pantalla {n} demasiado larga")
        number = card.get("number") or {}
        everything = " ".join([kicker, text, detail, str(number.get("value", "")), str(number.get("label", ""))])
        bad = check_numbers(everything, allowed)
        if bad:
            raise ValueError(f"pantalla {n} usa cifras que no están en el plan: {bad}")
        visual = ({"type": "number", "value": str(number["value"]), "label": str(number.get("label", ""))}
                  if number.get("value") else {"type": "none"})
        result.append({"id": f"P{n}", "type": "card", "kicker": kicker, "text": text, "detail": detail,
                       "visual": visual, "plan_sections": NARRATIVE_SECTIONS[2:]})
    return result


def plan_numbers():
    persona = (story.BASE / "cases" / story.CASE / "persona.md").read_text(encoding="utf-8")
    return allowed_numbers(story.load_plan(), persona, story.load_scenes()["fronts"])


def generate(person):
    """Genera y guarda las pantallas de una persona. Devuelve ("ai" | "fallback", nota)."""
    key = os.environ.get("TEAM_KEY", "")
    if not key:
        source, note, cards = "fallback", "sin TEAM_KEY: textos fijos", None
    else:
        try:
            reply = requests.post(
                f"{LLM_PROXY_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": MODEL, "messages": build_messages(person)},
                timeout=TIMEOUT_SECONDS,
            )
            reply.raise_for_status()
            cards = parse_scenes(reply.json()["choices"][0]["message"]["content"], plan_numbers())
            source, note = "ai", f"escrito por {MODEL}"
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            source, note, cards = "fallback", f"textos fijos ({error})", None

    def change(state):
        state["people"][person]["ai_scenes"] = cards
        state["people"][person]["ai_note"] = note
    story.update_state(change)
    print(f"[IA] {person}: {note}")           # se ve en la terminal donde corre el servidor
    return source, note
