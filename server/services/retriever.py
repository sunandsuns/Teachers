"""TF-IDF 检索器：对中文文本进行关键词检索和相似度排序。"""

import math
import re
import threading
from collections import Counter, OrderedDict
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
#: 用户私人书架里的书。只有元信息与模型生成的导读，没有全书正文——
#: 它由 :mod:`services.unified_search` 装进一个独立的子索引，不混进公共语料。
KIND_SHELF = "shelf"

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

#: 只有一个标题、没有正文的检索单元。
#: 笔记里的三级标题（"### 3. 修心：事来心现，事去心空"）只要前后有空行，
#: 就会被单独切成一段；它有十几个字，过得了"长度 ≥10"那道闸，于是堂而皇之
#: 进了索引。检索命中它，返回的是一条**没有内容**的结果：寻章页点开是空的，
#: 求教时模型也把它当一份材料，只能忽略或硬凑。判定只看一件事——整段是不是
#: 单独一行标题；标题下面还带着正文的段落不受影响。
_HEADING_ONLY_RE = re.compile(r"^#{1,6}\s+\S")

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

#: 查询结果缓存的条数上限。
#: 检索曾经是"每次查询都把 8534 篇文档走一遍"，换成倒排表之后单次只剩一两毫秒，
#: 缓存省下的绝对值不大；真正值钱的是**同一路查询会被反复执行**的地方——
#: 「求教」每次都要跑"主题锚那一路"，而它的查询文本与权重**只由主题决定**
#: （八个主题的组合就那么几种），跑一次就该记下来。寻章页"返回再搜一次"同理。
#: 上限 128：一条结果最多几十个小对象，整块缓存撑死几 MB。
RESULT_CACHE_MAX = 128


