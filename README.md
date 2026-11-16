# Un plan, dos recorridos

Un plan financiero lo recibe una pareja, pero cada uno lo lee por su lado y nada pasa hasta que se ponen de acuerdo.
Esta app le cuenta el plan a cada uno a su manera, les hace decidir por separado qué va primero,
y les enseña dónde coinciden y cuál es su primer paso.

Hackathon Sherpas x UPV Sigma Data Club, noviembre de 2026. (Nombre provisional.)

## Cómo funciona

1. **¿Coincidiréis?** Desde la primera pantalla, el gancho es el encuentro con la pareja.
2. **Qué te preocupa.** Cada uno lo responde por separado. El plan no lo sabe: nadie se lo había preguntado.
3. **Tres cosas que tienes que saber**, un dato por pantalla, escritas por la IA con los datos de esa persona.
4. **¿Qué va primero?** Cada uno ordena los cuatro frentes abiertos del plan.
5. **El encuentro.** Los dos órdenes lado a lado, lo que dice el plan sobre ellos, y un primer paso
   con una parte para cada uno: qué hacer, cuánto cuesta si el plan lo sabe, y qué preguntar al asesor.
6. **Otro día.** ¿Has hecho tu parte? Qué ha hecho el otro y qué toca ahora.
7. **Resumen para el asesor.** Qué preocupa a cada uno, qué pondría primero y dónde no coinciden.

## Cómo arrancarlo

Hace falta Python 3.10 o posterior.

```bash
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000. Para verlo en el móvil, conéctalo a la misma wifi y abre `http://<IP de tu ordenador>:5000`.

Para usar la IA, copia `.env.example` como `.env` y rellena `TEAM_KEY`.
Sin clave la app funciona igual, con los textos fijos del guion.

## Cómo probarlo en dos minutos

1. Entra como **Timothy**, responde y ordena tus prioridades. Te dirá que falta Melanie.
2. Vuelve al inicio y entra como **Melanie**. Al ordenar verás el encuentro y el primer paso.
3. Abre **Resumen del asesor** desde el inicio.
4. En el inicio, elige **3 días después** antes de entrar, para ver qué pasa cuando vuelven.
5. **Reiniciar la demo** borra todo.

## Qué hay en cada archivo

| Archivo | Qué hace |
|---|---|
| `scenes/timothy-melanie-weah.json` | El guion: los cuatro frentes, las tareas de cada uno y los textos fijos de reserva |
| `story.py` | La lógica: qué ve cada uno, el encuentro, el orden conjunto, el primer paso, el resumen del asesor |
| `ai.py` | La IA: qué se le envía al modelo, y la comprobación de que no inventa cifras |
| `app.py` | El servidor: recibe las peticiones del navegador y llama a `story.py` y `ai.py` |
| `probar_ia.py` | Para probar la IA desde la terminal y comparar modelos |
| `static/app.js` | Pinta las pantallas. No decide nada |
| `static/style.css` | Colores, tipografía y animaciones. Las variables del principio cambian todo el aspecto |
| `templates/advisor.html` | La página del resumen para el asesor |
| `cases/` | Los planes de Sherpas, tal cual vienen en el repo del hackathon |
| `data/state.json` | Lo que ha hecho cada persona. Se crea solo y no se sube a GitHub |

## Cómo usamos la IA, y cómo evitamos que invente

- Al responder qué le preocupa, el servidor envía al modelo el plan de la familia y los datos de esa persona,
  y le pide tres pantallas. Es una llamada por persona.
- **Cada cifra que escribe el modelo se comprueba contra el plan.** Si aparece una que no está, se descarta la respuesta.
- Si el modelo falla, tarda demasiado o no hay clave, se usan los textos fijos. La app nunca se queda en blanco.
- Las notas (60, 62, 73, 78) no pasan por el modelo: se leen de `score.top_moves` y `score.combined_moves` del plan.
- Las dudas se responden solo con el plan. Si el plan no lo calcula (el precio de un seguro), se apunta para el asesor.

Para probar la IA sin abrir la app: `python probar_ia.py timothy card`.

## Para quién está diseñado

Para parejas. Con una persona sola, el encuentro sería con el propio plan: su orden frente a lo que más mueve su nota.

## Añadir otra familia

1. Crear `scenes/<caso>.json` con la misma estructura que el de los Weah.
2. En cada frente, `move` tiene que ser el título exacto de un movimiento de `score.top_moves` de esa familia.
3. Cambiar `CASE` al principio de `story.py`.
