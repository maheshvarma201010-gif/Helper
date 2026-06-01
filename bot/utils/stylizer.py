import re

FONTS = {
    "bold": {
        "A": 0x1D400, "a": 0x1D41A, "0": 0x1D7CE
    },
    "italic": {
        "A": 0x1D434, "a": 0x1D44E, "0": None
    },
    "bold_italic": {
        "A": 0x1D468, "a": 0x1D482, "0": None
    },
    "mono": {
        "A": 0x1D670, "a": 0x1D68A, "0": 0x1D7F6
    },
    "script": {
        "A": 0x1D49C, "a": 0x1D4B6, "0": None
    },
    "bold_script": {
        "A": 0x1D4D0, "a": 0x1D4EA, "0": None
    },
    "fraktur": {
        "A": 0x1D504, "a": 0x1D51E, "0": None
    },
    "bold_fraktur": {
        "A": 0x1D56C, "a": 0x1D586, "0": None
    },
    "double_struck": {
        "A": 0x1D538, "a": 0x1D552, "0": 0x1D7D8
    },
    "sans_bold": {
        "A": 0x1D5D4, "a": 0x1D5EE, "0": 0x1D7EC
    },
    "sans_italic": {
        "A": 0x1D608, "a": 0x1D622, "0": None
    }
}

# Unicode characters that don't follow the sequential mapping in mathematical blocks
SPECIAL_CHARS = {
    "script": {
        "B": 0x212C, "E": 0x2130, "F": 0x2131, "H": 0x210B, "I": 0x2110, "L": 0x2112, "M": 0x2133, "R": 0x211B,
        "e": 0x212F, "g": 0x210A, "o": 0x2134
    },
    "fraktur": {
        "C": 0x212D, "H": 0x210C, "I": 0x2111, "R": 0x211C, "Z": 0x2128
    },
    "double_struck": {
        "C": 0x2102, "H": 0x210D, "N": 0x2115, "P": 0x2119, "Q": 0x211A, "R": 0x211D, "Z": 0x2124
    },
    "italic": {
        "h": 0x210E
    }
}

def get_char(char, style):
    if style not in FONTS:
        return char

    # Check special chars first
    if style in SPECIAL_CHARS and char in SPECIAL_CHARS[style]:
        return chr(SPECIAL_CHARS[style][char])

    mapping = FONTS[style]

    if 'A' <= char <= 'Z':
        return chr(mapping['A'] + (ord(char) - ord('A')))
    elif 'a' <= char <= 'z':
        return chr(mapping['a'] + (ord(char) - ord('a')))
    elif '0' <= char <= '9' and mapping.get('0') is not None:
        return chr(mapping['0'] + (ord(char) - ord('0')))

    return char

def stylize_text(text, style):
    if not text or not style or style == "normal":
        return text

    # Regex to keep HTML tags intact
    # We split by HTML tags, stylize the text parts, and join them back
    parts = re.split(r'(<[^>]+>)', text)
    result = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            result.append(part)
        else:
            stylized_part = "".join(get_char(c, style) for c in part)
            result.append(stylized_part)

    return "".join(result)

def get_available_fonts():
    return list(FONTS.keys()) + ["normal"]
