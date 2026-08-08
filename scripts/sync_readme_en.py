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

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

def fetch_upstream_chinese_readme():
    """Tries fetching latest upstream README.md via git or curl."""
    try:
        # Ensure upstream remote exists
        check_remote = subprocess.run(["git", "remote", "get-url", "upstream"], capture_output=True, text=True)
        if check_remote.returncode != 0:
            subprocess.run(["git", "remote", "add", "upstream", "https://github.com/1c7/chinese-independent-developer.git"], capture_output=True, text=True)

        res = subprocess.run(["git", "fetch", "upstream", "master"], capture_output=True, text=True)
        if res.returncode == 0:
            show_res = subprocess.run(["git", "show", "upstream/master:README.md"], capture_output=True, text=True)
            if show_res.returncode == 0 and len(show_res.stdout) > 1000:
                with open(README_ZH, "w", encoding="utf-8") as f:
                    f.write(show_res.stdout)
                print("Successfully fetched latest upstream README.md into README-zh.md via git!")
                return
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
                with open(README_ZH, "w", encoding="utf-8") as f:
                    f.write(content)
                print("Successfully fetched latest upstream README.md into README-zh.md via HTTP!")
    except Exception as e:
        print(f"HTTP download notice: {e}")

def format_date_en(year, month, day):
    month_name = MONTH_NAMES[int(month)]
    return f"### Added on {month_name} {int(day)}, {year}"

def parse_date_headers(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    headers = []
    for idx, line in enumerate(lines):
        match = DATE_PATTERN_CN.match(line.strip())
        if match:
            year, month, day = match.groups()
            headers.append((int(year), int(month), int(day), idx))
    return lines, headers

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
    # 1. Fetch latest Chinese version from upstream into README-zh.md
    fetch_upstream_chinese_readme()

    if not os.path.exists(README_ZH) or not os.path.exists(README_EN):
        print("Error: README-zh.md or README.md missing.")
        return

    zh_lines, zh_headers = parse_date_headers(README_ZH)

    with open(README_EN, "r", encoding="utf-8") as f:
        en_content = f.read()

    # Extract all existing dates from English README.md
    en_dates_found = set()
    en_date_matches = re.findall(r"^###\s+(?:Added\s+(?:on\s+)?)?([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", en_content, re.MULTILINE)
    for month_str, day_str, year_str in en_date_matches:
        if month_str in MONTH_NAMES:
            month_num = MONTH_NAMES.index(month_str)
            en_dates_found.add((int(year_str), month_num, int(day_str)))

    missing_sections = []
    translator = GoogleTranslator(source="auto", target="en")

    for i, (year, month, day, start_idx) in enumerate(zh_headers):
        if (year, month, day) not in en_dates_found:
            end_idx = zh_headers[i + 1][3] if i + 1 < len(zh_headers) else len(zh_lines)
            section_lines = zh_lines[start_idx:end_idx]
            
            en_header = format_date_en(year, month, day)
            section_lines[0] = f"{en_header}\n"
            
            print(f"Found missing upstream section: Added on {MONTH_NAMES[month]} {day}, {year} ({len(section_lines)} lines)")
            translated_section = translate_block(translator, section_lines)
            missing_sections.append("".join(translated_section))

    if not missing_sections:
        print("Main English README.md is already 100% in sync with upstream!")
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
        new_en_lines = en_lines[:insert_idx] + ["\n".join(missing_sections) + "\n"] + en_lines[insert_idx:]
        with open(README_EN, "w", encoding="utf-8") as f:
            f.writelines(new_en_lines)
        print(f"Successfully synced {len(missing_sections)} missing section(s) into English README.md!")
    else:
        print("Warning: Could not find '## 3. Project List' section header in README.md.")

if __name__ == "__main__":
    sync()
