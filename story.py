"""Lógica de la app: un plan, dos recorridos.

Aquí vive todo lo que no es pintar pantallas: qué ve cada persona, cómo se
comparan los dos órdenes, cuál es el primer paso y qué va al resumen del asesor.

Las notas NO están escritas a mano: se leen del plan (cases/<caso>/financial-health.json).
"""
import json
import threading
from pathlib import Path

BASE = Path(__file__).parent
CASE = "timothy-melanie-weah"
STATE_FILE = BASE / "data" / "state.json"
_lock = threading.Lock()


# ---------- Datos: guion y plan ----------

def load_scenes():
    """El guion: textos, frentes y tareas. Se edita en scenes/<caso>.json."""
    return json.loads((BASE / "scenes" / f"{CASE}.json").read_text(encoding="utf-8"))


def load_plan():
    """El plan de Sherpas tal cual viene en el repo del hackathon."""
    return json.loads((BASE / "cases" / CASE / "financial-health.json").read_text(encoding="utf-8"))


def fronts_by_id():
    return {f["id"]: f for f in load_scenes()["fronts"]}


def lower_first(text):
    """'La tarjeta' -> 'la tarjeta', para usar el título dentro de una frase."""
    return text[0].lower() + text[1:]


# ---------- Estado: lo que ha hecho cada persona ----------

def _empty_person():
    return {"worry": None, "worry_text": "", "order": [], "seen": [], "details": [],
            "questions": [], "ai_scenes": None, "ai_note": ""}


def _empty_state():
    people = load_scenes()["people"]
    return {"people": {p: _empty_person() for p in people},
            "household": {"done": {}, "blockers": {}, "reminder": None}}


def read_state():
    if not STATE_FILE.exists():
        return _empty_state()
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def update_state(change):
    """Lee el estado, aplica la función `change(state)` y lo guarda."""
    with _lock:
        state = read_state()
        change(state)
        STATE_FILE.parent.mkdir(exist_ok=True)
        # Se escribe en un archivo temporal y se cambia de golpe, para que nadie lea el archivo a medias.
        temp = STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(STATE_FILE)
        return state


def reset_state():
    with _lock:
        if STATE_FILE.exists():
            STATE_FILE.unlink()


def partner_of(person):
    scenes = load_scenes()
    partner = scenes["people"][person]["partner"]
    return partner, scenes["people"][partner]["name"]


# ---------- Notas: siempre desde el plan ----------

def score_for(front_ids):
    """Nota del plan si se hacen esos frentes, p. ej. {"card", "life"}.

    Los frentes sin movimiento en el plan (la universidad) no cambian la nota.
    """
    score = load_plan()["score"]
    fronts = fronts_by_id()
    moves = {fronts[f]["move"] for f in front_ids if fronts[f].get("move")}
    if not moves:
        return score["published_score"]
    if len(moves) == 1:
        title = next(iter(moves))
        for move in score["top_moves"]:
            if move["title"] == title:
                return move["score_after"]
    for combo in score["combined_moves"]:
        if set(combo["moves"]) == moves:
            return combo["score_after"]
    raise ValueError(f"El plan no trae nota para esta combinación: {sorted(moves)}")


def best_partner(front_id):
    """El otro frente que, junto con este, deja la nota más alta."""
    fronts = fronts_by_id()
    others = [f for f in fronts if f != front_id and fronts[f].get("move")]
    best = max(others, key=lambda other: score_for({front_id, other}))
    return best, score_for({front_id, best})


# ---------- La historia de cada persona ----------

def personal_scenes(person):
    """Las tres pantallas personales: las que escribió la IA, o las fijas de reserva."""
    scenes = load_scenes()
    me = read_state()["people"][person]
    cards = me["ai_scenes"] or scenes["personal"][person]
    return [{**card, "intro": scenes["personal_intro"]} if n == 0 else card for n, card in enumerate(cards)]


def build_story(person, day=0):
    """Lista de pantallas, en orden, para una persona. `day` son los días que han pasado."""
    scenes = load_scenes()
    if day > 0:
        story = list(scenes["later"]["dated"]) if day >= 30 else []
        story.append({"id": "L1", "type": "checkin", "dynamic": True})
        story.append({"id": "L2", "type": "step", "dynamic": True, "which": 1})
        return story

    rank = {**scenes["rank"], "fronts": [{"id": f["id"], "title": f["title"], "fact": f["fact"]}
                                         for f in scenes["fronts"]]}
    return ([{"id": "I0", "type": "intro", "dynamic": True}, scenes["question"]]
            + personal_scenes(person)
            + [rank,
               {"id": "E1", "type": "encounter", "dynamic": True},
               {"id": "E2", "type": "step", "dynamic": True, "which": 0}])


