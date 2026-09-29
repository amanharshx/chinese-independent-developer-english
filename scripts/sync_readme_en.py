#!/usr/bin/env python3
"""
sync_readme_en.py
------------------
Automated sync script for English-default repository fork.
1. Fetches the latest upstream Chinese README
2. Rebuilds the English README.md so its dated sections and footer mirror upstream
3. Reuses existing English sections that are unchanged upstream and still valid,
   translating everything else line by line
4. Writes README.md and README-zh.md only if every translation succeeded,
   so a failed run leaves both files untouched and is retried next time
"""

import os
import re
import subprocess
import sys
import time
from deep_translator import GoogleTranslator

README_EN = "README.md"
README_ZH = "README-zh.md"
LIST_HEADING = "## 3."

DATE_PATTERN_CN = re.compile(r"^###\s+(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*号添加")
DATE_PATTERN_EN = re.compile(r"^###\s+(?:Added\s+(?:on\s+)?)?([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})")
URL_PATTERN = re.compile(r"(?:https?://|\./)[^\s)\]]*[^\s)\].,;:!?，。]")
ERROR_MARKERS = ("Error 500", "That’s an error", "That's an error", "<html")

# Google's free endpoint rate-limits bursts, so requests are sent one at a time.
REQUEST_DELAY = 0.5
RETRY_DELAYS = (2, 5, 15, 30)

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

def parse_cn_date(line):
    match = DATE_PATTERN_CN.match(line.strip())
    if match:
        year, month, day = match.groups()
        return int(year), int(month), int(day)
    return None

def parse_en_date(line):
    match = DATE_PATTERN_EN.match(line.strip())
    if match and match.group(1) in MONTH_NAMES:
        return int(match.group(3)), MONTH_NAMES.index(match.group(1)), int(match.group(2))
    return None

def split_readme(content, parse_date):
    """Splits a README into (head, [(date, section lines)], tail).

    The head runs through the project list heading, each dated section runs until
    the next date or `## ` heading, and the tail starts at the first `## ` heading
    after the last dated section. Lines outside those parts are dropped.
    """
    lines = content.splitlines(keepends=True)
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith(LIST_HEADING)), None)
    if start is None:
        raise RuntimeError(f"Could not find '{LIST_HEADING}' heading")

    head = lines[:start]
    sections = []
    current = None
    tail_start = None
    for index in range(start, len(lines)):
        line = lines[index]
        key = parse_date(line)
        if key:
            current = [line]
            sections.append((key, current))
            tail_start = None
        elif line.startswith("## "):
            current = None
            if tail_start is None:
                tail_start = index
        elif current is not None:
            current.append(line)
        elif not sections:
            head.append(line)

    tail = lines[tail_start:] if tail_start is not None else []
    return head, sections, tail

def has_cjk(text):
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def needs_translation(line):
    return has_cjk(line) and not line.strip().startswith(("http", "```"))

def is_good_translation(source, translated):
    translated = translated.strip()
    return (bool(translated)
            and translated != source.strip()
            and not any(marker in translated for marker in ERROR_MARKERS)
            and sorted(URL_PATTERN.findall(source)) == sorted(URL_PATTERN.findall(translated)))

def is_valid_translation(source_lines, translated_lines):
    """Checks an existing English block line by line against its Chinese source.

    Blank lines are ignored, and matching links on every line catch translations
    that ended up on the wrong line.
    """
    source_lines = [line for line in source_lines if line.strip()]
    translated_lines = [line for line in translated_lines if line.strip()]
    if len(source_lines) != len(translated_lines):
        return False
    for source, translated in zip(source_lines, translated_lines):
        if needs_translation(source):
            if not is_good_translation(source, translated):
                return False
        elif sorted(URL_PATTERN.findall(source)) != sorted(URL_PATTERN.findall(translated)):
            return False
    return True

def restore_urls(source, translated):
    """Puts back source URLs that Google rewrote, e.g. eyeshapedetector -> eyeshapedector."""
    source_urls = URL_PATTERN.findall(source)
    if len(URL_PATTERN.findall(translated)) != len(source_urls):
        return translated
    urls = iter(source_urls)
    return URL_PATTERN.sub(lambda _: next(urls), translated)

def translate_line(translator, line):
    if not needs_translation(line):
        return line
    text = line.strip()
    indent = line[:len(line) - len(line.lstrip())]
    newline = "\n" if line.endswith("\n") else ""
    for delay in (*RETRY_DELAYS, None):
        time.sleep(REQUEST_DELAY)
        try:
            translated = restore_urls(text, translator.translate(text))
        except Exception as error:
            problem = repr(error)
        else:
            if is_good_translation(text, translated):
                return indent + translated.strip() + newline
            problem = f"unusable result {translated!r}"
        if delay is None:
            break
        print(f"  Retrying in {delay}s ({problem})")
        time.sleep(delay)
    raise RuntimeError(f"Could not translate line: {text}\nLast problem: {problem}")

def translate_block(translator, block_lines):
    return [translate_line(translator, line) for line in block_lines]

def build_english_readme(previous_zh_content, current_zh_content, en_content, translator):
    """Returns the rebuilt English README; raises if any translation fails."""
    _, zh_sections, zh_tail = split_readme(current_zh_content, parse_cn_date)
    previous_sections, previous_tail = {}, None
    if previous_zh_content:
        _, previous_list, previous_tail = split_readme(previous_zh_content, parse_cn_date)
        previous_sections = dict(previous_list)
    en_head, en_sections, en_tail = split_readme(en_content, parse_en_date)

    en_candidates = {}
    for key, lines in en_sections:
        en_candidates.setdefault(key, []).append(lines)

    body = []
    translated_count = 0
    for key, zh_lines in zh_sections:
        source = [f"{format_date_en(*key)}\n"] + zh_lines[1:]
        reused = None
        if previous_sections.get(key) == zh_lines:
            reused = next((lines for lines in en_candidates.get(key, [])
                           if is_valid_translation(source, lines)), None)
        if reused is None:
            print(f"Translating section: Added on {MONTH_NAMES[key[1]]} {key[2]}, {key[0]}")
            reused = translate_block(translator, source)
            translated_count += 1
        body.extend(reused)

    tail = en_tail
    if previous_tail != zh_tail or not is_valid_translation(zh_tail, en_tail):
        print("Translating footer")
        tail = translate_block(translator, zh_tail)
        translated_count += 1

    print(f"Translated {translated_count} block(s), reused {len(zh_sections) + 1 - translated_count}.")
    return "".join(en_head + body + tail)

def sync():
    if not os.path.exists(README_EN):
        print("Error: README.md missing.")
        sys.exit(1)

    previous_zh_content = ""
    if os.path.exists(README_ZH):
        with open(README_ZH, "r", encoding="utf-8") as f:
            previous_zh_content = f.read()
    with open(README_EN, "r", encoding="utf-8") as f:
        en_content = f.read()

    current_zh_content = fetch_upstream_chinese_readme()
    translator = GoogleTranslator(source="auto", target="en")
    new_en_content = build_english_readme(previous_zh_content, current_zh_content, en_content, translator)

    with open(README_EN, "w", encoding="utf-8") as f:
        f.write(new_en_content)
    with open(README_ZH, "w", encoding="utf-8") as f:
        f.write(current_zh_content)
    print("English README.md is in sync with upstream.")

if __name__ == "__main__":
    sync()
