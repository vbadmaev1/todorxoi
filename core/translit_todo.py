# -*- coding: utf-8 -*-
"""
translit_todo.py — конвертация между транслитерацией проекта
(ā ē ī ō ū ȫ ǖ, ö ü, γ č š ǰ, ...) и настоящим юникодным текстом тодо бичиг.

Как это устроено: словари ниже (_CHAR_ROM_TO_TODO / _CHAR_TODO_TO_ROM /
_REPLACEMENTS / контекстные правила для h и g) скопированы из присланного
JS значение-в-значение, без единого исправления — только синтаксис
JS -> Python. Единственное, что добавлено сверху, — тонкий слой
(translit_to_rom / rom_to_translit), который переводит диакритику проекта
в ASCII-обозначения этого JS и обратно (ȫ -> "O:", γ -> "G" и т.д.).

Файл перенесён в пакет без изменений логики.
"""

import re
import unicodedata


# =============================================================================
# ЧАСТЬ 1 — перенос присланного JS (romToTodo / todoToRom) почти дословно.
# =============================================================================

_REPLACEMENTS = {
    "ch": "C",
    "zh": "j",
    "ng": "N",
    "jy": "ᡚ",
    "ny": "ᡛ",
    "lh": "ᡀ",
    "gh": "ᡘ",
    "kh": "K",
    "ts": "ᠼ",
    "dz": "ᡜ",
    "x": "h",
    "G": "g",
    "q": "g",
    "=": "",
    "+": "",
}

_CHAR_ROM_TO_TODO = {
    ":": "ᡃ",
    "a": "ᠠ",
    "e": "ᡄ",
    "i": "ᡅ",
    "o": "ᡆ",
    "u": "ᡇ",
    "O": "ᡈ",
    "U": "ᡉ",
    "N": "ᡊ",
    "n": "ᠨ",
    "b": "ᡋ",
    "p": "ᡌ",
    "h": "ᡍ",
    "g": "ᡎ",
    "m": "ᡏ",
    "l": "ᠯ",
    "s": "ᠰ",
    "S": "ᠱ",
    "t": "ᡐ",
    "d": "ᡑ",
    "c": "ᡔ",
    "C": "ᡒ",
    "j": "ᡓ",
    "J": "ᡚ",
    "z": "ᠴ",
    "y": "ᡕ",
    "w": "ᡖ",
    "k": "ᡍ",
    "K": "ᡗ",
    "H": "ᡙ",
    "r": "ᠷ",
    "v": "ᡖ",
    "f": "ᠸ",
    "Q": "ᠼ",
    "Z": "ᡜ",
    ".": "︒",
    ",": "︐",
    "/": "︑",
    "&": "︑",
    "'": "᠋",
    '"': "᠌",
    "`": "᠍",
    "_": "᠎",
    "*": "‍",
    "-": " ",
    "!": "︕",
    "?": "︖",
    "<": "︽",
    ">": "︾",
    "\n": "<br>",
}

_CHAR_TODO_TO_ROM = {
    "ᡃ": ":",
    "ᠠ": "a",
    "ᡄ": "e",
    "ᡅ": "i",
    "ᡆ": "o",
    "ᡇ": "u",
    "ᡈ": "O",
    "ᡉ": "U",
    "ᡊ": "ng",
    "ᠨ": "n",
    "ᡋ": "b",
    "ᡌ": "p",
    "ᡏ": "m",
    "ᠯ": "l",
    "ᠰ": "s",
    "ᠱ": "S",
    "ᡐ": "t",
    "ᡑ": "d",
    "ᡔ": "c",
    "ᡒ": "C",
    "ᡓ": "j",
    "ᡚ": "J",
    "ᠴ": "z",
    "ᡕ": "y",
    "ᡖ": "w",
    "ᠷ": "r",
    "ᠸ": "f",
    "ᡜ": "dz",
    "ᠼ": "ts",
    "ᡚ": "jy",
    "ᡛ": "ny",
    "᠋": "'",
    "᠌": '"',
    "᠍": "`",
    "᠎": "_",
    "‍": "*",
    " ": "-",
    "︒": ".",
    "︐": ",",
    "︑": "&",
    "︕": "!",
    "︖": "?",
    "︽": "<",
    "︾": ">",
    "\n": "<br>",
}

