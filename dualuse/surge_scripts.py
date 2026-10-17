"""Team-written caller scripts for the live surge demo. Simulated callers, not recordings.

Each script is one caller: the first line opens the conversation and later lines are sent
after the assistant replies. Mix: routine requests, urgent needs and life threats in
English, Spanish and Mandarin, so the queue shows reordering and multilingual intake.
"""

SCRIPTS = (
    ("Is the 210 freeway open towards Pasadena?",),
    ("I want to ask about FEMA assistance for my damaged roof.", "We are staying with family. Nobody is hurt."),
    ("Where can I renew my CalFresh card? It expired last week.",),
    ("We evacuated from Altadena last night and have nowhere to sleep tonight.",
     "Two kids and my mother. We are in the parking lot of the Pasadena Convention Center."),
    ("My insulin is running low and the pharmacy near me burned down.", "I have maybe one day left."),
    ("I see smoke coming from the apartment next door.", "It is 450 Maple Ave. I can hear a baby crying inside."),
    ("My neighbor collapsed on the sidewalk and he is not breathing.",),
    ("Hello? Is anyone there?",),
    ("Mi mamá necesita oxígeno y se fue la luz hace dos horas.", "Estamos en Lake Avenue, en Altadena."),
    ("¿Dónde puedo pedir ayuda para pagar la renta? Perdí mi trabajo por el incendio.",),
    ("Hay humo en el pasillo de mi edificio y no podemos salir.", "Somos cuatro personas, en el tercer piso."),
    ("我们从阿尔塔迪纳撤离了，今晚没有地方住，还带着两个孩子。",),
    ("我爸爸八十岁了，行动不便，家里停电了，冰箱里的药要坏了。", "我们在帕萨迪纳的科罗拉多大道。"),
    ("请问哪里可以领取免费的饮用水？",),
)
