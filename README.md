# 人生导师 · 中国传统经典智慧知识库

> 把经典读成可用的判断力。

一个全栈应用：把《易经》《道德经》《毛选》《史记》《资治通鉴》等经典的原典与深读笔记，
做成可浏览、可检索、可提问的知识库。你抛出一个生活困惑，它会先从经典中检索相关段落，
再按「**你的处境 → 经典怎么说 → 我的分析 → 建议你怎么办**」的结构给出回答。

- **后端**：Python 3.13+ / FastAPI / 自研 TF-IDF 检索（jieba 分词，无向量库依赖）
- **前端**：React 18 + TypeScript + Vite + Tailwind（中式书卷配色）
- **测试**：pytest（后端 259 项）+ Vitest（前端 24 项）

---

## 下载桌面版

不想配环境，直接要一个能双击运行的 Windows 应用：

**→ [Releases 页面](https://github.com/sunandsuns/Teachers/releases/latest) 下载 `renshengdaoshi-*.zip`**

解压后双击 `人生导师.exe` 即可。**不需要装 Python、Node 或任何运行时**
（窗口用系统自带的 WebView2 内核）。整个文件夹要一起保留——exe 离不开同级的
`corpus/` 与 `_internal/`。详见包内的 `启动说明.txt`。

想改代码、跑源码态，看下面的「快速开始」；想自己打一个包，看「打包与分发」。

---

## 功能

| 页面 | 路径 | 能力 |
| --- | --- | --- |
| **书架** | `/` | 浏览 15 部经典，按 7 个类目（哲学 / 处世 / 术数 / 政治 / 兵学 / 纵横 / 历史文献）筛选 |
| **阅读** | `/books/:id` | 逐章阅读深读笔记；有原典的书可切换「原典全文」标签页（大书分块载入） |
| **寻章** | `/search` | 跨全库检索**深读笔记 + 原典全文**，可只查其一；结果直接**跳到那一段的所在位置** |
| **求教** | `/ask` | 描述你的问题或困境，系统检索经典段落并生成结构化回答（上游不可用时自动降级） |
| **感悟** | `/insights` | 今日感悟（同一天刷新不变）、随机一则、按 8 个主题浏览金句 |

---

## 架构

```
                ┌──────────────────────────────┐
                │  React 前端 (web/)            │
                │  书架 · 阅读 · 寻章 · 求教 · 感悟 │
                └───────────────┬──────────────┘
                                │ /api  (vite dev proxy → :8000)
                ┌───────────────▼──────────────┐
                │  FastAPI 后端 (server/)        │
                │  routers/ books search ask insight │
                └───────────────┬──────────────┘
                                │
        ┌───────────────┬───────┴────────┬───────────────┐
        ▼               ▼                ▼               ▼
  内容加载器       TF-IDF 检索器     LLM 模型路由     感悟服务
  content_loader    retriever       llm/ (router)  insight/service
        │               │                │               │
        └───────────────┴────────┬───────┴───────────────┘
                                 ▼
        ┌────────────────────────────────────────────┐
        │  语料层                                      │
        │  books/ · 理解笔记/ · MaoZeDongAnthology/    │
        │           · WangYangMing/                   │
        └────────────────────────────────────────────┘
```

### 目录结构

```
人生导师/
├── books/                     # 13 部原典纯文本（孙子兵法/道德经/论语/菜根谭/鬼谷子/
│                              #   战国策/史记/资治通鉴/贞观政要 等）
├── 理解笔记/                   # 25 篇深读笔记，应用的主要语料
├── MaoZeDongAnthology/        # 毛选 mdbook 工程（src/ 下 229 篇正文）
├── WangYangMing/              # 王阳明资料集（概览 + 诗词）
├── server/                    # FastAPI 后端
│   ├── main.py                # 应用入口、CORS、健康检查
│   ├── routers/               # 薄 HTTP 层：只做参数校验与响应建模
│   │   ├── books.py           #   /api/books（原典分块读取）
│   │   ├── search.py          #   /api/search（kind 过滤）
│   │   ├── ask.py             #   /api/ask（含 /status）
│   │   └── insight.py         #   /api/insight
│   └── services/              # 业务层：不依赖 FastAPI，可独立单测
│       ├── content_loader.py  #   注册表 + 加载策略
│       ├── retriever.py       #   TF-IDF 检索（笔记 + 原典双源）
│       ├── llm/               #   模型自动切换（config/transport/prompt/router）
│       └── insight/           #   data（金句）→ service（选择算法）
├── tests/                     # pytest：unit / integration 两层
├── run.py                     # 一键启动（端口自动避让）
├── smoke.py                   # 联调冒烟：走真实 HTTP + vite 代理
└── web/                       # React 前端（src/pages 下 5 个页面）
```

---

## 快速开始

### 1. 启动后端

```bash
# 安装依赖（需要 Python 3.10+）
pip install -r server/requirements.txt

# 启动（在项目根目录执行）
python -m uvicorn server.main:app --reload --port 8000
```

启动后：API 文档 <http://127.0.0.1:8000/docs>，健康检查 <http://127.0.0.1:8000/api/health>

### 2. 启动前端

```bash
cd web
npm install
npm run dev
```

打开 <http://localhost:5173>（Vite 已把 `/api` 代理到 `localhost:8000`，无跨域问题）。

### 3. 一键启动（可选）

```bash
python run.py          # 同时拉起前后端，Ctrl+C 一起退出
python run.py --help   # 查看端口等参数
```

默认后端 `:8000`、前端 `:5173`。**若端口被占用会自动顺延**（如 `8000→8001`）并打印提示，
不需要手动改配置。

> 注意：前端 dev server 由 Vite 绑定在 `localhost`（本机解析为 IPv6 `::1`）。
> 若用 `curl`/脚本访问，请用 `http://localhost:5173`；某些环境里 `http://127.0.0.1:5173` 会被代理拦截。

### 4. 启用 AI 深度解读（可选）

不配置 API Key 时，「求教」会自动降级为**本地检索模式**：直接列出检索到的经典段落与出处。
配置任意 **OpenAI 兼容端点**后，回答会按结构化模板生成。

把 `.env.example` 复制为 `.env`（`.env` 已在 `.gitignore` 中）：

```ini
LLM_BASE_URL=https://api.sllying.bond/v1     # 任意 OpenAI 兼容端点
LLM_API_KEY=sk-...
LLM_MODEL=                                    # 留空 = 自动挑选可用模型
LLM_MODEL_CANDIDATES=deepseek-v4-pro-0813,glm-4.7-flash,gemini-2.5-flash
```

也可以直接用环境变量覆盖（优先级更高）：

```bash
export LLM_API_KEY=sk-...                    # Windows: set LLM_API_KEY=...
python run.py
```

#### 模型自动切换

聚合类端点的模型可用性**随时间抖动**——同一时刻有的模型 403、有的 503、有的直接从列表里消失。
写死一个模型名，等于把应用绑死在某一次快照上。因此 `server/services/llm/router.py`
实现了「**候选有序 + 并发探活 + 结果缓存 + 失败轮换 + 时间预算**」：

| 环节 | 行为 |
| --- | --- |
| 候选来源 | 显式 `LLM_MODEL` → 显式 `LLM_MODEL_CANDIDATES` → 端点 `/models`（按偏好排序） |
| 探活 | 用一次极短对话（16 token）确认模型**真能出字**；**整批并发**，取最先返回成功的那个 |
| 缓存 | 选中结果缓存 `LLM_CACHE_TTL` 秒，避免每个请求都重探一遍 |
| 轮换 | 失败的模型进冷却队列，下次自动跳到下一个候选 |
| 冷却分级 | 可重试错误（5xx/429）冷却 120s；不可重试错误（401/403/404）冷却 600s，省得反复撞墙 |
| **时间预算** | 「探活 + 生成」总耗时受 `LLM_TOTAL_BUDGET` 约束；探活阶段另受 `PROBE_BUDGET_SHARE` 限制，最多吃掉总预算的三分之一 |

**探活必须并发**——这是实测踩坑后改的。聚合端点上的模型有两种坏法：

- **快速报错**（4xx/5xx）：立即返回，不费时间；
- **连得上但不回应**：一直挂到读超时才放手，费满 `LLM_PROBE_TIMEOUT`。

串行探活时后一种是致命的：4 个候选里有 3 个在挂，光探活就要烧掉 `3 × 12s`，
45s 的总预算在探活阶段就见底——**明明有可用模型，生成一步却没有余量，
用户等满 45 秒拿到的仍是本地降级答案**。并发把探活阶段的耗时上限从
「候选数 × 超时」压回「单次超时」，同时取最先返回的那个，响应快的模型优先。

实测同一端点、同一个问题（`工作中遇到小人怎么办？`）：

| | 耗时 | 结果 |
| --- | --- | --- |
| 串行探活 | 45.4s | `llm_used=false`，降级为本地检索 |
| 并发探活 | 11–14s | `llm_used=true`，`model=gemini-2.5-flash` |

时间预算还有一层保险作用：上游**集体**故障时也不该让用户干等。没有它，
最坏情况是 `/models` 8s + 4 次探活 × 12s + 生成 60s ≈ **2 分钟**，
用户只会在页面上等到浏览器超时。

想看当前端点上哪些模型真的能跑，用自带的探活 CLI：

```bash
python -m server.services.llm              # 探活全部候选，打印最终会选中的模型
python -m server.services.llm --limit 4    # 只探前 4 个
python -m server.services.llm --json       # 输出 JSON，便于脚本消费
python -m server.services.llm --no-proxy   # 强制直连，不走系统代理
```

运行时状态也可通过 `GET /api/ask/status` 查看（当前选中的模型、冷却中的模型、最近一次错误）。

---

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/books` | 书目列表（含章节数、是否有原典） |
| GET | `/api/books/{book_id}` | 单本书信息 |
| GET | `/api/books/{book_id}/chapters` | 章节目录 |
| GET | `/api/books/{book_id}/chapters/{chapter_id}` | 章节正文 |
| GET | `/api/books/{book_id}/source?offset=0` | 原典全文，**按 20000 字分块**返回（`has_more` 指示是否还有）；无原典返回 404 |
| GET | `/api/search?q=关键词&top_k=5&kind=all` | 全文检索，`kind` 取 `all`/`notes`/`source`；结果带出处、相关度、`kind` 与 `offset` |
| POST | `/api/ask` | 智能问答 `{"question": "...", "top_k": 5}`，响应含 `llm_used` 与 `model` |
| GET | `/api/ask/status` | LLM 状态：是否可用、当前模型、候选数、冷却中的模型、最近错误 |
| GET | `/api/insight/daily?day=YYYY-MM-DD` | 今日感悟（同一天结果稳定） |
| GET | `/api/insight/random` | 随机感悟 |
| GET | `/api/insight/themes` | 主题列表与各自数量 |
| GET | `/api/insight/by-theme/{theme}` | 按主题取金句 |
| GET | `/api/insight/by-book/{book_id}` | 按书目取金句 |
| GET | `/api/health` | 健康检查（书目数 / 章节数 / 索引段落数 / 有原典的书数 / 跳过大书 / 分类） |

---

## 语料

**15 部经典**，共 **352 章**、**8852 个检索单元**（1962 条深读笔记 + 6890 条原典段落）：

| ID | 书名 | 类目 | 章节 | 原典 | 原典字数 |
| --- | --- | --- | --- | --- | --- |
| 01 | 易经 | 哲学 | 5 | ✓ | 203,018 |
| 02 | 厚黑学 | 处世 | 13 | ✓ | 4,481 |
| 03 | 奇门遁甲 | 术数 | 15 | ✓ | 7,854 |
| 04 | 人性的弱点 | 处世 | 10 | ✓ | 184,755 |
| 05 | 毛泽东选集 | 政治 | 229 | — | — |
| 06 | 王阳明心学 | 哲学 | 4 | — | — |
| 07 | 孙子兵法 | 兵学 | 7 | ✓ | 7,637 |
| 08 | 道德经 | 哲学 | 7 | ✓ | 7,728 |
| 09 | 论语 | 哲学 | 7 | ✓ | 23,478 |
| 10 | 菜根谭 | 处世 | 6 | ✓ | 18,133 |
| 11 | 鬼谷子 | 纵横 | 7 | ✓ | 9,374 |
| 12 | 战国策 | 纵横 | 10 | ✓ | 158,104 |
| 13 | 史记 | 历史文献 | 8 | ✓ | 600,250 |
| 14 | 资治通鉴 | 历史文献 | 12 | ✓ | 3,216,638 |
| 15 | 贞观政要 | 历史文献 | 12 | ✓ | 187,128 |

07–15 的原典（孙子兵法 / 道德经 / 论语 / 菜根谭 / 鬼谷子 / 战国策 / 史记 / 资治通鉴 / 贞观政要）
取自 **殆知阁（daizhigev20）** 语料的「白文本」（不带注疏的干净正文），逐字校对后录入 `books/`。

05、06 没有原典是**有意为之**：毛选走 mdbook 工程、王阳明是资料集，正文形态与"一部古籍的连续全文"不同，
强行切一份纯文本反而失真。这两本只提供深读笔记，前端自动隐藏「原典全文」标签页。

深读笔记统一采用：**元信息表 → 核心思想深解 → 关键篇目/章句 → 八大主题归纳 → 常见误读辨析 → 与其他经典的交叉点**。
原文一律逐字引用并标注出处，理解以提炼为主。

> **两处刻意的取舍**（都为了不让浏览器卡死）：
> - **原典分块**：`/api/books/14/source` 一次只给 20000 字，《资治通鉴》要翻 161 次才读完。
> - **大书不进检索索引**：`SOURCE_INDEX_MAX_CHARS = 250_000`，《史记》《资治通鉴》超出阈值被跳过
>   （`/api/health` 的 `source_skipped` 会列出它们），否则每次检索都要在 380 万字里算余弦。

---

## 测试

```bash
# 后端（在项目根目录）
python -m pytest -q

# 前端
cd web && npm test
```

### 联调冒烟（需要服务已启动）

单元与集成测试用 `TestClient` 直连 ASGI，不经过真实网络。要验证「浏览器 → vite 代理 → 后端」
这条真实链路，先 `python run.py` 起服务，再另开一个终端：

```bash
python smoke.py
```

它会逐项检查：后端书目/章节/检索单元数与原典索引规模、前端页面可编译、vite 代理转发、
寻章检索（含 `kind` 过滤与命中偏移定位）、原典分块与按偏移跳读、求教在时间预算内返回、
感悟当日稳定性。全部通过退出码为 0。

> 「求教」那一步会**实测耗时**并要求 90 秒内返回。上游不可用时，这一步验证的正是
> "快速降级到本地检索"这条路径——它不该 FAIL，而该在 20 余秒内给出本地检索结果。

| 层 | 位置 | 覆盖内容 |
| --- | --- | --- |
| 单元 | `tests/unit/test_content_loader.py` | 章节拆分、幂等加载、章节往返读取 |
| 单元 | `tests/unit/test_loader_strategies.py` | 三种加载策略的行为与容错（用临时目录构造迷你仓库） |
| 单元 | `tests/unit/test_book_registry.py` | 注册表不变量：id 唯一、**每本登记的书都必须真有章节**、原典声明必须存在 |
| 单元 | `tests/unit/test_retriever.py` | 分词、余弦排序、降级子串匹配、笔记/原典双源与 offset |
| 单元 | `tests/unit/test_llm.py` | 配置解析（`.env` 优先级、候选排序）、prompt 结构、传输层错误分类 |
| 单元 | `tests/unit/test_llm_router.py` | 探活、TTL 缓存、冷却分级、失败轮换、**时间预算截断**（全用假 transport，不联网） |
| 单元 | `tests/unit/test_insight_service.py` | 日期确定性选句、主题索引 |
| 单元 | `tests/unit/test_api.py` | 路由、参数校验、404 语义、原典分页、`/ask/status` |
| 集成 | `tests/integration/test_read_flow.py` | 书架 → 章节 → 正文的完整链路一致性 |
| 集成 | `tests/integration/test_ask_flow.py` | 问答链路、search/ask 共用同一索引 |
| 集成 | `tests/integration/test_ask_llm_flow.py` | HTTP → router → 失败轮换 → 降级，端到端 |
| 集成 | `tests/integration/test_corpus_flow.py` | 逐本遍历可读性、新语料检索命中、感悟引用无悬空 |

> **性能**：内容层与索引只读，因此测试夹具为 session 级——整套后端测试从 114 秒降到 **7 秒**。

---

## 打包与分发

源码态要 Python 与 Node 两套环境，直接交给别人是没法用的。`build_app.py` 把
「构建前端 → PyInstaller 打包 → 组装语料与配置 → 实机自检」串成一条命令：

```bash
# 打包专用环境（与开发环境分开，否则产物会夹带无关依赖、体积翻倍）
python -m venv <打包环境>
<打包环境>/Scripts/pip install -r server/requirements.txt pyinstaller pywebview

<打包环境>/Scripts/python.exe build_app.py

python build_app.py --skip-frontend   # 复用已有的 web/dist
python build_app.py --no-selftest     # 只出产物，不自检
python build_app.py --selftest-only   # 不重新打包，只对已有产物做实机自检
python build_app.py --zip             # 自检通过后额外压成 zip
```

产物在 `dist/人生导师/`：`人生导师.exe` + `_internal/`（运行时依赖）+ `corpus/`（语料）
+ `.env`（模型配置）+ `启动说明.txt`。整个文件夹（或 zip）直接交给别人，双击即用，
对方不需要装 Python、Node 或任何运行时。

三个刻意的设计：

- **语料不进包体**。放在 exe 同级的 `corpus/`：用户能用记事本直接增补笔记而无需重新打包，
  每次启动也少解压一份。代价是分发时必须整个文件夹一起给，不能只发 exe。
- **打包到暂存目录再重命名换入**（`_run_pyinstaller`）。PyInstaller 构建前会先删掉同名
  输出目录，直接构建到 `dist/` 就必然摧毁上一版产物；改成"构建到 `.staging-<时间戳>` →
  原子重命名换入"之后，失败时旧产物完好，全程也不需要批量删文件。
- **窗口用 pywebview + 系统自带 WebView2**，不引入 Electron/Tauri——为了一个已经存在的
  Python 后端再拉进一整套 Node 或 Rust 工具链并不划算。

### 实机自检

打包后自动拉起 exe 逐项验证。这些失败模式**只在冻成 exe 之后才会暴露**，
源码态怎么跑都是通的：

| 检查 | 对应的真实故障 |
| --- | --- |
| 语料加载 15 本书 / 352 章 | 打包漏拷 `corpus`，书架是空的 |
| 原典已入检索库 | jieba 词典没进包，检索悄悄变差 |
| 前端页面由后端托管 | `web/dist` 没进包，窗口一片空白 |
| 深链刷新回退 | SPA 回退路由被注册在 API 之前 |
| 寻章有结果 / 原典分块可读 | 索引或分块接口在冻结态失效 |
| `.env` 被读取 | 配置没跟着走，AI 问答悄悄降级 |
| 求教在预算内返回且 `llm_used=true` | 内置 Key 根本调不通上游 |

### 窗口起不来怎么办

WebView2 的浏览器进程崩溃时（安全软件拦截、运行时损坏），`load_url` 不会抛异常，
窗口会永远停在"正在编索引"的白屏。`desktop.py` 因此在内核加载后额外做一次 JS 探针
（`_probe_window`），确认内核真的活着；一旦发现是死的，就改用系统浏览器打开同一地址
并弹框说明。探针只在**次次都失败**时才判死，避免误伤还在渲染的慢机器。

> 内置 `.env` 的取舍：包里放的是**可用的真实密钥**，拿到包的人可以看到并使用它。
> 若不希望额度被转用，把 `.env` 换成只含占位值的 `.env.example`——此时「求教」
> 会自动降级为本地检索模式，对方自行填入 Key 即可启用 AI 解读。

---

## 设计要点

**1. 声明与行为分离（`content_loader.py`）**
书目元信息（`BookSpec`）只描述"是什么"，"怎么装进来"由独立加载策略负责，
通过 `loader -> 策略` 查表分派。新增一本书只需在注册表登记一行；
新增一种语料形态只需增加一个策略方法，`load()` 无需改动。

```python
BOOK_REGISTRY = (
    BookSpec("01", "易经", "周文王/周公（传）", "哲学", NOTES, source="易经.txt"),
    BookSpec("05", "毛泽东选集", "毛泽东", "政治", MDBOOK, options={"dir": "MaoZeDongAnthology"}),
    BookSpec("06", "王阳明心学", "王守仁", "哲学", COLLECTION, options={...}),
)
```

**2. 三层分离，逐层可测**
`routers/`（HTTP）→ `services/`（业务，不依赖 FastAPI）→ 数据。
路由层只做参数校验与响应建模，业务规则全在 service，
因此 `InsightService` 可以脱离 HTTP 单独单测，HTTP 层也可整体替换。

**3. 优雅降级**
没有 LLM Key、LLM 上游整体故障、原典缺失、单个语料文件损坏——四种缺失都不会让接口报错，
而是走各自的降级路径（本地检索回答 / 快速降级 / 隐藏标签页 / 跳过该文件）。
关键是**降级要快**：时间预算让"上游挂了"表现为 20 秒内的本地检索结果，而不是浏览器的超时页。

**4. 模型可用性不写死**
LLM 层拆成 `config`（读配置与候选排序）/ `transport`（HTTP 细节）/ `prompt`（模板）/ `router`（选择与轮换）。
`transport` 可以在测试里被整体替换，因此路由策略——探活、缓存、冷却、轮换、预算——全部可脱离网络验证。

**5. 数据不变量由测试锁住**
`test_book_registry.py` 会验证"注册表里每一本书都必须真的能读到章节"，以及"07–15 声明的原典必须真有内容"。
这条断言正是为了拦住曾经出现过的"书目登记了但语料为空、前端只能显示暂无内容"。

---

## 已知问题与后续方向

- **检索质量**：TF-IDF 对「工作中遇到小人怎么办」这类口语化提问召回一般，
  因为查询词与语料用词不完全重合。可行的升级：查询改写、向量检索、BM25 调参。
- **上游端点不稳定**：`api.sllying.bond` 的模型列表与可用性频繁变化
  （观测到 33 → 22 个模型、同一模型时而 503 时而可用）。
  自动切换已能兜住，但**换一个更稳定的端点仍是根治手段**——改 `.env` 里的 `LLM_BASE_URL` 即可。
- **大书检索不到**：《史记》《资治通鉴》超出索引阈值被跳过，目前只能靠深读笔记检索。
  可行方向：为超大书建独立索引、按需加载、或换成倒排索引。
- **笔记重复**：`理解笔记/` 下 `05-毛泽东选集-第2部分-046至091.md` 与
  `05-毛泽东选集-第2部分-084至091.md` 区间重叠，疑似早期的重复产物，
  建议确认后合并或删除一份（毛选走 mdbook 策略，暂不影响接口输出）。
- **感悟池偏小**：47 条金句，覆盖 8 个主题，可继续扩充。
