"""全文检索 API 路由（界面上的「寻章」）。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..deps import require_user
from ..errors import LOGGED_IN
from ..schemas.search import SearchResponse, SearchResponseItem
from ..services.auth import User
from ..services.unified_search import search_all

# 「寻章」在界面上要登录（它在前端路由表 `RequireAuth` 那一组里），接口跟着收紧：
# 检索会连你自己的书架一起查，匿名不该进得来。理由与做法见 `deps.py`。
router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_user)],
    responses=LOGGED_IN,
)

#: 来源过滤：不限 / 只看深读笔记 / 只看原典全文 / 只看我的书架
KindFilter = Literal["all", "notes", "source", "shelf"]


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="搜索关键词", min_length=1),
    top_k: int = Query(5, ge=1, le=20, description="返回结果数"),
    kind: KindFilter = Query("all", description="来源过滤：all / notes / source / shelf"),
    user: User = Depends(require_user),
):
    """全文检索：在深读笔记、原典全文，以及**自己的书架**中搜索。

    ``kind`` 可用于只看解读、只看经文原句，或只看自己的书架。

    ``user_id`` 是必给的：检索范围包含本人的书架，而书架按账号隔离——
    少传这个参数，别人往私人书架里加的书就会出现在你的检索结果里。
    """
    results = search_all(q, top_k=top_k, kind=None if kind == "all" else kind, user_id=user.id)
    return SearchResponse(
        query=q,
        total=len(results),
        results=[
            SearchResponseItem(
                book_id=r.book_id,
                book_title=r.book_title,
                chapter_id=r.chapter_id,
                chapter_title=r.chapter_title,
                content=r.content,
                score=r.score,
                source=r.source,
                kind=r.kind,
                offset=r.offset,
            )
            for r in results
        ],
    )
