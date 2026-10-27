# blocks.py
import zipfile
from bs4 import BeautifulSoup, NavigableString

BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6",
              "li", "blockquote", "figcaption", "dt", "dd", "td", "th", "div"]


def block_text(tag) -> str:
    return " ".join(tag.get_text().split())


def _inline_text(node) -> str:
    return str(node) if isinstance(node, NavigableString) else node.get_text()


def wrap_orphans(soup):
    # 容器自己直接寫的文字（外層又包著子區塊）包進 span，讓它也成為區塊
    for t in list(soup.find_all(BLOCK_TAGS)):
        if not t.find(BLOCK_TAGS):
            continue
        group = []
        for child in list(t.children) + [None]:
            if child is not None and (
                isinstance(child, NavigableString)
                or (child.name not in BLOCK_TAGS and not child.find(BLOCK_TAGS))
            ):
                group.append(child)
                continue
            if "".join(_inline_text(g) for g in group).strip():
                span = soup.new_tag("span")
                span["data-orphan"] = "1"
                group[0].insert_before(span)
                for g in group:
                    span.append(g.extract())
            group = []


def is_block(t) -> bool:
    if t.has_attr("data-orphan"):
        return bool(block_text(t))
    return t.name in BLOCK_TAGS and not t.find(BLOCK_TAGS) and bool(block_text(t))


def load_blocks(zf: zipfile.ZipFile, chapter_path: str):
    soup = BeautifulSoup(zf.read(chapter_path), "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    wrap_orphans(soup)
    return soup, soup.find_all(is_block)