"""history 接口的出入参。

从 ``routers/history.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

#: 一次批量删除最多接受多少个目标。见 :class:`BulkDeleteRequest`。
#: 与 ``MAX_REQUEST_TURNS`` 同理：它是契约的一部分，不是路由的私事。
MAX_BULK_TARGETS = 500

class HistoryItem(BaseModel):
    """一条求教记录。"""

    id: int
    question: str
    answer: str
    model: Optional[str] = Field(None, description="产出回答的模型；null 表示本地检索降级")
    llm_used: bool
    retrieved_count: int
    conversation_id: Optional[str] = Field(
        None, description="所属话题；升级前的老记录为 null"
    )
    created_at: str = Field(..., description="本地时区的 ISO 8601")
    created_ts: float = Field(..., description="Unix 时间戳（秒）")

class TopicItem(BaseModel):
    """一个话题：一次会话里的连续追问聚成的一张卡片。"""

    id: str = Field(..., description="话题 id；老记录是 solo:<记录id>")
    title: str = Field(..., description="话题的第一问")
    question_count: int
    first_ts: float
    last_ts: float
    latest_question: str
    latest_answer: str

class HistoryListResponse(BaseModel):
    """记录列表。

    ``available=False`` 时列表为空、``error`` 里是原因——这是接口层面的
    **优雅降级**：数据库建不出来（程序目录只读、磁盘满）不该让界面报错，
    而应该照常渲染、顺手把原因说清楚。
    """

    available: bool
    error: str
    total: int
    items: list[HistoryItem]

class TopicListResponse(BaseModel):
    """话题列表。``total`` 是**话题**数，不是记录数。"""

    available: bool
    error: str
    total: int = Field(..., description="话题数，不是记录数")
    items: list[TopicItem]

class HistoryStatusResponse(BaseModel):
    """存储概况：有多少条、保留多久、下次什么时候清理。"""

    model_config = ConfigDict(title="HistoryStatus")

    available: bool
    error: str
    db_path: str
    total: int
    retention_days: float = Field(..., description="保留天数。默认半个月")
    last_purge_at: Optional[str]
    next_purge_at: Optional[str] = Field(..., description="下一次自动清理的时间")
    size_bytes: int

class BulkDeleteRequest(BaseModel):
    """勾选删除的目标：记录 id 与话题 id 可以混着给，也可以只给一边。

    两个清单都设了长度上限：这是**不可撤销**的操作，与其收下一个畸形请求
    （比如几万个 id）去拼一条巨型 SQL，不如当场返回 422。界面上的勾选量来自
    已加载的列表，远够不到这个数。
    """

    model_config = ConfigDict(title="DeleteTargets")

    ids: list[int] = Field(
        default_factory=list,
        max_length=MAX_BULK_TARGETS,
        description="要删的记录 id",
    )
    topics: list[str] = Field(
        default_factory=list,
        max_length=MAX_BULK_TARGETS,
        description="要整段删掉的话题 id（含老记录的 solo:<记录id>）",
    )