_SPECIAL_TODO_TO_ROM = {
    "ᡘ": "kh",
    "ᡀ": "lh",
    "ᡗ": "gh",
    "ᡙ": "h",
}

_FRONT_VOWELS = {"ᡄ", "ᡅ", "ᡈ", "ᡉ"}
_BACK_VOWELS = {"ᠠ", "ᡆ", "ᡇ"}


def _rom_to_todo(rom_text):
    """Дословный перенос romToTodo(...) из JS."""
    for key, val in _REPLACEMENTS.items():
        rom_text = rom_text.replace(key, val)
    todo_text = "".join(_CHAR_ROM_TO_TODO.get(ch, ch) for ch in rom_text)
    todo_text = todo_text.replace("ny", "N")  # финальная правка, как в JS
    return todo_text


def _todo_to_rom(todo_text):
    """Дословный перенос todoToRom(...) из JS (с контекстными правилами)."""
    out = []
    n = len(todo_text)
    for i, ch in enumerate(todo_text):
        next_ch = todo_text[i + 1] if i + 1 < n else ""
        if ch == "ᡍ":  # h / k / x, зависит от следующей гласной
            if next_ch in _FRONT_VOWELS:
                out.append("k")
            elif next_ch in _BACK_VOWELS:
                out.append("x")
            else:
                out.append("h")
            continue
        if ch == "ᡎ":  # g / G(=γ) / q, зависит от следующей гласной
            if next_ch in _FRONT_VOWELS:
                out.append("g")
            elif next_ch in _BACK_VOWELS:
                out.append("G")
            else:
                out.append("q")
            continue
        if ch in _SPECIAL_TODO_TO_ROM:
            out.append(_SPECIAL_TODO_TO_ROM[ch])
            continue
        out.append(_CHAR_TODO_TO_ROM.get(ch, ch))
    return "".join(out)


# =============================================================================
# ЧАСТЬ 2 — транслитерация проекта <-> ASCII-схема JS (часть 1).
# =============================================================================

# долгие гласные: у JS долгота — отдельный символ ":", у нас — макрон на
# базовой гласной. "O:" / "U:" — способ показать долгий ö/ü через ASCII-схему
# JS (ö уже сама по себе "O", ü — "U", ":" добавляет долготу поверх любой
# предыдущей гласной).
_TRANSLIT_TO_ROM_MULTI = [
    ("ā", "a:"), ("ē", "e:"), ("ī", "i:"), ("ō", "o:"), ("ū", "u:"),
    ("ȫ", "O:"), ("ǖ", "U:"),
    ("ö", "O"), ("ü", "U"),
    ("γ", "G"),
    ("č", "C"),
    ("š", "S"),
    ("ǰ", "j"),
    # РЕШЕНИЕ: x и k ведём в одну и ту же букву тодо бичиг (через "h" —
    # то, что в JS уже переключается на k/x по соседней гласной).
    ("k", "h"),
    ("x", "h"),
    # дефис (граница суффикса) НЕ трогаем здесь — он проходит как есть
    # в _rom_to_todo, где уже есть готовое правило "-" -> NNBSP ( ).
]

# обратная схема (для todo_to_translit): здесь x и k разводим обратно —
# ASCII "k"/"x", которые вернёт _todo_to_rom, уже корректно расставлены
# по гласной, просто переносим их как есть в нашу транслитерацию.
_ROM_TO_TRANSLIT_MULTI = [
    ("O:", "ȫ"), ("U:", "ǖ"),
    ("a:", "ā"), ("e:", "ē"), ("i:", "ī"), ("o:", "ō"), ("u:", "ū"),
    ("O", "ö"), ("U", "ü"),
    ("G", "γ"),
    ("C", "č"),
    ("S", "š"),
    ("j", "ǰ"),  # обычная ᡓ всегда даёт "полную" форму ǰ, не голое j
    ("h", "x"),  # ASCII "h" — контекстный fallback JS, когда рядом с ᡍ нет
                 # явной гласной (например, конец слова). Вместо этого
                 # смотрим на гласную ГАРМОНИЮ ВСЕГО СЛОВА (см. ниже) —
                 # но если и это не помогло, по умолчанию x.
]


def translit_to_rom(text):
    text = unicodedata.normalize("NFC", text)
    for src, dst in _TRANSLIT_TO_ROM_MULTI:
        text = text.replace(src, dst)
    return text


