"""Convert spoken numbers in Indian languages to digits.

Callers (and the STT) may give numbers as words: "teen" (Hindi, 3),
"moonu" (Tamil, 3), "moodu" (Telugu, 3), "पैंतीस" (Hindi script, 35),
"do saal" (2 years), or native digits like "३५". The LLM is asked to send
digits, but this helper is the safety net before validation.

Coverage: 0-100 for Hindi (Latin spelling + Devanagari), Tamil and Telugu
(Latin spelling + native script), and English. Native digits for all major
Indic scripts. Unknown words (like "saal", "years", "bacche") are ignored.
"""

import re

# Native digit characters for Indic scripts -> ASCII digits.
_NATIVE_DIGIT_BLOCKS = [
    "०१२३४५६७८९",  # Devanagari (Hindi, Marathi)
    "০১২৩৪৫৬৭৮৯",  # Bengali
    "੦੧੨੩੪੫੬੭੮੯",  # Gurmukhi (Punjabi)
    "૦૧૨૩૪૫૬૭૮૯",  # Gujarati
    "୦୧୨୩୪୫୬୭୮୯",  # Odia
    "௦௧௨௩௪௫௬௭௮௯",  # Tamil
    "౦౧౨౩౪౫౬౭౮౯",  # Telugu
    "೦೧೨೩೪೫೬೭೮೯",  # Kannada
    "൦൧൨൩൪൫൬൭൮൯",  # Malayalam
]
_DIGIT_TABLE = str.maketrans({ch: str(i) for block in _NATIVE_DIGIT_BLOCKS for i, ch in enumerate(block)})

# --- Hindi, Latin spelling. Index = value. Several spellings per number. ---
_HINDI_LATIN = [
    "shunya shoonya", "ek", "do", "teen tin", "char chaar", "paanch panch", "chhe chhah che chhah cheh",
    "saat sat", "aath aat", "nau", "das dus",
    "gyarah gyaarah gyara", "barah baarah bara", "terah tera", "chaudah chauda chodah", "pandrah pandra",
    "solah sola", "satrah satra", "atharah athaarah athara", "unnis unees unnees", "bees bis",
    "ikkis ikkees", "bais baees baais", "teis teyis", "chaubis chaubees", "pachchis pachees pachis paccis",
    "chhabbis chhabbees chabbis", "sattais sattaees", "athais atthaees athaees", "untis unatees untees", "tees tis",
    "ikattis iktees ikattees", "battis battees", "tentis taintees tetis", "chautis chauntees chontis",
    "paintis paintees", "chhattis chhattees chattis", "saintis saintees", "adtis artees adtees", "untalis unchaalees untalees",
    "chalis chaalees chaalis",
    "iktalis iktaalees", "bayalis bayaalees", "tetalis taintaalees", "chavalis chavaalees chauvalis",
    "paintalis paintaalees", "chhiyalis chhiyaalees", "saintalis saintaalees", "adtalis artaalees",
    "unchas unanchaas", "pachas pachaas",
    "ikyavan ikyaavan", "bavan baavan", "tirpan tirepan", "chauvan chauwan", "pachpan", "chhappan chappan",
    "sattavan sattaavan", "atthavan atthaavan athavan", "unsath unsaath", "saath sath",
    "iksath iksaath", "basath baasath", "tirsath tiresath", "chausath chaunsath", "painsath paisath",
    "chhiyasath chhiyaasath", "sadsath sarsath", "adsath arsath", "unhattar", "sattar",
    "ikhattar", "bahattar", "tihattar", "chauhattar", "pachhattar pachattar", "chhihattar",
    "satattar sathattar", "athattar", "unasi unaasi", "assi assee",
    "ikyasi ikyaasi", "bayasi bayaasi", "tirasi tiraasi", "chaurasi chauraasi", "pachasi pachaasi",
    "chhiyasi chhiyaasi", "sattasi sattaasi", "athasi atthaasi", "navasi navaasi", "nabbe",
    "ikyanve ikyaanve", "baanve banve", "tiranve tiraanve", "chauranve chauraanve", "pachanve pachaanve",
    "chhiyanve chhiyaanve", "sattanve sattaanve", "atthanve atthaanve", "ninyanve ninyaanve", "sau",
]

