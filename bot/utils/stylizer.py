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

# Build reverse map for destylization
REVERSE_MAP = {}
for style, mapping in FONTS.items():
    for char_start, unicode_start in mapping.items():
        if unicode_start is None: continue
        count = 10 if char_start.isdigit() else 26
        for i in range(count):
            REVERSE_MAP[chr(unicode_start + i)] = chr(ord(char_start) + i)

for style, mapping in SPECIAL_CHARS.items():
    for char, code in mapping.items():
        REVERSE_MAP[chr(code)] = char

def destylize(text):
    if not text:
        return text

    # Regex to identify HTML tags and HTML entities
    tag_entity_pattern = r'(<[^>]+>|&[a-zA-Z0-9#]+;)'
    parts = re.split(tag_entity_pattern, text)
    result = []

    for part in parts:
        if not part: continue
        if part.startswith('<') and part.endswith('>'):
            result.append(part)
        elif part.startswith('&') and part.endswith(';'):
            result.append(part)
        else:
            # Map stylized characters back to ASCII
            result.append("".join(REVERSE_MAP.get(c, c) for c in part))

    return "".join(result)

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

def stylize_text(text, style, is_button=False):
    if not text or not style:
        return text

    # Always destylize first to ensure we aren't layering fonts
    text = destylize(text)

    # To be safe and "change" the font, we'll strip basic formatting tags
    # but keep links and others.
    clean_text = re.sub(r'<(?:b|i|code|s|u)>', '', text, flags=re.IGNORECASE)
    clean_text = re.sub(r'</(?:b|i|code|s|u)>', '', clean_text, flags=re.IGNORECASE)

    if style == "normal":
        return clean_text

    # Use native Telegram tags for bold, italic, and mono if not in a button
    if not is_button:
        if style == "bold":
            return f"<b>{clean_text}</b>"
        elif style == "italic":
            return f"<i>{clean_text}</i>"
        elif style == "mono":
            return f"<code>{clean_text}</code>"
        elif style == "bold_italic":
            return f"<b><i>{clean_text}</i></b>"

        # If it's a Unicode style for a message, use the clean_text for the rest of processing
        text = clean_text

    # We need to track if we are inside an <a> tag to avoid double-wrapping links
    in_anchor = False

    # Regex to identify HTML tags and HTML entities
    tag_entity_pattern = r'(<[^>]+>|&[a-zA-Z0-9#]+;)'

    parts = re.split(tag_entity_pattern, text)
    result = []

    for part in parts:
        if not part:
            continue

        # Check if it's a tag or entity
        if part.startswith('<') and part.endswith('>'):
            lower_part = part.lower()
            if lower_part.startswith('<a ') or lower_part == '<a>':
                in_anchor = True
            elif lower_part == '</a>':
                in_anchor = False
            result.append(part)
        elif part.startswith('&') and part.endswith(';'):
            # It's an HTML entity, keep it as is
            result.append(part)
        else:
            # It's plain text content
            if in_anchor:
                # Already inside a link, just stylize characters
                result.append("".join(get_char(c, style) for c in part))
            else:
                # Outside a link, look for naked URLs and Usernames to stylize and wrap
                # Pattern for URLs and Usernames (usernames must be 5-32 chars, letters, numbers, underscores)
                combined_pattern = r'(https?://[^\s<>"]+|(?:\s|^)@[a-zA-Z0-9_]{5,32})'
                sub_parts = re.split(combined_pattern, part)
                for sp in sub_parts:
                    if not sp: continue
                    if sp.startswith(('http://', 'https://')):
                        # Stylize URL characters and wrap in <a> tag
                        stylized_url = "".join(get_char(c, style) for c in sp)
                        result.append(f'<a href="{sp}">{stylized_url}</a>')
                    elif '@' in sp and sp.strip().startswith('@'):
                        # Stylize Username characters and wrap in <a> tag
                        # sp might contain a leading space
                        at_index = sp.find('@')
                        prefix = sp[:at_index]
                        username = sp[at_index+1:]
                        stylized_username = "@" + "".join(get_char(c, style) for c in username)
                        result.append(f'{prefix}<a href="https://t.me/{username}">{stylized_username}</a>')
                    else:
                        # Standard text, just stylize
                        result.append("".join(get_char(c, style) for c in sp))

    return "".join(result)

def get_available_fonts():
    return list(FONTS.keys()) + ["normal"]