def intro(person):
    """Primera pantalla: el gancho es el encuentro con la pareja."""
    scenes = load_scenes()
    partner, partner_name = partner_of(person)
    partner_ready = bool(read_state()["people"][partner]["order"])
    text = scenes["intro"]["second" if partner_ready else "first"].format(partner=partner_name)
    return {"kicker": scenes["intro"]["kicker"], "text": text, "sub": scenes["intro"]["sub"]}


# ---------- El encuentro ----------

def both_ranked():
    return all(p["order"] for p in read_state()["people"].values())


def joint_order():
    """Orden conjunto: suma las posiciones de los dos. En empate, manda el orden del guion."""
    scenes = load_scenes()
    orders = [p["order"] for p in read_state()["people"].values()]
    priority = scenes["front_priority"]
    return sorted(priority, key=lambda f: (sum(order.index(f) for order in orders), priority.index(f)))


def insight(first_a, first_b):
    """Qué dice el plan sobre lo que cada uno ha puesto primero."""
    fronts = fronts_by_id()
    base = score_for(set())
    name = lambda f: lower_first(fronts[f]["title"])

    if first_a == first_b:
        front = fronts[first_a]
        if not front.get("move"):
            return front["no_score_note"]
        alone = score_for({first_a})
        other, together = best_partner(first_a)
        if alone > base:
            return (f"Solo con eso, la nota de vuestro plan pasa de {base} a {alone}. "
                    f"Y junto con {name(other)}, llega a {together}.")
        return (f"Con eso solo, la nota de vuestro plan sigue en {base}. "
                f"Junto con {name(other)}, sube a {together}.")

    movable = [f for f in (first_a, first_b) if fronts[f].get("move")]
    if len(movable) == 2:
        a, b, both = score_for({first_a}), score_for({first_b}), score_for({first_a, first_b})
        if both > max(a, b):
            return (f"Y no tenéis que elegir. Con solo {name(first_a)}, la nota de vuestro plan queda en {a}; "
                    f"con solo {name(first_b)}, en {b}. Con las dos cosas, sube de {base} a {both}.")
        # Juntas no suman más: se enseña qué otro frente sí movería la nota.
        front = max((first_a, first_b), key=lambda f: best_partner(f)[1])
        other, together = best_partner(front)
        return (f"Con solo {name(first_a)}, la nota de vuestro plan queda en {a}; "
                f"con solo {name(first_b)}, en {b}; con las dos cosas, en {both}. "
                f"Añadiendo {name(other)} a {name(front)}, sube a {together}.")
    notes = [fronts[f]["no_score_note"] for f in (first_a, first_b) if not fronts[f].get("move")]
    if movable:
        notes.append(f"Con {name(movable[0])}, la nota de vuestro plan queda en {score_for({movable[0]})}.")
    return " ".join(notes)


def encounter(person):
    """La pantalla central: espera al otro, o descubre los dos órdenes."""
    state = read_state()
    partner, partner_name = partner_of(person)
    if not both_ranked():
        return {"waiting": True, "partner": partner, "partner_name": partner_name,
                "text": f"Tu orden está guardado. Falta {partner_name}."}

    fronts = fronts_by_id()
    mine, theirs = state["people"][person]["order"], state["people"][partner]["order"]
    rows = [{"position": n + 1, "mine": fronts[a]["title"], "theirs": fronts[b]["title"], "match": a == b}
            for n, (a, b) in enumerate(zip(mine, theirs))]
    if mine[0] == theirs[0]:
        text = f"Los dos habéis puesto primero {lower_first(fronts[mine[0]]['title'])}."
    else:
        text = (f"No habéis puesto lo mismo primero. Tú, {lower_first(fronts[mine[0]]['title'])}. "
                f"{partner_name}, {lower_first(fronts[theirs[0]]['title'])}.")
    return {"waiting": False, "partner_name": partner_name, "text": text, "rows": rows,
            "matches": sum(r["match"] for r in rows), "insight": insight(mine[0], theirs[0])}