# --- Hindi, Devanagari. Index = value. ---
_HINDI_DEVANAGARI = [
    "शून्य", "एक", "दो", "तीन", "चार", "पांच पाँच", "छह छः छे", "सात", "आठ", "नौ", "दस",
    "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह पन्द्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस", "बीस",
    "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस", "तीस",
    "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस", "चालीस",
    "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस चौवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास", "पचास",
    "इक्यावन", "बावन", "तिरेपन तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ", "साठ",
    "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर", "सत्तर",
    "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी उनासी", "अस्सी",
    "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी", "नब्बे",
    "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे", "सौ",
]

# --- Words with a fixed value (units, teens, tens). Tamil and Telugu build
# 21-99 as "tens + unit" (e.g. "irupathu anju" = 25), handled in _combine(). ---
_FIXED_WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
    # Tamil (Latin spelling, common spoken forms)
    "onnu": 1, "onru": 1, "ondru": 1, "rendu": 2, "irandu": 2, "moonu": 3, "moondru": 3, "munru": 3,
    "naalu": 4, "nalu": 4, "naangu": 4, "nangu": 4, "anju": 5, "ainthu": 5, "aindhu": 5, "aaru": 6,
    "ezhu": 7, "elu": 7, "ettu": 8, "ombodhu": 9, "onbathu": 9, "onpathu": 9, "pathu": 10, "patthu": 10,
    "padhinonnu": 11, "pathinonnu": 11, "panirendu": 12, "pannendu": 12, "padhimoonu": 13, "pathimoonu": 13,
    "padhinaalu": 14, "pathinaalu": 14, "padhinanju": 15, "pathinanju": 15, "padhinaaru": 16, "pathinaaru": 16,
    "padhinezhu": 17, "pathinezhu": 17, "padhinettu": 18, "pathinettu": 18, "patthombodhu": 19, "pathonbathu": 19,
    "irupathu": 20, "irubathu": 20, "iruvathu": 20, "irupathi": 20, "irubathi": 20,
    "muppathu": 30, "muppathi": 30, "naarpathu": 40, "narpathu": 40, "naarpathi": 40,
    "aimbathu": 50, "ambathu": 50, "aimbathi": 50, "arubathu": 60, "arupathu": 60, "arubathi": 60,
    "ezhupathu": 70, "ezhubathu": 70, "ezhupathi": 70, "enbathu": 80, "enpathu": 80, "enbathi": 80,
    "thonnooru": 90, "thonnuru": 90, "thonnootri": 90, "nooru": 100,
    # Tamil script (formal and spoken forms; "...த்து/...த்தி" are the "tens +" prefixes)
    "ஒன்று": 1, "ஒண்ணு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "மூணு": 3, "நான்கு": 4, "நாலு": 4,
    "ஐந்து": 5, "அஞ்சு": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    "பதினொன்று": 11, "பன்னிரண்டு": 12, "பதிமூன்று": 13, "பதினான்கு": 14, "பதினைந்து": 15,
    "பதினாறு": 16, "பதினேழு": 17, "பதினெட்டு": 18, "பத்தொன்பது": 19,
    "இருபது": 20, "இருபத்து": 20, "இருபத்தி": 20, "முப்பது": 30, "முப்பத்து": 30, "முப்பத்தி": 30,
    "நாற்பது": 40, "நாற்பத்து": 40, "நாற்பத்தி": 40, "ஐம்பது": 50, "ஐம்பத்து": 50, "ஐம்பத்தி": 50,
    "அறுபது": 60, "அறுபத்து": 60, "அறுபத்தி": 60, "எழுபது": 70, "எழுபத்து": 70, "எழுபத்தி": 70,
    "எண்பது": 80, "எண்பத்து": 80, "எண்பத்தி": 80, "தொண்ணூறு": 90, "தொண்ணூற்று": 90, "நூறு": 100,
    # Telugu (Latin spelling)
    "okati": 1, "okka": 1, "moodu": 3, "mudu": 3, "naalugu": 4, "nalugu": 4, "aidu": 5, "ayidu": 5,
    "edu": 7, "eedu": 7, "enimidi": 8, "tommidi": 9, "thommidi": 9, "padi": 10,
    "padakondu": 11, "pannendu": 12, "padamoodu": 13, "padnalugu": 14, "padhnalugu": 14, "padihenu": 15,
    "padahaaru": 16, "padaharu": 16, "padihedu": 17, "paddenimidi": 18, "padhenimidi": 18, "pandommidi": 19,
    "iravai": 20, "iravay": 20, "muppai": 30, "muppay": 30, "nalabhai": 40, "nalabai": 40, "yabhai": 50,
    "yabai": 50, "ebhai": 50, "aravai": 60, "debbai": 70, "enabhai": 80, "enabai": 80, "tombhai": 90,
    "tombai": 90, "vanda": 100, "vandha": 100,
    # Telugu script
    "ఒకటి": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "అయిదు": 5, "ఆరు": 6, "ఏడు": 7,
    "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10, "పదకొండు": 11, "పన్నెండు": 12, "పదమూడు": 13,
    "పద్నాలుగు": 14, "పదిహేను": 15, "పదహారు": 16, "పదిహేడు": 17, "పద్దెనిమిది": 18, "పందొమ్మిది": 19,
    "ఇరవై": 20, "ముప్పై": 30, "నలభై": 40, "యాభై": 50, "అరవై": 60, "డెబ్బై": 70, "ఎనభై": 80,
    "తొంభై": 90, "వంద": 100,
}


