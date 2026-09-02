import re
import html
from collections import defaultdict
from bot.utils.stylizer import destylize

def parse_format_input(format_text: str):
    """
    Parses format input text containing lines like:
    "Multi Audio : link1"
    "Multi Audio : link2"
    "Telugu : link3"

    Returns a list of tuples in order: [(target_text, url), ...]
    """
    mappings = []
    if not format_text:
        return mappings

    lines = format_text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue

        target_text = ""
        url = ""

        # Try matching URL pattern on the right side
        match = re.search(r'^(.*?)(?:\s*[:\-]\s*|\s+)(https?://\S+|t\.me/\S+|\S+\.\S+.*)$', line, re.IGNORECASE)
        if match:
            target_text = match.group(1).strip()
            url = match.group(2).strip()
        elif ':' in line:
            parts = line.split(':', 1)
            target_text = parts[0].strip()
            url = parts[1].strip()
        elif ' - ' in line:
            parts = line.split(' - ', 1)
            target_text = parts[0].strip()
            url = parts[1].strip()

        if target_text and url:
            mappings.append((target_text, url))

    return mappings

def count_occurrences(caption_html: str, target_text: str) -> int:
    """Counts un-hyperlinked occurrences of target_text in caption_html."""
    dest_target = destylize(target_text).strip().lower()
    tag_pattern = r'(<[^>]+>)'
    parts = re.split(tag_pattern, caption_html)
    in_anchor = False
    count = 0

    for p in parts:
        if not p:
            continue
        if p.startswith('<') and p.endswith('>'):
            lower_p = p.lower()
            if lower_p.startswith('<a ') or lower_p == '<a>':
                in_anchor = True
            elif lower_p == '</a>':
                in_anchor = False
        else:
            if not in_anchor:
                dest_p = destylize(p)
                matches = re.findall(re.escape(dest_target), dest_p, re.IGNORECASE)
                count += len(matches)

    return count

def insert_hyperlinks(caption_html: str, mappings: list):
    """
    Inserts hyperlinks into caption HTML string sequentially for each target_text occurrence.
    Preserves original formatting, emojis, and HTML structure.

    Returns:
        tuple: (updated_caption_html, extra_links, missing_links)
        - extra_links: list of tuples [(target_text, [unused_url, ...]), ...]
        - missing_links: list of tuples [(target_text, total_occurrences, provided_links_count), ...]
    """
    if not caption_html or not mappings:
        return caption_html, [], []

    # Group provided URLs sequentially by normalized target text key
    grouped_links = defaultdict(list)
    target_display = {}

    for target_text, url in mappings:
        key = destylize(target_text).strip().lower()
        grouped_links[key].append(url)
        if key not in target_display:
            target_display[key] = target_text

    # Calculate total occurrences in original caption for reporting missing links
    total_occurrences = {}
    for key, disp_target in target_display.items():
        total_occurrences[key] = count_occurrences(caption_html, disp_target)

    tag_pattern = r'(<[^>]+>)'
    consumed_counts = defaultdict(int)

    # Replace occurrences sequentially per target key
    for key, urls in grouped_links.items():
        disp_target = target_display[key]
        destylized_target = key

        parts = re.split(tag_pattern, caption_html)
        new_parts = []
        in_anchor = False
        url_idx = 0

        for p in parts:
            if not p:
                continue

            if p.startswith('<') and p.endswith('>'):
                lower_p = p.lower()
                if lower_p.startswith('<a ') or lower_p == '<a>':
                    in_anchor = True
                elif lower_p == '</a>':
                    in_anchor = False
                new_parts.append(p)
            else:
                if in_anchor or url_idx >= len(urls):
                    new_parts.append(p)
                else:
                    destylized_p = destylize(p)
                    if destylized_target in destylized_p.lower():
                        exact_pattern = re.compile(re.escape(disp_target), re.IGNORECASE)
                        dest_pattern = re.compile(re.escape(destylized_target), re.IGNORECASE)

                        if exact_pattern.search(p):
                            def repl_exact(m):
                                nonlocal url_idx
                                if url_idx < len(urls):
                                    u = urls[url_idx]
                                    url_idx += 1
                                    consumed_counts[key] += 1
                                    return f'<a href="{u}">{m.group(0)}</a>'
                                return m.group(0)
                            p = exact_pattern.sub(repl_exact, p)
                        elif dest_pattern.search(destylized_p):
                            def repl_dest(m):
                                nonlocal url_idx
                                if url_idx < len(urls):
                                    u = urls[url_idx]
                                    url_idx += 1
                                    consumed_counts[key] += 1
                                    return f'<a href="{u}">{m.group(0)}</a>'
                                return m.group(0)
                            p = dest_pattern.sub(repl_dest, destylized_p)

                    new_parts.append(p)

        caption_html = "".join(new_parts)

    extra_links = []
    missing_links = []

    for key, urls in grouped_links.items():
        provided_count = len(urls)
        used_count = consumed_counts[key]
        total_occs = total_occurrences.get(key, 0)
        disp_target = target_display[key]

        if provided_count > total_occs:
            unused_urls = urls[total_occs:]
            extra_links.append((disp_target, unused_urls))
        elif provided_count < total_occs:
            missing_links.append((disp_target, total_occs, provided_count))

    return caption_html, extra_links, missing_links
