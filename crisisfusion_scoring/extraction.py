"""Bounded bilingual prototype extraction, with source-scoped evidence.

This is deterministic development logic, not a validated emergency dispatch
protocol. Known expressions are covered; unsupported semantics require a person.
"""
import re
import unicodedata

def normal(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).lower()) if not unicodedata.combining(c)).replace("’", "'")

def matched(pattern, value):
    return bool(re.search(pattern, value, re.I))

def extract_call(text, language="en", rule_version="prototype-2026-10-17-v4.1"):
    """Small bilingual evidence extractor; unknown never means safe.

    Context is clause-local so 'I am not hurt, but my neighbor is trapped'
    does not negate the neighbor's need. Every positive/negative field carries
    the unmodified source clause; machine-generated inference is identified.
    """
    keys = ["personal_danger", "trapped", "evacuation_barrier", "help_requested",
            "human_requested", "potential_hazard", "explicit_non_emergency",
            "understanding_failed", "contradiction"]
    fields = {key: {"value": "unknown", "evidence": []} for key in keys}
    evidence, uncertainties, hazard_kinds, unexplained_clauses = [], [], [], []
    first_person_need = False
    approved_service_intent = False
    # Keep question punctuation and quotes verbatim; source matching remains auditable.
    clauses = [c.strip() for sentence in re.findall(r"[^.!?;\n]+[.!?;]?", text)
               for c in re.split(r"\b(?:but|pero|and|y)\b|,\s*(?=(?:I|we|he|she|they|someone|my\s+(?:neighbor|child|mother|father|friend)|mi\s+(?:madre|padre|hijo|hija|vecino|vecina)|estoy|no puedo)\b)", sentence, flags=re.I) if c.strip()]
    # A whitelisted topic anywhere in a transcript is insufficient. Limited
    # automation is gated on every clause consisting of recognized service or
    # offer wording. Unexplained additions require a person, even if a language
    # rule fails to recognize their exact emergency meaning.
    approved_tokens = set("i we want would like to know can could you your please tell me what when where is are the a an of for about my our this it its not no emergency urgent non nonemergency just question inquiry service information available campus hall library office opening hours parking permit trash pickup collection recycling maintenance ticket repair status thanks thank hello hi does do open close closes opening closing provide providing offer offering donate donating volunteer medical supplies blankets water food team por favor me puede puedes decir cual cuales es son el la los las de del para mi nuestro no una emergencia urgente solo pregunta consulta servicio informacion horario horarios apertura biblioteca oficina permiso estacionamiento recogida basura reciclaje mantenimiento reparacion estado gracias hola nosotros ofrecemos ofrezco donar voluntario voluntaria suministros medicos mantas agua comida equipo".split())

    def mark(key, value, quote, **context):
        item = {"field": key, "value": value, "quote": quote, **context}
        old = fields[key]["value"]
        # Preserve contradictions instead of overwriting an earlier positive.
        if old != "unknown" and old != value:
            fields["contradiction"]["value"] = True
            fields["contradiction"]["evidence"].append(item)
        if old != True or value == True:
            fields[key]["value"] = value
        fields[key]["evidence"].append(item)
        evidence.append(item)

    previous_context = None
    for quote in clauses:
        clause = normal(quote)
        historical = matched(r"\b(yesterday|last (?:week|year|night)|ago|used to|previously|ayer|anoche|semana pasada)\b", clause) and not matched(r"\b(now|currently|today|ahora|hoy|still|todavia)\b", clause)
        reported = matched(r"\b(heard|rumou?r|someone (?:said|told me)|social media|on (?:facebook|twitter)|they say|forwarded (?:message|text)|(?:message|notice|post|email|text|radio|recording|note) (?:says|said|saying|reports)|dicen|escuche|me dijeron|rumor|redes sociales|mensaje reenviado)\b", clause)
        epistemic = matched(r"\b(?:cannot|can't|couldn't|do not|don't) (?:tell|see|know|confirm)|\b(?:unsure|uncertain|not sure|maybe|perhaps|possibly|no se si|no puedo (?:ver|confirmar)|tal vez|quizas)\b", clause)
        conditional = matched(r"^(?:if|suppose|what if|in case|si alguien|si una persona)\b", clause)
        question = quote.endswith('?') and matched(r"^(?:are|is|was|were|does|did|can|could|would|what if|esta|estan)\b", clause)
        # Carry source/time across a conjunction only when no new personal subject
        # or explicit present-time assertion starts. A new sentence resets scope.
        direct_reset = matched(r"^(?:i (?:am|can't|cannot|need|see)|we (?:are|need|see)|estoy|no puedo|ahora|now)\b", clause)
        if previous_context and not direct_reset:
            reported = reported or previous_context['reported']
            historical = historical or previous_context['historical']
            epistemic = epistemic or previous_context['epistemic']
        speculative = epistemic or conditional or question
        previous_context = None if quote.endswith(('.', '!', '?', ';')) else {'reported':reported, 'historical':historical, 'epistemic':speculative}
        offering = matched(r"\b(offer(?:ing)?|provide|providing|donat(?:e|ing)|volunteer|ofrecemos|ofrezco|donar|voluntari[oa])\b", clause)
        subject = "other" if matched(r"\b(neighbou?r|friend|someone|person|child|mother|father|vecin[oa]|nino|nina|madre|padre)\b", clause) else "self_or_unspecified"
        context = {"subject": subject, "temporal": "historical" if historical else "current",
                   "provenance": "reported" if reported else "uncertain" if speculative else "direct_or_unspecified",
                   "intent": "offering" if offering else "report_or_request"}
        hazards = {
            "fire": r"\b(fire|smoke|burning|flames?|incendio|humo|fuego|llamas)\b",
            "flood": r"\b(flood(?:ing)?|rising water|water rising|inundacion|inundando|agua subiendo)\b",
            "gas": r"\b(gas leak|smell gas|gas smell|fuga de gas|olor a gas)\b",
            "power": r"\b(power outage|blackout|power is out|no power|electricity|apagon|sin luz|sin electricidad)\b",
            "violence": r"\b(gun|shooting|weapon|attack|disparos|arma|ataque)\b",
            "medical": r"\b(bleeding|unconscious|cannot breathe|can't breathe|not breathing|sangrando|inconsciente|no (?:puedo|puede|podemos|pueden) respirar|no respira|no esta respirando|ha dejado de respirar|stopped breathing|is not breathing)\b",
        }
        hazard_matches = [kind for kind, pat in hazards.items() if matched(pat, clause)]
        # A negated danger is not evidence that every part of this call is safe.
        hazard_negated = matched(r"\b(no (?:fire|smoke|flood|gas leak|hay (?:fuego|humo|incendio))|not (?:a fire|flooding)|false alarm|sin humo)\b", clause)
        if hazard_matches and not historical and not offering:
            hazard_kinds.extend(hazard_matches)
            mark("potential_hazard", not hazard_negated, quote, **context)
        trapped = matched(r"\b(trapped|stuck|atrapad[oa]s?|encerrad[oa]s?)\b", clause)
        # Ordinary delays and figurative use are not entrapment evidence.
        mundane_stuck = matched(r"\b(stuck (?:in traffic|in a traffic jam|on (?:homework|a problem)|at a red light)|traffic is stuck|atasco|atascad[oa] en el trafico)\b", clause)
        trapped = trapped and not mundane_stuck
        if matched(r"\b(pinned (?:my |his |her |their )?(?:legs|arms|body)|pinned (?:under|beneath)|(?:legs|body) (?:is |are )?pinned)\b", clause):
            trapped = True
        trapped_no = matched(r"\b(not|isn't|aren't|no (?:estoy|esta|estan|estamos))\s+(?:\w+\s+)?(?:trapped|stuck|atrapad[oa]s?|encerrad[oa]s?)\b", clause)
        negated_group = re.search(r"\b(?:not|nobody (?:is|was)|no one (?:is|was)|none of us (?:is|are))\s+(?:hurt|injured|trapped|bleeding|unconscious)(?:\s+or\s+(?:hurt|injured|trapped|bleeding|unconscious))*", clause)
        if negated_group and matched(r"\btrapped\b", negated_group.group()):
            trapped_no = True
        barrier = matched(r"\b(can(?:not|'t) (?:get out|leave|evacuate|escape)|unable to (?:leave|evacuate|escape)|cannot use (?:the )?stairs|can't use (?:the )?stairs|exit (?:is )?blocked|blocked exit|cannot walk|can't walk|no (?:puedo|puede|podemos|pueden) (?:salir|evacuar|caminar)|cannot reach (?:the )?exit|can't reach (?:the )?exit|salida bloqueada)\b", clause)
        # Functional evacuation obstruction, not disability identity, is evidence.
        barrier = barrier or matched(r"\b(?:wheelchair|walker) (?:can(?:not|'t)|does(?: not|n't)) (?:fit|pass)(?: through)? (?:the )?(?:only )?exit\b|\bexit (?:is )?too narrow for (?:my |a |the )?(?:wheelchair|walker)\b", clause)
        danger = matched(r"\b(can(?:not|'t) breathe|not breathing|unconscious|bleeding|injured|hurt|in danger|immediate danger|inconsciente|sangrando|herid[oa]|lesionad[oa]|no (?:puedo|puede|podemos|pueden) respirar|no respira|no esta respirando|ha dejado de respirar|stopped breathing|(?:broke|broken) (?:my |his |her |their )?(?:leg|arm)|en peligro)\b", clause)
        danger = danger and not matched(r"\b(hurt (?:my |your |his |her )?feelings|hurt emotionally|broken heart)\b", clause)
        danger_no = matched(r"\b(not (?:hurt|injured|bleeding|in danger|unconscious)|no (?:one (?:is )?(?:hurt|injured)|injuries|estoy (?:herid[oa]|en peligro))|uninjured)\b", clause)
        danger_no = danger_no or bool(negated_group and matched(r"\b(?:hurt|injured|bleeding|unconscious)\b", negated_group.group())) or matched(r"^neither\b.{0,80}\bnor\b.{0,40}\b(?:is|are|am) (?:hurt|injured|bleeding|unconscious)\b", clause)
        requested = matched(r"\b(help me|need (?:help|assistance|rescue)|please help|ayuda|ayud[ae]me|necesito (?:ayuda|rescate)|necesitamos ayuda)\b", clause)
        human = matched(r"\b(human|operator|person please|speak to (?:a |someone)|talk to (?:a |someone)|agente|operador|persona real)\b", clause)
        if human and not offering:
            mark("human_requested", True, quote, **context)
        if not historical and not offering:
            if trapped:
                mark("trapped", "unknown" if speculative else not trapped_no, quote, **context)
            if barrier:
                mark("evacuation_barrier", "unknown" if speculative else True, quote, **context)
            if danger:
                mark("personal_danger", "unknown" if speculative else not danger_no, quote, **context)
            if requested:
                mark("help_requested", True, quote, **context)
            if (danger and not danger_no or trapped and not trapped_no or barrier) and not reported and not speculative:
                first_person_need = True
        if speculative and (hazard_matches or trapped or danger or barrier):
            mark("understanding_failed", True, quote, **context)
            uncertainties.append("Danger wording is uncertain, conditional, or a question; a human must verify what is currently occurring.")
        if reported and (hazard_matches or trapped or danger or requested):
            uncertainties.append("Reported information requires verification; it is not independent confirmation.")
        if historical:
            uncertainties.append("Historical statement retained separately from current danger.")
        explicit_routine = matched(r"\b(non[- ]emergency|not an emergency|no emergency|no es una emergencia|not urgent|no es urgente|everyone (?:is )?safe)\b", clause)
        safe_context = matched(r"^(?:(?:nobody|no one|none of us) (?:is|are) (?:hurt|injured|trapped)|i am not (?:hurt|injured|trapped)(?: or (?:hurt|injured|trapped))*|(?:i am|we are|everyone is) safe|there is no (?:fire|smoke|danger)|no danger now)[.!]?$", clause)
        whitelist = matched(r"\b(opening hours|office hours|library hours|(?:when|what time) (?:does|is) (?:the )?(?:library|office) (?:open|close)|parking permit|trash (?:pickup|collection)|recycling|maintenance ticket|repair status|service status|horario|permiso de estacionamiento|recogida de basura|biblioteca)\b", clause)
        approved_service_intent = approved_service_intent or whitelist or offering
        if explicit_routine or whitelist or offering or safe_context:
            mark("explicit_non_emergency", True, quote, **context)
        clause_tokens = set(re.findall(r"[a-z]+", clause))
        if not safe_context and (not clause_tokens.issubset(approved_tokens) or not (explicit_routine or whitelist or offering or clause_tokens.issubset({"thank", "you", "thanks", "hello", "hi", "gracias", "hola", "please", "por", "favor"}))):
            unexplained_clauses.append(quote)
        if matched(r"\b(inaudible|unintelligible|unclear|asr error|cannot understand|can't understand|no entiendo|incomprensible)\b|\[noise\]|\?{2,}", clause):
            mark("understanding_failed", True, quote, **context)
    if language not in {"en", "es", "mixed"} or not clauses:
        mark("understanding_failed", True, text or "[empty transcript]", subject="unknown", temporal="unknown", provenance="unknown", intent="unknown")
        uncertainties.append("Language or content is not supported by the local extractor.")
    value = lambda name: fields[name]["value"] is True
    if first_person_need:
        triage = "IMMEDIATE_HUMAN"
        reasons = ["Current explicit danger, entrapment, or evacuation barrier requires a human now."]
    elif value("potential_hazard") or value("contradiction") or value("help_requested") or (value("understanding_failed") and not value("explicit_non_emergency")):
        triage = "HUMAN_VERIFY"
        reasons = ["Potential danger, a help request, or conflicting evidence requires verification."]
    elif value("human_requested"):
        triage = "ROUTINE_HUMAN"
        reasons = ["The caller explicitly requested a person."]
    elif value("understanding_failed"):
        # Ordinary service ambiguity differs from possible emergency ambiguity.
        triage = "ROUTINE_HUMAN" if value("explicit_non_emergency") else "HUMAN_VERIFY"
        reasons = ["Content could not be understood reliably; a person must clarify."]
    elif value("explicit_non_emergency") and approved_service_intent and not unexplained_clauses:
        triage = "AUTOMATION_ELIGIBLE"
        reasons = ["Explicit non-emergency service request or offer; only a limited approved response is eligible."]
    else:
        triage = "HUMAN_VERIFY"
        reasons = ["Insufficient evidence for safe limited automation."]
    if unexplained_clauses and value("explicit_non_emergency") and triage == "HUMAN_VERIFY":
        uncertainties.append("A routine topic was recognized, but additional content is outside the complete-transcript automation whitelist.")
    if first_person_need or value("help_requested"):
        need_types = ["personal_assistance"]
    elif value("potential_hazard") or value("contradiction"):
        need_types = ["report_verification"]
    elif value("human_requested"):
        need_types = ["human_request"]
    elif triage == "AUTOMATION_ELIGIBLE":
        need_types = ["routine_service"]
    else:
        need_types = ["clarification"]
    question = ("Are you or anyone nearby in danger right now, and where are you?" if triage == "HUMAN_VERIFY"
                else "What location should the human operator use, if you can safely share it?" if triage == "IMMEDIATE_HUMAN"
                else "What would you like the operator to help with?" if triage == "ROUTINE_HUMAN" else None)
    if language == "es" and question:
        question = "¿Usted u otra persona está en peligro ahora? ¿Dónde se encuentra?" if triage in {"IMMEDIATE_HUMAN", "HUMAN_VERIFY"} else "¿En qué puede ayudarle el operador?"
    reply = "Your routine request has been recorded. A campus service operator can confirm hours, availability, or ticket status; this prototype does not have live service information." if triage == "AUTOMATION_ELIGIBLE" else None
    if not evidence:
        evidence.append({"field": "unclassified_content", "value": "unknown", "quote": text,
                         "subject": "unknown", "temporal": "unknown", "provenance": "unknown",
                         "intent": "unknown", "explanation": "Original input retained because the local extractor could not establish an approved interpretation."})
    return {"fields": fields, "triage_status": triage, "reasons": reasons,
            "uncertainties": list(dict.fromkeys(uncertainties)),
            "hazard_kind": hazard_kinds[0] if hazard_kinds else "service" if value("explicit_non_emergency") else "other",
            "need_types": need_types, "evidence": evidence,
            "rule_version": rule_version, "extractor": "local_bilingual_rules",
            "clarifying_question": question, "automation_reply": reply}

