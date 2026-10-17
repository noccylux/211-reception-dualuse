"""Sample caller utterances for the demo board. All written by the team; none is a
real call. The UI shows the origin next to every sample."""

ORIGIN = "written by the team for the demo (simulated caller)"

SAMPLES = [
    {"text": "My house is on fire and my kid is inside.", "origin": ORIGIN, "expected": "immediate"},
    {
        "text": "My neighbor collapsed on the sidewalk and he is not breathing, there is smoke everywhere on Lake Avenue.",
        "origin": ORIGIN,
        "expected": "immediate",
    },
    {
        "text": "We evacuated from Altadena last night and have nowhere to sleep tonight, two kids with us.",
        "origin": ORIGIN,
        "expected": "priority",
    },
    {
        "text": "My mother's oxygen concentrator stopped when the power went out in Pasadena; the tank lasts two more hours.",
        "origin": ORIGIN,
        "expected": "priority",
    },
    {"text": "Is the 210 freeway open towards Pasadena?", "origin": ORIGIN, "expected": "normal"},
    {"text": "I want to ask about FEMA assistance for my damaged roof.", "origin": ORIGIN, "expected": "normal"},
    {
        "text": "Where can I renew my CalFresh card? It expired last week.",
        "origin": ORIGIN,
        "expected": "normal (an ordinary Tuesday call)",
    },
    {"text": "Hello? Is anyone there?", "origin": ORIGIN, "expected": "unknown"},
    {
        "text": "Mi casa se está quemando y mi hijo está adentro.",
        "origin": ORIGIN,
        "expected": "immediate (Spanish; the keyword rules miss it, the model should not)",
    },
    {
        "text": "我们从阿尔塔迪纳撤离了，今晚没有地方住，还带着两个孩子。",
        "origin": ORIGIN,
        "expected": "priority (Chinese; the keyword rules miss it, the model should not)",
    },
]