@dataclass(frozen=True)
class SearchResult:
    """单条检索结果。

    **不可变**：``search()`` 会把结果放进查询缓存里复用，而返回给调用方的是
    浅拷贝——列表是新的，元素还是同一批对象。元素若可变，某处随手写一句
    ``result.score = ...`` 就会把缓存里的分数一起改掉，下一个拿到同一份结果的
    请求看到的是被改过的排序。这种 bug 不报错、只让结果莫名漂移。
    要改分数请用 ``dataclasses.replace``（``advice.merge_passes`` 就是这么做的）。
    """
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
        self._idf_cache: dict[str, float] = {}
        #: **倒排表**：词项 → (文档下标数组, 该文档里这个词的 TF-IDF 权重数组)。
        #: 检索只遍历"含某个查询词项"的那几篇，而不是全部 8534 篇——实测
        #: 平均每个词项只命中 7 篇。写成两个平行数组而不是 list[tuple]，
        #: 是为了省掉 60 万个元组对象。
        self._postings: dict[str, tuple[list[int], list[float]]] = {}
        #: 每篇文档的向量模长，与倒排表一起在 build_index 时算好。
        self._doc_norms: list[float] = []
        #: build_index 完成时 ``documents`` 的长度。与当前长度对不上就说明
        #: 索引过期（建完之后又 add_document 了），检索前要重建。
        self._indexed_count = 0
        #: 查询结果缓存（LRU，见 :data:`RESULT_CACHE_MAX`）。
        #: 索引一变就整体作废——缓存里的结果指向的是旧的下标。
        self._result_cache: "OrderedDict[tuple, list[SearchResult]]" = OrderedDict()
        #: 索引里出现过的书 id，惰性算一次（``add_document`` 时置空）。
        #: 「求教」每次检索都要按书给权重，原先每次都把 8534 篇扫一遍取 book_id。
        self._book_ids: Optional[frozenset] = None
        #: 原典入索引的情况（哪几本入了、哪几本因体量被跳过），供健康检查展示
        self.source_coverage: dict[str, list[str]] = {"indexed": [], "skipped": []}

    @property
    def book_ids(self) -> frozenset:
        """索引里出现过的书 id（惰性缓存）。

        只读用途，返回 ``frozenset`` 是为了避免调用方无意间改到缓存。
        """
        if self._book_ids is None:
            self._book_ids = frozenset(doc["book_id"] for doc in self.documents)
        return self._book_ids

    def add_document(self, book_id: str, book_title: str,
                     chapter_id: str, chapter_title: str, content: str,
                     *, kind: str = KIND_NOTES, weight: float = 1.0,
                     offset: int = 0) -> None:
        """添加文档到索引。

        ``kind`` / ``weight`` / ``offset`` 供原典条目使用：原典需要标明来源类型、
        降低权重，并记录该段在全文中的位置以便前端跳转。
        """
        # 文档集合要变了：缓存里的结果指向的是旧下标，书 id 集合也不再作数。
        # 建索引时本方法会被调用八千多次，所以清缓存前先判空（空字典的
        # 真值判断只是读一个长度字段，比无条件 clear() 便宜得多）。
        self._book_ids = None
        if self._result_cache:
            self._result_cache.clear()
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
            if _HEADING_ONLY_RE.match(para.strip()) and "\n" not in para.strip():
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
        """构建索引：算出每篇文档的模长，并把文档向量转置成倒排表。

        检索时不再逐文档重算向量——8000+ 检索单元的规模下，
        把这一步从"每次查询"挪到"建索引一次"，单次查询快一个数量级。

        转置成倒排表（词项 → 命中它的文档）又在此基础上快了一个数量级：
        检索的内层循环从"8534 篇 × 每个词项"降到"每个词项 × 它真正命中的篇数"
        （实测平均每个词项只命中 7 篇）。**转置不改变任何一个点积**——
        某篇文档的加法次序仍按查询词项的顺序进行，与逐篇扫描时完全一致，
        所以分数是逐位相同的。``tests/unit/test_retriever.py`` 的
        ``TestSearchConsistency`` 就是钉这一点的。
        """
        if self._result_cache:
            self._result_cache.clear()
        self._idf_cache.clear()
        for term in self.df:
            self._compute_idf(term)
        # 取本地引用：字典推导式里若写 ``self._compute_idf(term)``，
        # 值表达式与 if 条件各调一次，60 万次迭代下差 70ms 左右。
        idf = self._idf_cache

        postings: dict[str, tuple[list[int], list[float]]] = {}
        norms: list[float] = []
        for i, tf in enumerate(self.tf):
            vec = {
                term: count * idf[term]
                for term, count in tf.items()
                if idf.get(term, 0.0) > 0
            }
            for term, value in vec.items():
                entry = postings.get(term)
                if entry is None:
                    entry = ([], [])
                    postings[term] = entry
                entry[0].append(i)
                entry[1].append(value)
            # 模长这一行一字未动：``sum()`` 在 3.12+ 对浮点用了补偿求和，
            # 换成手写累加会得到不同的最低位，进而让分数与旧结果对不上。
            norms.append(math.sqrt(sum(v * v for v in vec.values())))
        self._postings = postings
        self._doc_norms = norms
        self._indexed_count = len(self.documents)

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

        结果带 LRU 缓存（见 :data:`RESULT_CACHE_MAX`）。**返回的是浅拷贝**：
        调用方可以随意排序、切片，但不要就地改 ``SearchResult`` 的字段——
        那会写进缓存里，下一个拿到同一份结果的请求会看到被改过的分数。
        要改分数请用 ``dataclasses.replace``（``advice.merge_passes`` 就是这么做的）。
        """
        if not self.documents:
            return []

        cache_key = self._cache_key(query, top_k, kind, book_weights)
        cached = self._result_cache.get(cache_key)
        if cached is not None:
            self._result_cache.move_to_end(cache_key)
            return list(cached)

        # 有文档但索引未同步（例如 build_index 之后又 add_document），补建一次
        if self._indexed_count != len(self.documents):
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
            results = self._substring_search(query, top_k, kind)
            self._remember(cache_key, results)
            return results

        query_norm = math.sqrt(sum(v * v for v in query_vec.values()))
        if query_norm == 0:
            return []

        # 把 query 的稀疏非零项拆成两个平行列表，内层只剩"取下标 + 乘法 + 加法"。
        q_terms = list(query_vec)
        q_vals = [query_vec[term] for term in q_terms]
        n_terms = len(q_terms)

        postings = self._postings
        doc_norms = self._doc_norms
        documents = self.documents
        weights = book_weights or {}

        # 点积：**倒排表**让内层只走真正含这个词项的文档，而不是全部 8534 篇。
        # 累加仍按查询词项的顺序进行（外层就是词项循环），所以某篇文档收到的
        # 加法次序与"逐篇扫描"时完全一致，得到的 dot 逐位相同。
        acc: dict[int, float] = {}
        get_entry = postings.get
        for k in range(n_terms):
            entry = get_entry(q_terms[k])
            if entry is None:
                continue
            idxs, vals = entry
            qv = q_vals[k]
            for j in range(len(idxs)):
                i = idxs[j]
                acc[i] = acc.get(i, 0.0) + qv * vals[j]

        # 只保留 (分数, 下标)：SearchResult 里带正文切片与出处字符串，
        # 命中上百篇时全部构造出来再丢掉 95%，纯属白做。
        scored: list[tuple[float, int]] = []
        for i, dot in acc.items():
            if dot <= 0:
                continue
            doc = documents[i]
            if kind is not None and doc.get("kind", KIND_NOTES) != kind:
                continue
            doc_norm = doc_norms[i]
            if doc_norm == 0:
                continue

            # 来源权重：让精炼过的笔记略高于原典
            score = dot / (query_norm * doc_norm) * doc.get("weight", 1.0)
            if weights:
                score *= weights.get(doc["book_id"], 1.0)
            if score > 0:
                scored.append((score, i))

        # 同分时按下标升序，与"先构造再整体稳定排序"的旧行为保持一致
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        results = [self._to_result(documents[i], score) for score, i in scored[:top_k]]
        self._remember(cache_key, results)
        return results

    @staticmethod
    def _cache_key(
        query: str,
        top_k: int,
        kind: Optional[str],
        book_weights: Optional[Mapping[str, float]],
    ) -> tuple:
        """缓存键。

        ``book_weights`` 是字典、不可哈希，按**内容**折成有序元组——它由
        书架与主题决定，同一套权重每次都是同一批键值（十五本书，排序开销
        是微秒级）。``kind`` 参与是因为它决定"召回哪一路"，同样的问句限定
        ``notes`` 与不限定的结果并不相同。
        """
        weights_key = tuple(sorted(book_weights.items())) if book_weights else None
        return (query, top_k, kind, weights_key)

    def _remember(self, key: tuple, results: list[SearchResult]) -> None:
        """记一条缓存；超过上限就丢最久没用过的那个。"""
        self._result_cache[key] = list(results)
        self._result_cache.move_to_end(key)
        while len(self._result_cache) > RESULT_CACHE_MAX:
            self._result_cache.popitem(last=False)

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
        kind = doc.get("kind")
        if kind == KIND_SOURCE:
            return f'《{doc["book_title"]}》· 原典'
        if kind == KIND_SHELF:
            return f'《{doc["book_title"]}》· 我的书架'
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


def reset_retriever() -> None:
    """丢弃全局单例（测试与热重载用）。"""
    global _retriever
    _retriever = None


#: 建索引的进度（0.0~1.0）与当前阶段说明，供启动画面显示真实进度。
#: 建索引要好几秒（实测本机约 7 秒，几乎全花在 jieba 分词上），
#: 这期间窗口里只有一个转圈的动画，用户不知道是在干活还是卡住了。
#: 这里把"第几本书 / 共几本"报出去，启动画面就能显示一条真在走的进度条。
#:
#: 只放两个只读标量：写的时候加锁，读的时候也加锁——字符串赋值在 CPython
#: 里是原子的，但两个字段要一起读才有意义，不加锁可能读到"新进度配旧说明"。
_progress_lock = threading.Lock()
_progress: dict[str, object] = {"ratio": 0.0, "stage": "准备中"}


def _report_progress(ratio: float, stage: str) -> None:
    """更新进度快照。构建过程中的任何失败都不该因此中断，故整体吞异常。"""
    try:
        with _progress_lock:
            _progress["ratio"] = max(0.0, min(1.0, ratio))
            _progress["stage"] = stage
    except Exception:  # noqa: BLE001 — 进度只是观感，绝不能影响正事
        pass


def index_progress() -> dict[str, object]:
    """当前建索引进度快照，供 ``/api/health`` 与启动画面读取。"""
    with _progress_lock:
        return {"ratio": float(_progress["ratio"]), "stage": str(_progress["stage"])}


def build_retriever_from_loader(loader, *, include_source: bool = True) -> TFIDFRetriever:
    """从内容加载器构建检索器。

    笔记每章入索引；``include_source`` 为真时，体量适中的原典全文也一并入索引，
    这样「寻章」才能真正做到"跨全库"——既找得到解读，也找得到原句。

    构建过程中会持续上报进度（见 :func:`index_progress`），让启动画面上的
    进度条走的是真实进度而不是一条循环动画。
    """
    global _retriever
    retriever = TFIDFRetriever()
    indexed_source: list[str] = []
    skipped_source: list[str] = []

    books = list(loader.get_books())
    # 每本书按"正文一批、原典一批"计两步，总步数用于折算比例。
    # 原典被跳过的书只有一步，宁可让进度条走得略保守，也不要把比例算虚。
    total_steps = sum(2 if (include_source and b.source_file) else 1 for b in books) + 1

    def _tick(done: int, stage: str) -> None:
        _report_progress(done / total_steps if total_steps else 1.0, stage)

    step = 0
    for book in books:
        for ch in book.chapters:
            retriever.add_document(
                book_id=book.book_id,
                book_title=book.title,
                chapter_id=ch.chapter_id,
                chapter_title=ch.title,
                content=ch.content,
            )
        step += 1
        _tick(step, "正在读《%s》" % book.title)

        if not include_source or not book.source_file:
            continue
        text = loader.get_source_text(book.book_id)
        if not text:
            step += 1
            continue
        if len(text) > SOURCE_INDEX_MAX_CHARS:
            skipped_source.append(book.title)
            step += 1
            _tick(step, "《%s》体量过大，跳过原典" % book.title)
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
        step += 1
        _tick(step, "正在读《%s》原典" % book.title)

    _tick(step, "正在计算词频权重")
    retriever.build_index()
    _tick(total_steps, "就绪")
    retriever.source_coverage = {
        "indexed": indexed_source,
        "skipped": skipped_source,
    }
    _retriever = retriever
    return retriever


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