def step(person, which=0):
    """Ficha de un paso: qué hacer, la parte de cada uno, cuánto cuesta y qué preguntar."""
    partner, partner_name = partner_of(person)
    if not both_ranked():
        return {"waiting": True, "partner": partner, "partner_name": partner_name,
                "text": f"Vuestro primer paso sale cuando {partner_name} ordene lo suyo."}
    fronts = fronts_by_id()
    order = joint_order()
    front = fronts[order[which]]
    following = fronts[order[which + 1]]["title"] if which + 1 < len(order) else None
    return {
        "waiting": False,
        "kicker": "Vuestro primer paso" if which == 0 else "Lo siguiente",
        "title": front["title"],
        "do": front["do"],
        "my_task": front["tasks"][person],
        "partner_task": front["tasks"][partner],
        "partner_name": partner_name,
        "cost": front["cost"],
        "ask": front["ask"],
        "detail": front["detail"],
        "following": following,
        "with_date": which == 0,
        "reminder": read_state()["household"]["reminder"],
    }


# ---------- Cuando vuelven otro día ----------

def checkin(person):
    """¿Has hecho tu parte? Y qué ha hecho el otro."""
    scenes = load_scenes()
    state = read_state()
    partner, partner_name = partner_of(person)
    if not both_ranked():
        return {"ready": False, "text": f"Todavía no hay primer paso: falta que {partner_name} y tú ordenéis lo vuestro."}

    fronts = fronts_by_id()
    front_id = joint_order()[0]
    front = fronts[front_id]
    done = state["household"]["done"]
    mine, theirs = done.get(person), done.get(partner)
    partner_line = {True: f"{partner_name} ya ha hecho su parte.",
                    False: f"{partner_name} todavía no ha hecho su parte.",
                    None: f"{partner_name} aún no ha contestado."}[theirs]

    message = None
    if mine and theirs:
        message = "Hecho entre los dos."
        if front.get("move"):
            base, after = score_for(set()), score_for({front_id})
            if after > base:
                message += f" Cuando vuestro asesor actualice el plan, la nota pasa de {base} a {after}."
            else:
                other, together = best_partner(front_id)
                message += (f" La nota aún no se mueve: falta {lower_first(fronts[other]['title'])}. "
                            f"Con las dos cosas, sube a {together}.")
    elif mine:
        message = f"Tu parte está hecha. Falta la de {partner_name}."
    elif mine is False and state["household"]["blockers"].get(person):
        message = scenes["later"]["blocker_thanks"]

    return {"ready": True, "title": front["title"], "text": "¿Has hecho tu parte?", "task": front["tasks"][person],
            "partner_line": partner_line, "answered": mine, "message": message,
            "blockers": scenes["later"]["blockers"]}


# ---------- Resumen para el asesor ----------

def advisor_summary():
    scenes = load_scenes()
    state = read_state()
    fronts = fronts_by_id()
    worries = {o["id"]: o["text"] for o in scenes["question"]["options"]}
    blockers = {b["id"]: b["text"] for b in scenes["later"]["blockers"]}

    people = []
    for pid, info in scenes["people"].items():
        p = state["people"][pid]
        cards = (p["ai_scenes"] or []) + scenes["personal"][pid]
        titles = {c["id"]: c["kicker"] for c in cards} | {f["id"]: f["title"] for f in scenes["fronts"]}
        people.append({
            "name": info["name"],
            "worry": worries.get(p["worry"]),
            "worry_text": p["worry_text"],
            "order": [fronts[f]["title"] for f in p["order"]],
            "seen": len(p["seen"]),
            "details": [titles.get(s, s) for s in p["details"]],
            "questions": p["questions"],
            "done": state["household"]["done"].get(pid),
            "blocker": blockers.get(state["household"]["blockers"].get(pid)),
            "written_by": "IA" if p["ai_scenes"] else "texto fijo",
        })

    ready = both_ranked()
    first = fronts[joint_order()[0]] if ready else None
    rows = []
    if ready:
        orders = [p["order"] for p in people]
        rows = [{"position": n + 1, "cells": list(cells), "match": len(set(cells)) == 1}
                for n, cells in enumerate(zip(*orders))]
    return {
        "family": scenes["family"],
        "people": people,
        "ready": ready,
        "rows": rows,
        "first": first,
        "score": {"before": score_for(set()), "after": score_for({first["id"]}) if first else None},
        "reminder": state["household"]["reminder"],
    }
