# -*- coding: utf-8 -*-
"""临时脚本：把 docs 下的 PDF / DOCX 提取为纯文本，便于阅读。"""
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF

DOCS = Path(r"D:\2026cumcm\docs")
OUT = Path(r"D:\2026cumcm\codes\_extracted")
OUT.mkdir(exist_ok=True)


def extract_pdf(src: Path) -> str:
    parts = []
    with fitz.open(src) as doc:
        for i, page in enumerate(doc):
            parts.append(f"\n===== Page {i + 1} =====\n")
            parts.append(page.get_text("text"))
    return "".join(parts)


def extract_docx(src: Path) -> str:
    """不依赖 python-docx：直接解压并解析 word/document.xml。"""
    with zipfile.ZipFile(src) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"</w:tc>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


for f in sorted(DOCS.iterdir()):
    if f.suffix.lower() == ".pdf":
        txt = extract_pdf(f)
    elif f.suffix.lower() == ".docx":
        txt = extract_docx(f)
    else:
        continue
    dst = OUT / (f.stem + ".txt")
    dst.write_text(txt, encoding="utf-8")
    print(f"{f.name} -> {dst.name}  ({len(txt)} chars)")
