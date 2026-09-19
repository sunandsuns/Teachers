"""TF-IDF 检索器：对中文文本进行关键词检索和相似度排序。"""

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Optional

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


#: 两类检索来源。
#: - NOTES：深读笔记，经过提炼，是回答"人生问题"的主力
#: - SOURCE：原典全文，用于找到经文原句
KIND_NOTES = "notes"
KIND_SOURCE = "source"

#: 原典条目的得分权重。笔记是提炼过的、更贴问题，故让原典略低于笔记，
#: 避免大段古文把精炼的解读挤下去。
SOURCE_WEIGHT = 0.85

#: 各书原典在 ``SOURCE_WEIGHT`` 之上再乘一次的折减。
#: 卦爻辞、编年史这类碎片离了语境几乎没有指导意义，却因为篇幅大、文言词
#: 密集，恰恰是词面检索里最容易冒头的东西——不压住它们，问一句"我最近很
#: 焦虑"回来的会是《易经》某卦的白话解释。
SOURCE_BOOK_WEIGHT: Mapping[str, float] = {
    "01": 0.55,  # 易经：卦爻辞 + 逐句白话，碎片化最严重
    "03": 0.5,   # 奇门遁甲：术数表格
    "05": 0.5,   # 毛泽东选集：现代政论
    "13": 0.7,   # 史记：叙事
    "14": 0.7,   # 资治通鉴：编年叙事
}

#: 单本书原典进入索引的字符上限。
#: 《资治通鉴》321 万字、《史记》60 万字，全量入索引会让建索引耗时与
#: 内存大幅上升，而且正史叙事对"人生困惑"的召回价值有限——
#: 这类书仍可全文阅读，检索则以笔记为主。
SOURCE_INDEX_MAX_CHARS = 250_000

#: 建索引时整段丢弃的噪声单元。
#: 语料里混着仓库 README 之类自动生成的说明（"本项目创建于……最近的一次
#: 更新时间为……"），它们讲的不是经典，却因为用词普通、篇幅适中而在词面
#: 检索里稳定冒头，还常常排在真正有用的段落前面。丢掉它们比留着降权干净。
_NOISE_UNIT_RE = re.compile(
    r"本项目创建于|本仓库创建于|最近的一次更新|最后更新时间|Last updated",
)

#: 目录页。整段都是"卷十""论行幸第三十七"这类篇目名，一个字的内容都没有。
#: 它们排在检索结果里看着像原文，实际上引不出任何句子——模型拿到只能绕开。
#: 用密度判定（标记够多、且几乎占满整段）而不是命中即丢，免得误伤正文里
#: 偶尔出现的"第三章"。
# 篇目名的写法有两种：「卷十」「第九章」这种带单位的，以及「议征伐第三十五」
# 这种序号落在末尾的——后者在正史目录里更常见，只认前者会漏掉整页目录。
_TOC_MARK_RE = re.compile(
    r"卷[一二三四五六七八九十百\d]+|第[一二三四五六七八九十百\d]{1,4}[章篇节回卷]?"
)
_TOC_MIN_MARKS = 6


@dataclass
class SearchResult:
    """单条检索结果。"""
    book_id: str
    book_title: str
    chapter_id: str
    chapter_title: str
    content: str           # 匹配段落文本
    score: float           # 相似度分数
    source: str            # 出处描述
    kind: str = KIND_NOTES  # 来源类型：notes / source
    offset: int = 0        # SOURCE 类型时，该段在原典全文中的字符位置


def _tokenize(text: str) -> list[str]:
    """中文分词：优先用 jieba，降级为字符级分词。"""
    if _HAS_JIEBA:
        words = jieba.cut_for_search(text)
        # 过滤停用词和单字符（保留2字以上词）
        return [w.strip() for w in words if len(w.strip()) >= 2]
    else:
        # 降级：按标点分段，取2-4字滑窗
        segments = re.split(r'[，。！？；\n\s,.;!?]+', text)
        tokens = []
        for seg in segments:
            seg = seg.strip()
            for i in range(len(seg)):
                for w in range(2, min(5, len(seg) - i + 1)):
                    tokens.append(seg[i:i+w])
        return tokens


