"""Prueba la IA desde la terminal, sin abrir la app.

Uso:
    python probar_ia.py                    -> Timothy, preocupado por la tarjeta, con gpt-5-mini
    python probar_ia.py melanie kids       -> Melanie, preocupada por los niños
    python probar_ia.py timothy card deepseek-flash    -> otro modelo, para comparar

Enseña lo que tarda, lo que escribe el modelo y si pasa la comprobación de cifras.
"""
import json
import os
import sys
import time

import requests

import ai
import story

person = sys.argv[1] if len(sys.argv) > 1 else "timothy"
worry = sys.argv[2] if len(sys.argv) > 2 else "card"
model = sys.argv[3] if len(sys.argv) > 3 else ai.MODEL

if not os.environ.get("TEAM_KEY"):
    sys.exit("Falta TEAM_KEY en el archivo .env")

story.update_state(lambda state: state["people"][person].update({"worry": worry, "worry_text": ""}))
messages = ai.build_messages(person)
print(f"Persona: {person} · preocupación: {worry} · modelo: {model}")
print(f"Se envían {len(messages[0]['content']) + len(messages[1]['content'])} caracteres. Esperando respuesta...")

start = time.time()
reply = requests.post(
    f"{ai.LLM_PROXY_URL}/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['TEAM_KEY']}"},
    json={"model": model, "messages": messages},
    timeout=120,
)
print(f"Respuesta en {time.time() - start:.1f} segundos (código {reply.status_code})")
reply.raise_for_status()
body = reply.json()
text = body["choices"][0]["message"]["content"]
print("Uso de tokens:", body.get("usage"))
print("\n--- Lo que ha escrito el modelo ---\n" + text)

try:
    cards = ai.parse_scenes(text, ai.plan_numbers())
    print("\n--- CORRECTO: pasa la comprobación. Así se verían las pantallas ---")
    for card in cards:
        print(f"\n[{card['kicker']}]\n{card['text']}\n  números: {card['detail']}")
except ValueError as error:
    print(f"\n--- RECHAZADO: {error} ---\nLa app usaría los textos fijos del guion.")
