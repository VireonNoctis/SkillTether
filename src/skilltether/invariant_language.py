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
        mandatory=r"\b(?:debe|debes|deben|deberá|deberán|obligatorio|es\s+necesario\s+que)\b",
        conditional=r"\b(?:solo\s+si|solamente\s+si|a\s+menos\s+que|antes|después|si|siempre\s+que)\b",
        numeric_limit=r"\b(?:al\s+menos|como\s+m[áa]ximo|no\s+m[áa]s\s+de|no\s+menos\s+de|hasta|m[áa]ximo|m[íi]nimo|l[íi]mite|exactamente|menos\s+de|m[áa]s\s+de)\b",
        action=r"\b(?:usar|usa|use|utilizar|utilice|conservar|conserve|preservar|preserve|enviar|envíe|almacenar|almacene|aceptar|rechazar|ejecutar|ejecute|eliminar|elimine|evitar|evite|configurar|configure|esperar|espere|reintentar|incluya|excluir|crear|detener|llamar|abrir|cerrar)\b",
        target_negation=("no", "nunca", "sin", "ningún", "ninguna", "ninguno"),
        target_mandatory=("debe", "deben", "obligatorio", "es necesario"),
    ),
    "de": _profile(
        "de",
        negation=r"\b(?:niemals|kein(?:e|en|em|er|es)?|ohne|nicht(?!\s+mehr\s+als))\b",
        mandatory=r"\b(?:muss|musst|müssen|verpflichtend|erforderlich|ist\s+verpflichtet)\b",
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
        mandatory=r"\b(?:deve|devi|devono|dovrà|obbligatorio|è\s+necessario\s+che)\b",
        conditional=r"\b(?:solo\s+se|a\s+meno\s+che|prima|dopo|se|purché)\b",
        numeric_limit=r"\b(?:almeno|al\s+massimo|non\s+più\s+di|non\s+meno\s+di|fino\s+a|massimo|minimo|limite|esattamente|entro|meno\s+di|più\s+di)\b",
        action=r"\b(?:usare|usa|utilizzare|utilizza|mantenere|conservare|preservare|inviare|memorizzare|accettare|rifiutare|eseguire|eliminare|rimuovere|evitare|configurare|attendere|riprovare|includere|escludere|creare|interrompere|chiamare|aprire|chiudere)\b",
        target_negation=("non", "mai", "nessuno", "nessuna", "senza"),
        target_mandatory=("deve", "devono", "obbligatorio", "è necessario"),
    ),
    "ar": _profile(
        "ar",
        negation=r"(?:لا\s+(?:تحذف|تسمح|تغيّر|تغير)|أبدًا|دون)",
        mandatory=r"(?:يجب|يتعين|إلزامي|لا\s+بد\s+من)",
        conditional=r"(?:فقط\s+إذا|إلا\s+إذا|قبل\s+|بعد\s+|إذا|عندما)",
        numeric_limit=r"(?:على\s+الأقل|بحد\s+أقصى|لا\s+يزيد\s+عن|لا\s+أكثر\s+من|الحد\s+الأقصى|الحد\s+الأدنى)",
        action=r"(?:استخدم|احفظ|احتفظ|أرسل|خزن|اقبل|ارفض|نفّذ|نفذ|احذف|أزل|حافظ|تحقق|انتظر|أوقف|ضمّن|استبعد)",
        target_negation=("لا", "أبدًا", "دون"),
        target_mandatory=("يجب", "إلزامي", "يتعين"),
    ),
    "hi": _profile(
        "hi",
        negation=r"(?:कभी\s+नहीं|नहीं|बिना|(?<!\S)मत(?!\S))",
        mandatory=r"(?:अवश्य|अनिवार्य|ज़रूरी|जरूरी|चाहिए)",
        conditional=r"(?:केवल[^।\n]{0,40}जब|सिर्फ[^।\n]{0,40}जब|जब\s+तक|पहले|बाद|यदि|अगर)",
        numeric_limit=r"(?:कम\s+से\s+कम|अधिकतम|न्यूनतम|से\s+अधिक\s+नहीं|ज्यादा\s+से\s+ज्यादा)",
        action=r"(?:रखें|बनाए\s+रखें|सहेजें|भेजें|स्वीकार\s+करें|अस्वीकार\s+करें|चलाएँ|चलाएं|हटाएँ|हटाएं|प्रतीक्षा\s+करें|पुनः\s+प्रयास\s+करें)",
        target_negation=("नहीं", "कभी नहीं", "बिना", "मत"),
        target_mandatory=("अवश्य", "अनिवार्य", "ज़रूरी", "जरूरी", "चाहिए"),
    ),
    "ru": _profile(
        "ru",
        negation=r"(?:никогда|без\s+|не\s+(?:удаляйте|удаляй|разрешается|выполняйте)|не(?!\s+более))",
        mandatory=r"(?:должен|должна|должны|обязан|обязана|обязаны|обязательно)",
        conditional=r"(?:только\s+если|если|до\s+того\s+как|перед|после|пока\s+не)",
        numeric_limit=r"(?:не\s+более|не\s+менее|максимум|минимум|не\s+больше|не\s+меньше|в\s+пределах)",
        action=r"(?:используйте|используй|сохраните|сохраняйте|отправьте|храните|принимайте|отклоните|выполните|удалите|избегайте|настройте|ожидайте|повторите|включите|исключите|создайте|остановите|откройте|закройте|проверяйте)",
        target_negation=("не", "никогда", "без"),
        target_mandatory=("должен", "должны", "обязан", "обязаны"),
    ),
    "ja": _profile(
        "ja",
        negation=r"(?:決して.{0,12}ないでください|削除しないでください|してはいけません|禁止|使用してはならない)",
        mandatory=r"(?:必ず|しなければなりません|必要があります|必要です|必須です)",
        conditional=r"(?:場合に限り|場合のみ|場合|前に|後に|とき)",
        numeric_limit=r"(?:最大|最小|以上|以下|超えない|以内|まで|少なくとも|ちょうど)",
        action=r"(?:使用してください|保持してください|保存してください|送信してください|削除してください|実行してください|確認してください|待機してください|停止してください|含めてください|除外してください|再試行してください)",
        target_negation=("しないでください", "してはいけません", "禁止", "ない"),
        target_mandatory=("必ず", "しなければなりません", "必要です", "必須です"),
    ),
    "zh": _profile(
        "zh",
        negation=r"(?:请勿|不得|禁止|不能|不可|不要)",
        mandatory=r"(?:必须|务必|应当|需要|必须要)",
        conditional=r"(?:仅当|只有在|除非|如果|当)",
        numeric_limit=r"(?:最多|至少|不超过|不少于|至多|最少|最大|最小|上限|下限|以内)",
        action=r"(?:请(?:使用|保留|保存|发送|删除|执行|检查|等待|停止|包含|排除|确保|重试|重新尝试))",
        target_negation=("请勿", "不得", "禁止", "不能", "不可"),
        target_mandatory=("必须", "务必", "应当", "需要"),
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
