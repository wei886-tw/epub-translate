# ab_compare_v2.py
import re
import sys
import time
import zipfile
from pathlib import Path

import requests
from opencc import OpenCC

from blocks import load_blocks, block_text

if len(sys.argv) != 4:
    print("用法：python3 ab_compare_v2.py <epub 路徑> <導言檔在 epub 內的路徑> <第一章檔在 epub 內的路徑>")
    sys.exit(1)

EPUB, INTRO, CH1 = sys.argv[1:4]
SAMPLES = [
    (INTRO, lambda bs: bs[2:12]),
    (CH1, lambda bs: [b for b in bs if len(block_text(b)) >= 60][:10]),
]

QWEN_PROMPT = (
    "你是專業書籍譯者，請將以下英文內容翻譯成台灣慣用的繁體中文，保持語意通順自然。"
    "原文的第一人稱（I）譯為「我」，稱呼讀者（you）才用「你」，不要用「您」。"
    "不要加註解或說明，直接輸出翻譯結果。\n\n"
)
GEMMA_PROMPT = (
    "You are a professional English (en) to Traditional Chinese (zh-Hant) translator. "
    "Convey the meaning and nuances of the original text accurately. "
    "Output only the translation.\n\n"
)
MODELS = [
    {"name": "qwen2.5:latest", "prompt": QWEN_PROMPT, "extra": {}},
    {"name": "translategemma:12b", "prompt": GEMMA_PROMPT, "extra": {}},
    {"name": "qwen3.5:9b", "prompt": QWEN_PROMPT, "extra": {"think": False}},
]
REPLACE = {"高亮": "螢光標示", "下劃線": "底線"}

cc = OpenCC("s2twp")
cc_chars = OpenCC("s2t")


def translate(model, text):
    payload = {
        "model": model["name"],
        "prompt": model["prompt"] + text,
        "stream": False,
        "options": {"temperature": 0},
        **model["extra"],
    }
    r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=600)
    r.raise_for_status()
    return r.json().get("response", "").strip()


def post(text):
    text = cc.convert(text)
    for old, new in REPLACE.items():
        text = text.replace(old, new)
    return text


def simplified_chars(raw):
    return sum(1 for a, b in zip(raw, cc_chars.convert(raw)) if a != b)


zf = zipfile.ZipFile(EPUB)
texts = []
for path, pick in SAMPLES:
    _, blocks = load_blocks(zf, path)
    texts += [block_text(b) for b in pick(blocks)]
print(f"共 {len(texts)} 個區塊")

results = {}
for model in MODELS:
    print(model["name"], "暖機中")
    translate(model, "Hello.")
    rows = []
    for i, text in enumerate(texts, 1):
        start = time.perf_counter()
        try:
            raw = translate(model, text)
        except Exception as e:
            raw = f"[錯誤] {e}"
        rows.append((raw, time.perf_counter() - start))
        print(f"  {i}/{len(texts)}")
    results[model["name"]] = rows

lines = []
for i, text in enumerate(texts):
    lines.append(f"## 區塊 {i + 1}\n\n原文：{text}\n")
    for model in MODELS:
        raw, sec = results[model["name"]][i]
        lines.append(f"- {model['name']}（{sec:.1f} 秒）：{post(raw)}")
    lines.append("")

lines.append("## 統計\n")
for model in MODELS:
    rows = results[model["name"]]
    total = sum(s for _, s in rows)
    english = sum(len(re.findall(r"[A-Za-z]{3,}", post(r))) for r, _ in rows)
    simp = sum(simplified_chars(r) for r, _ in rows)
    short = sum(1 for (r, _), t in zip(rows, texts) if len(t) >= 100 and len(r) < 0.3 * len(t))
    lines.append(
        f"- {model['name']}：總耗時 {total:.1f} 秒，英文殘留 {english} 處，"
        f"簡體字 {simp} 個，疑似截斷 {short} 個"
    )

Path("ab_compare_v2.md").write_text("\n".join(lines), encoding="utf-8")
print("已輸出 ab_compare_v2.md")