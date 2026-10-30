"""Explicit, conservative language cue packs for draft invariant suggestions.

These rules are prompts for human curation, not natural-language understanding.
The profiles are intentionally small and versioned with the source code so their
false positives and false negatives can be measured against labelled fixtures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class InvariantLanguageProfile:
    language: str
    cue: re.Pattern[str]
    negation: re.Pattern[str]
    mandatory: re.Pattern[str]
    conditional: re.Pattern[str]
    numeric_limit: re.Pattern[str]
    action: re.Pattern[str]
    target_negation_markers: tuple[str, ...]
    target_mandatory_markers: tuple[str, ...]


def _profile(
    language: str,
    *,
    negation: str,
    mandatory: str,
    conditional: str,
    numeric_limit: str,
    action: str,
    target_negation: tuple[str, ...],
    target_mandatory: tuple[str, ...],
) -> InvariantLanguageProfile:
    flags = re.IGNORECASE | re.UNICODE
    patterns = [re.compile(value, flags) for value in (
        negation, mandatory, conditional, numeric_limit, action,
    )]
    cue = re.compile(
        "|".join(f"(?:{pattern.pattern})" for pattern in patterns) + r"|\d",
        flags,
    )
    return InvariantLanguageProfile(
        language=language, cue=cue, negation=patterns[0], mandatory=patterns[1],
        conditional=patterns[2], numeric_limit=patterns[3], action=patterns[4],
        target_negation_markers=target_negation,
        target_mandatory_markers=target_mandatory,
    )


PROFILES: dict[str, InvariantLanguageProfile] = {
    "en": _profile(
        "en",
        negation=r"\b(?:not|never|without|mustn't|don't|doesn't|cannot|can't|no(?!\s+(?:more than|less than|greater than)))\b",
        mandatory=r"\b(?:must|required|shall|mandatory|is required to)\b",
        conditional=r"\b(?:only if|unless|before|after|if|provided that)\b",
        numeric_limit=r"\b(?:at least|at most|no more than|no less than|up to|maximum|minimum|max(?:imum)?|min(?:imum)?|limit(?:ed)?|exactly|within|less than|greater than|more than)\b",
        action=r"\b(?:use|set|keep|allow|wait|retry|run|limit|retain|provide|send|store|accept|reject|include|exclude|process|create|delete|remove|preserve|avoid|require|ensure|configure|return|stop|continue|call|execute|install|open|close)\b",
        target_negation=("not", "never", "without", "cannot", "can't", "mustn't", "don't"),
        target_mandatory=("must", "shall", "required", "mandatory"),
    ),
    "fr": _profile(
        "fr",
        negation=r"\b(?:jamais|aucun(?:e|s|es)?|sans|pas(?!\s+plus\s+de)|ne\s+\w+(?:\s+\w+)?\s+pas|n['’]\w+\s+pas)\b",
        mandatory=r"\b(?:doit|doivent|devez|devra|devront|obligatoire|il\s+faut|tenu\s+de|tenus\s+de)\b",
        conditional=r"\b(?:uniquement\s+si|seulement\s+si|sauf\s+si|à\s+condition\s+que|avant|après|si)\b",
        numeric_limit=r"\b(?:au\s+moins|au\s+plus|pas\s+plus\s+de|pas\s+moins\s+de|maximum|minimum|limite|exactement|dans\s+un\s+délai\s+de|moins\s+de|plus\s+de)\b",
        action=r"\b(?:utiliser|utilisez|utilise|conserver|conservez|préserver|préservez|envoyer|envoyez|stocker|stockez|accepter|rejeter|exécuter|exécutez|supprimer|supprimez|éviter|évitez|configurer|configurez|attendre|attendez|réessayer|réessayez|inclure|exclure|créer|créez|retourner|arrêter|appeler|ouvrir|fermer)\b",
        target_negation=("ne pas", "pas", "jamais", "aucun", "aucune", "sans"),
        target_mandatory=("doit", "doivent", "obligatoire", "il faut"),
    ),
    "es": _profile(
        "es",
        negation=r"\b(?:nunca|sin|ning[uú]n(?:a|os|as)?|no(?!\s+m[áa]s\s+de))\b",
        mandatory=r"\b(?:debe|deben|deberá|deberán|obligatorio|es\s+necesario\s+que)\b",
        conditional=r"\b(?:solo\s+si|solamente\s+si|a\s+menos\s+que|antes|después|si|siempre\s+que)\b",
        numeric_limit=r"\b(?:al\s+menos|como\s+m[áa]ximo|no\s+m[áa]s\s+de|no\s+menos\s+de|hasta|m[áa]ximo|m[íi]nimo|l[íi]mite|exactamente|menos\s+de|m[áa]s\s+de)\b",
        action=r"\b(?:usar|usa|use|utilizar|utilice|conservar|conserve|preservar|preserve|enviar|envíe|almacenar|almacene|aceptar|rechazar|ejecutar|ejecute|eliminar|elimine|evitar|evite|configurar|configure|esperar|espere|reintentar|incluya|excluir|crear|detener|llamar|abrir|cerrar)\b",
        target_negation=("no", "nunca", "sin", "ningún", "ninguna", "ninguno"),
        target_mandatory=("debe", "deben", "obligatorio", "es necesario"),
    ),
    "de": _profile(
        "de",
        negation=r"\b(?:niemals|kein(?:e|en|em|er|es)?|ohne|nicht(?!\s+mehr\s+als))\b",
        mandatory=r"\b(?:muss|müssen|verpflichtend|erforderlich|ist\s+verpflichtet)\b",
        conditional=r"\b(?:nur\s+wenn|es\s+sei\s+denn|bevor|nachdem|nach|vor|wenn|falls)\b",
        numeric_limit=r"\b(?:mindestens|höchstens|nicht\s+mehr\s+als|nicht\s+weniger\s+als|bis\s+zu|maximal|minimal|grenze|genau|innerhalb|weniger\s+als|mehr\s+als)\b",
        action=r"\b(?:verwenden|verwende|nutzen|nutze|behalten|bewahren|senden|speichern|akzeptieren|ablehnen|ausführen|löschen|entfernen|vermeiden|konfigurieren|warten|wiederholen|einschließen|ausschließen|erstellen|stoppen|aufrufen|öffnen|schließen|ausgeben)\b",
        target_negation=("nicht", "niemals", "kein", "keine", "ohne"),
        target_mandatory=("muss", "müssen", "verpflichtend", "erforderlich"),
    ),
    "pt": _profile(
        "pt",
        negation=r"\b(?:nunca|nenhum(?:a|s|as)?|sem|não(?!\s+mais\s+que))\b",
        mandatory=r"\b(?:deve|devem|deverá|deverão|obrigatório|é\s+necessário\s+que)\b",
        conditional=r"\b(?:somente\s+se|apenas\s+se|a\s+menos\s+que|antes|depois|se|desde\s+que)\b",
        numeric_limit=r"\b(?:pelo\s+menos|no\s+máximo|não\s+mais\s+que|não\s+menos\s+que|até|máximo|mínimo|limite|exatamente|dentro\s+de|menos\s+que|mais\s+que)\b",
        action=r"\b(?:usar|use|utilizar|utilize|manter|preservar|enviar|armazenar|aceitar|rejeitar|executar|execute|excluir|remover|evitar|configure|configurar|aguardar|repetir|incluir|criar|interromper|chamar|abrir|fechar)\b",
        target_negation=("não", "nunca", "sem", "nenhum", "nenhuma"),
        target_mandatory=("deve", "devem", "obrigatório", "é necessário"),
    ),
    "it": _profile(
        "it",
        negation=r"\b(?:mai|nessun(?:o|a|i|e)?|senza|non(?!\s+più\s+di))\b",
        mandatory=r"\b(?:deve|devono|dovrà|obbligatorio|è\s+necessario\s+che)\b",
        conditional=r"\b(?:solo\s+se|a\s+meno\s+che|prima|dopo|se|purché)\b",
        numeric_limit=r"\b(?:almeno|al\s+massimo|non\s+più\s+di|non\s+meno\s+di|fino\s+a|massimo|minimo|limite|esattamente|entro|meno\s+di|più\s+di)\b",
        action=r"\b(?:usare|usa|utilizzare|utilizza|mantenere|conservare|preservare|inviare|memorizzare|accettare|rifiutare|eseguire|eliminare|rimuovere|evitare|configurare|attendere|riprovare|includere|escludere|creare|interrompere|chiamare|aprire|chiudere)\b",
        target_negation=("non", "mai", "nessuno", "nessuna", "senza"),
        target_mandatory=("deve", "devono", "obbligatorio", "è necessario"),
    ),
}


@lru_cache(maxsize=64)
def language_profile(locale: str | None) -> InvariantLanguageProfile | None:
    """Return a small, explicit cue profile for the primary BCP 47 language."""
    if not locale:
        return None
    language = locale.split("-", 1)[0].lower()
    return PROFILES.get(language)


def classify_candidate(text: str, profile: InvariantLanguageProfile) -> str | None:
    """Classify one possible instruction line; unknown phrasing remains unclassified."""
    negative = bool(profile.negation.search(text))
    mandatory = bool(profile.mandatory.search(text))
    conditional = bool(profile.conditional.search(text))
    numeric_limit = bool(profile.numeric_limit.search(text))
    action = bool(profile.action.search(text))
    has_number = bool(re.search(r"\d", text))

    if negative:
        return "negation"
    if has_number and (numeric_limit or action or mandatory or conditional):
        return "numeric_limit"
    if mandatory:
        return "mandatory_condition"
    if conditional:
        return "precondition"
    if action:
        return "decision_rule"
    return None


def suggested_target_markers(
    locale: str | None, category: str,
) -> tuple[list[str], list[str]]:
    """Return draft target-language markers; caller must keep the manifest unreviewed."""
    profile = language_profile(locale)
    if profile is None:
        return [], []
    negation = list(profile.target_negation_markers) if category == "negation" else []
    mandatory = list(profile.target_mandatory_markers) if category == "mandatory_condition" else []
    return negation, mandatory
