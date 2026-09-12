"""Thai Kedmanee <-> US QWERTY layout mapping.

Every physical key on the main alphanumeric block is one row of KEYS:

    (us_unshifted, us_shifted, thai_unshifted, thai_shifted)

Thai characters are spelled as \\u escapes on purpose: several of them are
combining marks that render on top of the previous glyph, which makes a
literal table impossible to proofread.
"""

KEYS = [
    # --- number row -------------------------------------------------------
    ("`", "~", "_",      "%"),
    ("1", "!", "ๅ", "+"),       # LAKKHANGYAO
    ("2", "@", "/",      "๑"),  # THAI DIGIT ONE
    ("3", "#", "-",      "๒"),
    ("4", "$", "ภ", "๓"),  # PHO SAMPHAO
    ("5", "%", "ถ", "๔"),  # THO THUNG
    ("6", "^", "ุ", "ู"),  # SARA U / SARA UU
    ("7", "&", "ึ", "฿"),  # SARA UE / BAHT SIGN
    ("8", "*", "ค", "๕"),  # KHO KHWAI
    ("9", "(", "ต", "๖"),  # TO TAO
    ("0", ")", "จ", "๗"),  # CHO CHAN
    ("-", "_", "ข", "๘"),  # KHO KHAI
    ("=", "+", "ช", "๙"),  # CHO CHANG
    # --- top letter row ---------------------------------------------------
    ("q", "Q", "ๆ", "๐"),  # MAIYAMOK / THAI DIGIT ZERO
    ("w", "W", "ไ", '"'),       # SARA AI MAIMALAI
    ("e", "E", "ำ", "ฎ"),  # SARA AM / DO CHADA
    ("r", "R", "พ", "ฑ"),  # PHO PHAN
    ("t", "T", "ะ", "ธ"),  # SARA A
    ("y", "Y", "ั", "ํ"),  # MAI HAN AKAT / NIKHAHIT
    ("u", "U", "ี", "๊"),  # SARA II / MAI TRI
    ("i", "I", "ร", "ณ"),  # RO RUA
    ("o", "O", "น", "ฯ"),  # NO NU / PAIYANNOI
    ("p", "P", "ย", "ญ"),  # YO YAK
    ("[", "{", "บ", "ฐ"),  # BO BAIMAI
    ("]", "}", "ล", ","),       # LO LING
    ("\\", "|", "ฃ", "ฅ"), # KHO KHUAT / KHO KHON
    # --- home row ---------------------------------------------------------
    ("a", "A", "ฟ", "ฤ"),  # FO FAN / RU
    ("s", "S", "ห", "ฆ"),  # HO HIP
    ("d", "D", "ก", "ฏ"),  # KO KAI
    ("f", "F", "ด", "โ"),  # DO DEK / SARA O
    ("g", "G", "เ", "ฌ"),  # SARA E
    ("h", "H", "้", "็"),  # MAI THO / MAITAIKHU
    ("j", "J", "่", "๋"),  # MAI EK / MAI CHATTAWA
    ("k", "K", "า", "ษ"),  # SARA AA
    ("l", "L", "ส", "ศ"),  # SO SUA
    (";", ":", "ว", "ซ"),  # WO WAEN
    ("'", '"', "ง", "."),       # NGO NGU
    # --- bottom row -------------------------------------------------------
    ("z", "Z", "ผ", "("),       # PHO PHUNG
    ("x", "X", "ป", ")"),       # PO PLA
    ("c", "C", "แ", "ฉ"),  # SARA AE
    ("v", "V", "อ", "ฮ"),  # O ANG / HO NOKHUK
    ("b", "B", "ิ", "ฺ"),  # SARA I / PHINTHU
    ("n", "N", "ื", "์"),  # SARA UEE / THANTHAKHAT
    ("m", "M", "ท", "?"),       # THO THAHAN
    (",", "<", "ม", "ฒ"),  # MO MA
    (".", ">", "ใ", "ฬ"),  # SARA AI MAIMUAN
    ("/", "?", "ฝ", "ฦ"),  # FO FA / LU
]

EN_TO_TH: dict[str, str] = {}
TH_TO_EN: dict[str, str] = {}
for _us, _US, _th, _TH in KEYS:
    EN_TO_TH[_us] = _th
    EN_TO_TH[_US] = _TH
    TH_TO_EN.setdefault(_th, _us)
    TH_TO_EN.setdefault(_TH, _US)

#: Codepoint range of the Thai script block.
THAI_START, THAI_END = "฀", "๿"

TH2EN = "th2en"
EN2TH = "en2th"


def is_thai(ch: str) -> bool:
    return THAI_START <= ch <= THAI_END


def detect_direction(text: str) -> str | None:
    """Guess which way the text needs to go, or None if there is no evidence.

    Thai script is unambiguous: if it is there at all, the text was typed on a
    Thai layout.  Latin letters point the other way.  Text with neither -
    "2026", "$14.99", an emoji - is not evidence of anything, and returning a
    direction anyway would happily turn a selected phone number into Thai
    consonants.  Digits and punctuation *are* on both layouts, so that damage
    is real; the caller is expected to decline rather than guess.
    """
    thai = sum(1 for ch in text if is_thai(ch))
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if not thai and not latin:
        return None
    return TH2EN if thai > latin else EN2TH


def convert(text: str, direction: str | None = None) -> str:
    """Re-type ``text`` as if the other keyboard layout had been active.

    ``direction`` of ``None`` auto-detects.  Characters that are not on either
    layout (spaces, newlines, emoji, ASCII digits) pass through untouched.
    """
    if direction is None:
        direction = detect_direction(text) or EN2TH
    table = TH_TO_EN if direction == TH2EN else EN_TO_TH
    return "".join(table.get(ch, ch) for ch in text)


def normalize_thai(text: str) -> str:
    """Fold the SARA E + SARA E sequence into a single SARA AE.

    Typing ``gg`` produces เเ, which looks identical to แ but is
    a different string.  Off by default: it is a spelling fix, not a layout fix.
    """
    return text.replace("เเ", "แ")