def _is_toc(text: str) -> bool:
    """整段是不是目录页。

    判定看**去掉篇目名之后还剩多少字**：目录页剩下的只有"议征伐""论行幸"
    这类三四个字的条目名，正文则剩下一大段。只数标记会误伤连续引用多个
    章节的正文段落（深解里常出现"第九章……第六十四章"）。
    """
    marks = _TOC_MARK_RE.findall(text)
    if len(marks) < _TOC_MIN_MARKS:
        return False
    residual = re.sub(r"\s+", "", _TOC_MARK_RE.sub("", text))
    return len(residual) <= len(marks) * 6


class TFIDFRetriever:
    """基于 TF-IDF 的全文检索器。"""

    def __init__(self):
        self.documents: list[dict] = []    # [{"doc_id", "book_id", ..., "content", "tokens", "kind", "weight", "offset"}]
        self.df: Counter = Counter()       # 文档频率
        self.tf: list[Counter] = []         # 每篇的词频
        self._indexed = False
        self._idf_cache: dict[str, float] = {}
        #: 预计算的文档向量与模长（build_index 时填充）
        self._doc_vecs: list[dict[str, float]] = []
        self._doc_norms: list[float] = []
        #: 原典入索引的情况（哪几本入了、哪几本因体量被跳过），供健康检查展示
        self.source_coverage: dict[str, list[str]] = {"indexed": [], "skipped": []}

    def add_document(self, book_id: str, book_title: str,
                     chapter_id: str, chapter_title: str, content: str,
                     *, kind: str = KIND_NOTES, weight: float = 1.0,
                     offset: int = 0) -> None:
        """添加文档到索引。

        ``kind`` / ``weight`` / ``offset`` 供原典条目使用：原典需要标明来源类型、
        降低权重，并记录该段在全文中的位置以便前端跳转。
        """
        # 将长章节按段落拆分为更小的检索单元
        paragraphs = self._split_paragraphs(content)
        cursor = offset
        for i, para in enumerate(paragraphs):
            para_start = cursor
            cursor += len(para) + 2  # 近似还原段落间的分隔长度
            if len(para.strip()) < 10:
                continue
            if _NOISE_UNIT_RE.search(para) or _is_toc(para):
                continue
            tokens = _tokenize(para)
            if not tokens:
                continue
            doc_id = f"{book_id}-{chapter_id}-{i:02d}"
            self.documents.append({
                "doc_id": doc_id,
                "book_id": book_id,
                "book_title": book_title,
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "content": para,
                "tokens": tokens,
                "kind": kind,
                "weight": weight,
                "offset": para_start,
            })
            tf = Counter(tokens)
            self.tf.append(tf)
            for term in tf:
                self.df[term] += 1

    #: 单个检索单元的最大字符数。原典里常有整卷不带空行的情况，
    #: 不切分会得到几万字的巨型片段，既慢又对不上问题。
    MAX_UNIT_CHARS = 400

    def _split_paragraphs(self, text: str) -> list[str]:
        """将文本拆成检索单元：先按标题/空行分段，过长的段再按句切分。"""
        parts = re.split(r'\n##\s+|\n\n+', text)
        units: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= self.MAX_UNIT_CHARS:
                units.append(part)
                continue
            units.extend(self._split_long(part))
        return units

    def _split_long(self, text: str) -> list[str]:
        """把超长段落按句号/换行切成不超过 ``MAX_UNIT_CHARS`` 的块。"""
        sentences = re.split(r'(?<=[。！？；\n])', text)
        chunks: list[str] = []
        buffer = ""
        for sentence in sentences:
            if buffer and len(buffer) + len(sentence) > self.MAX_UNIT_CHARS:
                chunks.append(buffer.strip())
                buffer = ""
            buffer += sentence
        if buffer.strip():
            chunks.append(buffer.strip())
        return [c for c in chunks if c]

    def _compute_idf(self, term: str) -> float:
        """计算逆文档频率。"""
        if term in self._idf_cache:
            return self._idf_cache[term]
        n = len(self.documents)
        if n == 0:
            return 0.0
        df = self.df.get(term, 0)
        if df == 0:
            idf = 0.0
        else:
            idf = math.log((n + 1) / (df + 1)) + 1  # 平滑处理
        self._idf_cache[term] = idf
        return idf

    def build_index(self) -> None:
        """构建索引：预计算每个文档的 TF-IDF 向量与模长。

        检索时不再逐文档重算向量——8000+ 检索单元的规模下，
        把这一步从"每次查询"挪到"建索引一次"，单次查询快一个数量级。
        """
        self._idf_cache.clear()
        for term in self.df:
            self._compute_idf(term)

        self._doc_vecs: list[dict[str, float]] = []
        self._doc_norms: list[float] = []
        for tf in self.tf:
            vec = {
                term: count * self._compute_idf(term)
                for term, count in tf.items()
                if self._compute_idf(term) > 0
            }
            self._doc_vecs.append(vec)
            self._doc_norms.append(math.sqrt(sum(v * v for v in vec.values())))
        self._indexed = True

    def search(
        self,
        query: str,
        top_k: int = 5,
        kind: Optional[str] = None,
        book_weights: Optional[Mapping[str, float]] = None,
    ) -> list[SearchResult]:
        """检索与 query 最相关的 top_k 个段落。

        ``kind`` 限定来源类型（``notes`` / ``source``），None 表示不限。

        ``book_weights`` 按 ``book_id`` 给结果乘一个系数。**默认不用**——
        「寻章」要的是全库召回，一碗水端平；只有「求教」才需要它把语料里
        篇幅最大、却最不对口的那几本压下去（见 ``services/advice.py``）。
        """
        if not self.documents:
            return []

        # 有文档但向量未同步（例如 build_index 之后又 add_document），补建一次
        if len(self._doc_vecs) != len(self.documents):
            self.build_index()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # 计算 query 的 TF-IDF 向量
        query_tf = Counter(query_tokens)
        query_vec: dict[str, float] = {}
        for term, count in query_tf.items():
            idf = self._compute_idf(term)
            if idf > 0:
                query_vec[term] = count * idf

        if not query_vec:
            # 降级：直接子串匹配
            return self._substring_search(query, top_k, kind)

        query_norm = math.sqrt(sum(v * v for v in query_vec.values()))
        results: list[SearchResult] = []

        for i, doc in enumerate(self.documents):
            if kind is not None and doc.get("kind", KIND_NOTES) != kind:
                continue

            doc_vec = self._doc_vecs[i]
            doc_norm = self._doc_norms[i]
            if doc_norm == 0 or query_norm == 0:
                continue

            # 余弦相似度：只需遍历 query 的稀疏非零项
            dot = sum(value * doc_vec.get(term, 0.0) for term, value in query_vec.items())
            # 来源权重：让精炼过的笔记略高于原典
            score = dot / (query_norm * doc_norm) * doc.get("weight", 1.0)
            if book_weights:
                score *= book_weights.get(doc["book_id"], 1.0)

            if score > 0:
                results.append(self._to_result(doc, score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _to_result(doc: dict, score: float) -> SearchResult:
        return SearchResult(
            book_id=doc["book_id"],
            book_title=doc["book_title"],
            chapter_id=doc["chapter_id"],
            chapter_title=doc["chapter_title"],
            content=doc["content"][:500],  # 截取前500字
            score=score,
            source=TFIDFRetriever._describe(doc),
            kind=doc.get("kind", KIND_NOTES),
            offset=doc.get("offset", 0),
        )

    @staticmethod
    def _describe(doc: dict) -> str:
        """出处描述。原典条目直接标"原典"，避免与笔记章节混为一谈。"""
        if doc.get("kind") == KIND_SOURCE:
            return f'《{doc["book_title"]}》· 原典'
        return f'《{doc["book_title"]}》· {doc["chapter_title"]}'

    def _substring_search(self, query: str, top_k: int, kind: Optional[str] = None) -> list[SearchResult]:
        """降级：子串匹配。"""
        results: list[SearchResult] = []
        for doc in self.documents:
            if kind is not None and doc.get("kind", KIND_NOTES) != kind:
                continue
            if query in doc["content"]:
                results.append(self._to_result(doc, doc.get("weight", 1.0)))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


# 全局单例
_retriever: Optional[TFIDFRetriever] = None


def get_retriever() -> TFIDFRetriever:
    """获取全局检索器单例。"""
    global _retriever
    if _retriever is None:
        _retriever = TFIDFRetriever()
        _retriever.build_index()
    return _retriever


def build_retriever_from_loader(loader, *, include_source: bool = True) -> TFIDFRetriever:
    """从内容加载器构建检索器。

    笔记每章入索引；``include_source`` 为真时，体量适中的原典全文也一并入索引，
    这样「寻章」才能真正做到"跨全库"——既找得到解读，也找得到原句。
    """
    global _retriever
    retriever = TFIDFRetriever()
    indexed_source: list[str] = []
    skipped_source: list[str] = []

    for book in loader.get_books():
        for ch in book.chapters:
            retriever.add_document(
                book_id=book.book_id,
                book_title=book.title,
                chapter_id=ch.chapter_id,
                chapter_title=ch.title,
                content=ch.content,
            )

        if not include_source or not book.source_file:
            continue
        text = loader.get_source_text(book.book_id)
        if not text:
            continue
        if len(text) > SOURCE_INDEX_MAX_CHARS:
            skipped_source.append(book.title)
            continue
        retriever.add_document(
            book_id=book.book_id,
            book_title=book.title,
            chapter_id="source",
            chapter_title="原典",
            content=text,
            kind=KIND_SOURCE,
            weight=SOURCE_WEIGHT * SOURCE_BOOK_WEIGHT.get(book.book_id, 1.0),
        )
        indexed_source.append(book.title)

    retriever.build_index()
    retriever.source_coverage = {
        "indexed": indexed_source,
        "skipped": skipped_source,
    }
    _retriever = retriever
    return retriever


def reset_retriever() -> None:
    """丢弃全局单例（测试与热重载用）。"""
    global _retriever
    _retriever = None


#: 惰性构建的互斥锁。首次构建要几秒，并发到来的请求不该各建一份。
_build_lock = threading.Lock()


def ensure_retriever(loader=None) -> TFIDFRetriever:
    """返回可用的检索器，尚未构建时惰性构建。

    应用启动（lifespan）、``/api/search``、``/api/ask`` 原先各写了一份
    「没有就构建」，三处必须保持一致才有意义——**收拢到这里**，顺带补上并发保护：
    启动流程与首个请求、或两个同时到达的请求，都可能在同一瞬间发现索引是空的。

    ``loader`` 省略时才去取全局单例，调用方（如应用启动流程）可以注入自己的
    加载器，便于测试替换。

    幂等：已构建则原样返回，不会重建。
    """
    retriever = get_retriever()
    if retriever.documents:
        return retriever

    with _build_lock:
        # 双重检查：等锁期间可能已被别的线程建好，此时再建一次纯属浪费几秒
        retriever = get_retriever()
        if retriever.documents:
            return retriever

        if loader is None:
            from .content_loader import get_loader  # 局部导入，避免模块级循环依赖

            loader = get_loader()
        return build_retriever_from_loader(loader)
