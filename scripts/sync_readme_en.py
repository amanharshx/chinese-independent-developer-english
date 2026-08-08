#!/usr/bin/env python3
"""
sync_readme_en.py
------------------
Automated sync script for English-default repository fork.
1. Syncs latest upstream Chinese README into README-zh.md
2. Detects new date entries added in README-zh.md
3. Translates missing date sections into English
4. Prepends translated sections into main English README.md
"""

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator

README_EN = "README.md"
README_ZH = "README-zh.md"

DATE_PATTERN_CN = re.compile(r"^###\s+(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*号添加")
DATE_PATTERN_EN = re.compile(r"^###\s+(?:Added\s+(?:on\s+)?)?([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})")

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

def fetch_upstream_chinese_readme():
    """Fetches latest upstream Chinese README and returns its content."""
    try:
        # Ensure upstream remote exists
        check_remote = subprocess.run(["git", "remote", "get-url", "upstream"], capture_output=True, text=True)
        if check_remote.returncode != 0:
            subprocess.run(["git", "remote", "add", "upstream", "https://github.com/1c7/chinese-independent-developer.git"], capture_output=True, text=True)

        res = subprocess.run(["git", "fetch", "upstream", "master"], capture_output=True, text=True)
        if res.returncode == 0:
            show_res = subprocess.run(["git", "show", "upstream/master:README.md"], capture_output=True, text=True)
            if show_res.returncode == 0 and len(show_res.stdout) > 1000:
                print("Successfully fetched latest upstream README.md via git!")
                return show_res.stdout
    except Exception as e:
        print(f"Git fetch notice: {e}")

    # Fallback to direct raw GitHub download if git fetch not possible
    try:
        import urllib.request
        url = "https://raw.githubusercontent.com/1c7/chinese-independent-developer/master/README.md"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode('utf-8')
            if len(content) > 1000:
                print("Successfully fetched latest upstream README.md via HTTP!")
                return content
    except Exception as e:
        print(f"HTTP download notice: {e}")

    raise RuntimeError("Unable to fetch upstream README.md")

def format_date_en(year, month, day):
    month_name = MONTH_NAMES[int(month)]
    return f"### Added on {month_name} {int(day)}, {year}"

def parse_chinese_sections(content):
    lines = content.splitlines(keepends=True)
    headers = []
    for idx, line in enumerate(lines):
        match = DATE_PATTERN_CN.match(line.strip())
        if match:
            year, month, day = match.groups()
            headers.append((int(year), int(month), int(day), idx))
    sections = {}
    for i, (year, month, day, start_idx) in enumerate(headers):
        end_idx = headers[i + 1][3] if i + 1 < len(headers) else len(lines)
        sections[(year, month, day)] = lines[start_idx:end_idx]
    return sections

def sections_needing_translation(previous_content, current_content):
    previous_sections = parse_chinese_sections(previous_content)
    current_sections = parse_chinese_sections(current_content)
    return [key for key, section in current_sections.items()
            if previous_sections.get(key) != section]

def english_section_ranges(content):
    lines = content.splitlines(keepends=True)
    headers = []
    for index, line in enumerate(lines):
        match = DATE_PATTERN_EN.match(line.strip())
        if match and match.group(1) in MONTH_NAMES:
            month = MONTH_NAMES.index(match.group(1))
            headers.append(((int(match.group(3)), month, int(match.group(2))), index))

    ranges = {}
    for i, (key, start_idx) in enumerate(headers):
        end_idx = headers[i + 1][1] if i + 1 < len(headers) else len(lines)
        ranges[key] = (start_idx, end_idx)
    return lines, ranges

def replace_english_sections(content, replacements):
    lines, ranges = english_section_ranges(content)
    for key, (start_idx, end_idx) in sorted(ranges.items(), reverse=True):
        if key in replacements:
            lines[start_idx:end_idx] = [replacements[key]]
    return "".join(lines)

def translate_line(translator, line):
    stripped = line.strip()
    if not stripped or stripped.startswith("http") or stripped.startswith("```"):
        return line
    if not any('\u4e00' <= char <= '\u9fff' for char in line):
        return line
    try:
        translated = translator.translate(line)
        return translated + '\n' if not translated.endswith('\n') else translated
    except Exception as e:
        return line

def translate_block(translator, block_lines):
    with ThreadPoolExecutor(max_workers=5) as executor:
        translated = list(executor.map(lambda l: translate_line(translator, l), block_lines))
    return translated

def sync():
    if not os.path.exists(README_EN):
        print("Error: README-zh.md or README.md missing.")
        return

    previous_zh_content = ""
    if os.path.exists(README_ZH):
        with open(README_ZH, "r", encoding="utf-8") as f:
            previous_zh_content = f.read()

    current_zh_content = fetch_upstream_chinese_readme()
    with open(README_ZH, "w", encoding="utf-8") as f:
        f.write(current_zh_content)

    zh_sections = parse_chinese_sections(current_zh_content)
    changed_sections = sections_needing_translation(previous_zh_content, current_zh_content)

    with open(README_EN, "r", encoding="utf-8") as f:
        en_content = f.read()

    _, en_ranges = english_section_ranges(en_content)
    if not changed_sections:
        print("Main English README.md is already 100% in sync with upstream!")
        return

    translator = GoogleTranslator(source="auto", target="en")
    replacements = {}
    new_sections = []
    for key in changed_sections:
        year, month, day = key
        section_lines = list(zh_sections[key])
        section_lines[0] = f"{format_date_en(year, month, day)}\n"
        translated_section = "".join(translate_block(translator, section_lines))
        print(f"Translating changed upstream section: Added on {MONTH_NAMES[month]} {day}, {year}")
        if key in en_ranges:
            replacements[key] = translated_section
        else:
            new_sections.append(translated_section)

    en_content = replace_english_sections(en_content, replacements)

    if not new_sections:
        with open(README_EN, "w", encoding="utf-8") as f:
            f.write(en_content)
        print(f"Successfully updated {len(replacements)} changed section(s) in English README.md!")
        return

    en_lines = en_content.splitlines(keepends=True)
    insert_idx = -1
    for idx, line in enumerate(en_lines):
        if line.strip().startswith("## 3."):
            insert_idx = idx + 1
            if insert_idx < len(en_lines) and not en_lines[insert_idx].strip():
                insert_idx += 1
            break

    if insert_idx != -1:
        new_en_lines = en_lines[:insert_idx] + ["\n".join(new_sections) + "\n"] + en_lines[insert_idx:]
        with open(README_EN, "w", encoding="utf-8") as f:
            f.writelines(new_en_lines)
        print(f"Successfully synced {len(changed_sections)} changed section(s) into English README.md!")
    else:
        print("Warning: Could not find '## 3. Project List' section header in README.md.")

if __name__ == "__main__":
    sync()
