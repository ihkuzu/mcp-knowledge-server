import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import snowballstemmer

STOPWORDS = set(
    "a an the and or but if of to in on at for from by with without about into over under is are was were be "
    "been being do does did can could should would will shall may might must i me my we our you your he she "
    "it its they them their this that these those what which who whom when where why how there here not no "
    "yes so than then too very just also any all some each other only own same such up down out off again "
    "after before during once more most much many still get got has have had".split()
)
_STEMMER = snowballstemmer.stemmer("english")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def stem(word: str) -> str:
    return _STEMMER.stemWord(word)


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


@dataclass
class Chunk:
    doc: str
    title: str
    section: str
    text: str


@dataclass
class Hit:
    doc: str
    title: str
    section: str
    score: float
    text: str


def split_sections(name: str, markdown: str) -> list[Chunk]:
    title = name
    chunks: list[Chunk] = []
    section, lines = "", []

    def flush():
        body = "\n".join(lines).strip()
        if body:
            chunks.append(Chunk(name, title, section or title, body))

    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section, lines = line[3:].strip(), []
        else:
            lines.append(line)
    flush()
    return chunks


class DocIndex:
    """BM25 over markdown sections."""

    def __init__(self, docs_dir: Path, k1: float = 1.5, b: float = 0.75):
        self.docs_dir = docs_dir
        self.k1, self.b = k1, b
        self.docs: dict[str, str] = {}
        self.chunks: list[Chunk] = []
        for path in sorted(docs_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.docs[path.stem] = text
            self.chunks.extend(split_sections(path.stem, text))
        # the title and heading are indexed with the body so short sections still match
        self._tf = [Counter(tokenize(f"{c.title} {c.section} {c.text}")) for c in self.chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = sum(self._len) / max(len(self._len), 1)
        df = Counter(term for tf in self._tf for term in tf)
        n = len(self.chunks)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[Hit]:
        terms = tokenize(query)
        scored = []
        for i, tf in enumerate(self._tf):
            score = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    norm = self.k1 * (1 - self.b + self.b * self._len[i] / self._avg)
                    score += self._idf[t] * f * (self.k1 + 1) / (f + norm)
            if score > min_score:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [
            Hit(self.chunks[i].doc, self.chunks[i].title, self.chunks[i].section, round(s, 3), self.chunks[i].text)
            for s, i in scored[:k]
        ]

    def list_docs(self) -> list[dict]:
        out = []
        for name, text in self.docs.items():
            title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), name)
            sections = [c.section for c in self.chunks if c.doc == name]
            out.append({"name": name, "title": title, "sections": sections})
        return out

    def read(self, name: str) -> str:
        # names come from the client, so only plain slugs that are already indexed are allowed
        if not NAME_RE.match(name) or name not in self.docs:
            raise KeyError(name)
        return self.docs[name]
