"""书籍/章节 API 路由。

书目与正文也要登录：这套产品现在的入口就是登录页，登录之前一个页面也看不了。
界面那道门在后端跟着收紧，否则直接打接口照样绕过去——而"哪些接口要登录"
若只写在前端，漏一处的代价是悄悄地对匿名开放。
为什么是路由级 `dependencies` 而不是每个 handler 各写一遍，见 `deps.py`。

这一组不碰数据库（内容直接从语料文件读），所以错误声明里没有 503。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_user
from ..errors import LOGGED_IN
from ..schemas.books import BookSummary, ChapterDetail, ChapterSummary, SourceResponse
from ..services.content_loader import get_loader

router = APIRouter(
    prefix="/api/books",
    tags=["books"],
    dependencies=[Depends(require_user)],
    responses=LOGGED_IN,
)

#: 原典单次返回的最大字符数。
#: 《资治通鉴》全文约 310 万字，一次性塞给浏览器会让页面卡死，
#: 因此原典按块返回，由前端翻页累加。
SOURCE_CHUNK = 20000


def _summary(book) -> BookSummary:
    return BookSummary(
        book_id=book.book_id,
        title=book.title,
        author=book.author,
        category=book.category,
        chapter_count=len(book.chapters),
        has_source=book.source_file is not None,
    )


def _missing(code: str, message: str) -> HTTPException:
    """找不到东西。带上 ``code`` 供前端区分是书没了还是章节没了。

    原先这几条只有一句英文（``"Book not found"``），会原样显示在中文界面上——
    全项目唯一一处英文的错误文案，也是唯一一处没带 ``code`` 的。
    """
    return HTTPException(status_code=404, detail={"code": code, "message": message})


@router.get("", response_model=list[BookSummary])
async def list_books():
    """获取所有书目列表。"""
    return [_summary(book) for book in get_loader().get_books()]


@router.get("/{book_id}", response_model=BookSummary)
async def get_book(book_id: str):
    """获取单本书信息。"""
    book = get_loader().get_book(book_id)
    if book is None:
        raise _missing("book_not_found", "没有这本书")
    return _summary(book)


@router.get("/{book_id}/chapters", response_model=list[ChapterSummary])
async def list_chapters(book_id: str):
    """获取某书的章节列表。"""
    chapters = get_loader().get_chapters(book_id)
    if not chapters:
        raise _missing("chapter_not_found", "没有这本书，或它还没有章节")
    return [
        ChapterSummary(chapter_id=ch.chapter_id, title=ch.title, book_id=ch.book_id)
        for ch in chapters
    ]


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterDetail)
async def get_chapter(book_id: str, chapter_id: str):
    """获取某章节的完整内容。"""
    chapter = get_loader().get_chapter(book_id, chapter_id)
    if chapter is None:
        raise _missing("chapter_not_found", "没有这一章")
    return ChapterDetail(
        chapter_id=chapter.chapter_id,
        title=chapter.title,
        book_id=chapter.book_id,
        content=chapter.content,
    )


@router.get("/{book_id}/source", response_model=SourceResponse)
async def get_source(
    book_id: str,
    offset: int = Query(0, ge=0, description="起始字符位置"),
    limit: int = Query(SOURCE_CHUNK, ge=1, le=200_000, description="本次返回的字符数"),
):
    """获取某书的原典全文（分块）。

    小书一次就能取完；大书由前端按 ``has_more`` 逐块拉取。
    """
    loader = get_loader()
    book = loader.get_book(book_id)
    text = loader.get_source_text(book_id)
    if book is None or text is None:
        raise _missing("source_not_available", "这本书没有原典全文")

    chunk = text[offset : offset + limit]
    return SourceResponse(
        book_id=book_id,
        title=book.title,
        content=chunk,
        offset=offset,
        limit=limit,
        total=len(text),
        has_more=offset + limit < len(text),
    )