_BACK_HARMONY_LETTERS = set("aāoōuū")   # гласные заднего ряда
_FRONT_HARMONY_LETTERS = set("eēiīöȫüǖ")  # гласные переднего ряда


def _word_harmony(word):
    """Гармония гласных всего слова — используется только как запасной
    вариант, когда рядом нет явной гласной."""
    for ch in word:
        if ch in _BACK_HARMONY_LETTERS:
            return "back"
        if ch in _FRONT_HARMONY_LETTERS:
            return "front"
    return "back"  # совсем без гласных — редкий случай, дефолт


def rom_to_translit(text, word_for_harmony=None):
    for src, dst in _ROM_TO_TRANSLIT_MULTI:
        if src == "h":
            continue  # обработаем отдельно, с учётом гармонии
        text = text.replace(src, dst)
    if "h" in text and word_for_harmony is not None:
        fallback = "k" if _word_harmony(word_for_harmony) == "front" else "x"
        text = text.replace("h", fallback)
    else:
        text = text.replace("h", "x")
    return unicodedata.normalize("NFC", text)


# =============================================================================
# ЧАСТЬ 3 — публичные функции
# =============================================================================

def translit_to_todo(text):
    """Транслитерация проекта -> юникодный текст тодо бичиг.

    Вход приводится к нижнему регистру: в тодо бичиг прописных букв нет,
    а промежуточная ASCII-схема использует регистр как значащий (O = ö,
    U = ü, C = č, S = š, G = γ). Без этого заглавная буква в начале
    предложения просто не конвертировалась бы («Xalimaq» -> «Xᠠᠯᡅᡏᠠᡎ»).

    Переводы строк обрабатываются отдельно: в исходной JS-таблице "\\n"
    отображается в литерал "<br>" (это имело смысл для веб-страницы, но не
    здесь — иначе «<br>» так и уедет в картинку). Поэтому режем текст по
    строкам, конвертируем каждую и склеиваем обратно через "\\n".
    """
    lines = text.split("\n")
    return "\n".join(_rom_to_todo(translit_to_rom(line.lower())) for line in lines)


def todo_to_translit(todo_text):
    """Юникодный текст тодо бичиг -> транслитерация проекта.

    Переводы строк, как и в обратную сторону, обрабатываются построчно —
    чтобы "\\n" не превратился в литерал "<br>"."""
    out = []
    for line in todo_text.split("\n"):
        rom = _todo_to_rom(line)
        out.append(rom_to_translit(rom, word_for_harmony=rom))
    return "\n".join(out)


# =============================================================================
# ЧАСТЬ 4 — определение, чем именно является присланный текст
# =============================================================================

# Юникод-блок Mongolian: U+1800..U+18AF (тодо бичиг живёт здесь же)
_TODO_RE = re.compile(r"[᠀-᢯]")
# кириллица, включая калмыцкие буквы ә ө ү һ җ ң
_CYRILLIC_RE = re.compile(r"[а-яёәөүһҗңА-ЯЁӘӨҮҺҖҢ]")
# латиница проекта (с диакритикой)
_LATIN_RE = re.compile(r"[a-zA-Zāēīōūȫǖöüγčšǰ]")

SCRIPT_TODO = "todo"
SCRIPT_CYRILLIC = "cyrillic"
SCRIPT_TRANSLIT = "translit"
SCRIPT_UNKNOWN = "unknown"


def detect_script(text):
    """Определяет, в какой системе записан текст: тодо бичиг, калмыцкая
    кириллица или транслитерация на латинице."""
    if _TODO_RE.search(text):
        return SCRIPT_TODO
    if _CYRILLIC_RE.search(text):
        return SCRIPT_CYRILLIC
    if _LATIN_RE.search(text):
        return SCRIPT_TRANSLIT
    return SCRIPT_UNKNOWN


if __name__ == "__main__":
    print("Примеры конвертации транслитерация -> тодо бичиг:\n")
    demo_words = ["γalzuü", "činggis", "čōno", "sȫnēkü", "aq-tai", "xoyino",
                  "körsülekü", "bičig"]
    for w in demo_words:
        todo = translit_to_todo(w)
        back = todo_to_translit(todo)
        mark = "OK " if back == w else "-- "
        print(f"  {mark}{w:15s} -> {todo:15s} -> обратно: {back}")