def _build_word_table() -> dict[str, int]:
    table = dict(_FIXED_WORDS)
    for value, spellings in enumerate(_HINDI_LATIN):
        for word in spellings.split():
            table[word] = value
    for value, spellings in enumerate(_HINDI_DEVANAGARI):
        for word in spellings.split():
            table[word] = value
    return table


WORD_VALUES = _build_word_table()

# Words that multiply the previous number by 100 ("ek sau" = 100, "two hundred" = 200).
_HUNDRED_WORDS = {"sau", "सौ", "hundred", "nooru", "நூறு", "vanda", "vandha", "వంద"}

_TOKEN_SPLIT = re.compile(r"[\s,;/.\-–?!।]+")
_AND_WORDS = {"and", "aur", "or", "और", "mattrum", "matrum", "inka", "mariyu"}


def _normalize(text: str) -> str:
    return text.translate(_DIGIT_TABLE).lower().strip()


def _combine(values: list[int]) -> list[int]:
    """Merge spoken parts into whole numbers.

    "twenty five" -> 25, "irupathu anju" -> 25, "ek sau" -> 100.
    A tens value (20..90) followed by a unit (1..9) becomes one number.
    """
    result: list[int] = []
    for v in values:
        if result and v == 100 and 1 <= result[-1] <= 9:
            result[-1] *= 100
        elif result and 1 <= v <= 9 and result[-1] % 10 == 0 and 20 <= result[-1] % 100 <= 90:
            result[-1] += v
        elif result and 1 <= v <= 99 and result[-1] % 100 == 0 and result[-1] >= 100:
            result[-1] += v  # "sau paanch" -> 105
        else:
            result.append(v)
    return result


def extract_numbers(text: str) -> list[int]:
    """Find all numbers in text, in order. Digits win over words if present.

    Words separated by "and"/"aur" are kept apart: "do aur paanch" -> [2, 5].
    """
    if text is None:
        return []
    norm = _normalize(str(text))
    digits = re.findall(r"\d+(?:\.\d+)?", norm)
    if digits:
        return [int(float(d)) if float(d).is_integer() else float(d) for d in digits]

    groups: list[list[int]] = [[]]
    for token in _TOKEN_SPLIT.split(norm):
        if not token:
            continue
        if token in _AND_WORDS:
            groups.append([])
            continue
        if token in WORD_VALUES:
            groups[-1].append(WORD_VALUES[token])
        elif token in _HUNDRED_WORDS:
            groups[-1].append(100)
        else:
            # Unknown word (e.g. "saal", "years"): ends the current number.
            groups.append([])
    numbers: list[int] = []
    for g in groups:
        numbers.extend(_combine(g))
    return numbers


def parse_spoken_number(value) -> int | float | None:
    """Return the single number in value, or None if there is none or more than one.

    "teen" -> 3, "do saal" -> 2, "moonu" -> 3, "पैंतीस" -> 35, "35" -> 35,
    "do ya teen" -> None (ambiguous, so the agent should ask again).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    numbers = extract_numbers(str(value))
    return numbers[0] if len(numbers) == 1 else None


def parse_number_list(value) -> list | None:
    """Parse a list of numbers: [5, 8], "5, 8", "paanch aur aath" -> [5, 8]."""
    if isinstance(value, list):
        out = []
        for item in value:
            n = parse_spoken_number(item)
            if n is None:
                return None
            out.append(n)
        return out
    if value is None:
        return None
    numbers = extract_numbers(str(value))
    return numbers or None
