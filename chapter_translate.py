"""
epub 整書批次翻譯，逐章丟給本地 Ollama 翻譯，支援進度續跑

用法：
    python3 chapter_translate.py "/path/to/book.epub" --progress-dir progress_v2
    python3 chapter_translate.py "/path/to/book.epub" --progress-dir progress_v2 --limit 10

已經翻過的章節（progress-dir 底下已有對應 json）會自動跳過。
"""
from blocks import load_blocks, block_text
import argparse
import json
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"
MAX_RETRIES = 2

NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
}


def get_opf_path(zf: zipfile.ZipFile) -> str:
    container_xml = zf.read("META-INF/container.xml")
    root = ET.fromstring(container_xml)
    rootfile = root.find(".//container:rootfile", NS)
    return rootfile.attrib["full-path"]


def get_spine_items(zf: zipfile.ZipFile, opf_path: str):
    opf_data = zf.read(opf_path)
    root = ET.fromstring(opf_data)

    manifest = {}
    for item in root.findall(".//opf:manifest/opf:item", NS):
        manifest[item.attrib["id"]] = item.attrib["href"]

    spine_ids = [
        itemref.attrib["idref"]
        for itemref in root.findall(".//opf:spine/opf:itemref", NS)
    ]

    base_dir = "/".join(opf_path.split("/")[:-1])
    hrefs = []
    for sid in spine_ids:
        href = manifest.get(sid)
        if href is None:
            continue
        full_path = f"{base_dir}/{href}" if base_dir else href
        hrefs.append(full_path)
    return hrefs


GLOSSARY_PATH = Path(__file__).with_name("glossary.json")

def load_glossary() -> str:
    data = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    lines = [f"「{x['wrong']}」改用「{x['right']}」" for x in data.get("avoid", [])]
    lines += [f"{x['en']} 譯為「{x['zh']}」" for x in data.get("terms", [])]
    return "\n".join(lines)


GLOSSARY_TEXT = load_glossary()


def translate_text(text: str) -> str:
    prompt = (
        "你是專業書籍譯者，請將以下英文內容翻譯成台灣慣用的繁體中文，"
        "保持語意通順自然，稱呼讀者一律用「你」，不要用「您」，不要加註解或說明，直接輸出翻譯結果。\n"
        "用詞規則：\n"
        f"{GLOSSARY_TEXT}\n\n"
        f"{text}"
    )
    resp = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=1200,
    )
    resp.raise_for_status()
    result = resp.json().get("response", "").strip()
    if not result:
        raise ValueError("模型回傳空字串")
    return result


def load_progress(progress_dir: Path, index: int):
    path = progress_dir / f"{index:03d}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_progress(progress_dir: Path, index: int, data: dict):
    path = progress_dir / f"{index:03d}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def check_coverage(soup, texts):
    body_chars = len("".join((soup.body or soup).get_text().split()))
    block_chars = sum(len(t.replace(" ", "")) for t in texts)
    return block_chars, body_chars


def translate_chapter(progress_dir, idx, chapter_path, blocks, texts, existing):
    entries = None
    if existing and len(existing.get("blocks", [])) == len(texts):
        old = existing["blocks"]
        if all(e["original"] == t for e, t in zip(old, texts)):
            entries = old
    if entries is None:
        entries = [
            {"i": i, "tag": b.name, "original": t, "translated": "", "failed": False}
            for i, (b, t) in enumerate(zip(blocks, texts))
        ]

    total = len(entries)
    for n, entry in enumerate(entries, 1):
        if entry["translated"]:
            continue
        entry["failed"] = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                entry["translated"] = translate_text(entry["original"])
                break
            except Exception as e:
                print(f"[{idx:03d}] 區塊 {n}/{total} 第 {attempt} 次失敗：{e}")
                time.sleep(2)
        if not entry["translated"]:
            entry["failed"] = True
        save_progress(
            progress_dir,
            idx,
            {"chapter_path": chapter_path, "skipped": False, "done": False, "blocks": entries},
        )
        print(f"[{idx:03d}] 區塊 {n}/{total} {'失敗' if entry['failed'] else '完成'}")

    failed_count = sum(1 for e in entries if e["failed"])
    save_progress(
        progress_dir,
        idx,
        {"chapter_path": chapter_path, "skipped": False, "done": failed_count == 0, "blocks": entries},
    )
    return failed_count


def main():
    parser = argparse.ArgumentParser(description="epub 整書批次翻譯")
    parser.add_argument("epub_path", help="epub 檔案路徑")
    parser.add_argument("--progress-dir", default="progress_v2", help="進度存放資料夾，預設 progress_v2")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 個未完成章節，測試用")
    args = parser.parse_args()

    progress_dir = Path(args.progress_dir)
    progress_dir.mkdir(exist_ok=True)

    try:
        zf = zipfile.ZipFile(args.epub_path)
    except FileNotFoundError:
        print(f"找不到檔案：{args.epub_path}", file=sys.stderr)
        sys.exit(1)

    opf_path = get_opf_path(zf)
    spine_items = get_spine_items(zf, opf_path)
    total = len(spine_items)
    print(f"共 {total} 個章節\n")

    todo = []
    for i in range(total):
        data = load_progress(progress_dir, i)
        if data is None or not data.get("done"):
            todo.append(i)

    print(f"已完成 {total - len(todo)} 章，剩餘 {len(todo)} 章待翻\n")

    if args.limit is not None:
        todo = todo[: args.limit]
        print(f"本次限制只跑 {len(todo)} 章\n")

    failed = {}

    for idx in todo:
        chapter_path = spine_items[idx]
        print(f"[{idx:03d}] 抽取 {chapter_path}")

        try:
            soup, blocks = load_blocks(zf, chapter_path)
        except Exception as e:
            print(f"[{idx:03d}] 抽取失敗：{e}\n")
            failed[idx] = "抽取失敗"
            continue

        texts = [block_text(b) for b in blocks]
        block_chars, body_chars = check_coverage(soup, texts)
        if block_chars != body_chars:
            print(f"[{idx:03d}] 警告：區塊字元 {block_chars} 與全文字元 {body_chars} 不一致，可能漏字")

        if not blocks:
            if body_chars:
                print(f"[{idx:03d}] 有文字但找不到區塊，不標記完成\n")
                failed[idx] = "有文字但找不到區塊"
                continue
            print(f"[{idx:03d}] 沒有文字內容，跳過並標記完成\n")
            save_progress(
                progress_dir,
                idx,
                {"chapter_path": chapter_path, "skipped": True, "done": True, "blocks": []},
            )
            continue

        failed_count = translate_chapter(
            progress_dir, idx, chapter_path, blocks, texts, load_progress(progress_dir, idx)
        )
        if failed_count:
            failed[idx] = f"{failed_count} 個區塊失敗"
            print(f"[{idx:03d}] 章節未完成，{failed_count} 個區塊失敗\n")
        else:
            print(f"[{idx:03d}] 完成並已存檔\n")

    print("本次批次結束")
    if failed:
        for i, reason in failed.items():
            print(f"章節 {i:03d}：{reason}")
        print("重跑同一個指令即可，已翻好的區塊會沿用，只重試失敗的")
    else:
        print("本次批次全部成功")


if __name__ == "__main__":
    main()
