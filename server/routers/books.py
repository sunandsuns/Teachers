"""书籍/章节 API 路由。"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.content_loader import get_loader

router = APIRouter(prefix="/api/books", tags=["books"])

#: 原典单次返回的最大字符数。
#: 《资治通鉴》全文约 310 万字，一次性塞给浏览器会让页面卡死，
#: 因此原典按块返回，由前端翻页累加。
SOURCE_CHUNK = 20000


class BookSummary(BaseModel):
    """书目摘要（列表用）。"""
    book_id: str
    title: str
    author: str
    category: str
    chapter_count: int
    has_source: bool


class ChapterSummary(BaseModel):
    """章节摘要（列表用）。"""
    chapter_id: str
    title: str
    book_id: str


class ChapterDetail(BaseModel):
    """章节详情（阅读用）。"""
    chapter_id: str
    title: str
    book_id: str
    content: str


@router.get("", response_model=list[BookSummary])
async def list_books():
    """获取所有书目列表。"""
    loader = get_loader()
    result = []
    for book in loader.get_books():
        result.append(BookSummary(
            book_id=book.book_id,
            title=book.title,
            author=book.author,
            category=book.category,
            chapter_count=len(book.chapters),
            has_source=book.source_file is not None,
        ))
    return result


@router.get("/{book_id}", response_model=BookSummary)
async def get_book(book_id: str):
    """获取单本书信息。"""
    loader = get_loader()
    book = loader.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookSummary(
        book_id=book.book_id,
        title=book.title,
        author=book.author,
        category=book.category,
        chapter_count=len(book.chapters),
        has_source=book.source_file is not None,
    )


@router.get("/{book_id}/chapters", response_model=list[ChapterSummary])
async def list_chapters(book_id: str):
    """获取某书的章节列表。"""
    loader = get_loader()
    chapters = loader.get_chapters(book_id)
    if not chapters:
        raise HTTPException(status_code=404, detail="Book not found or no chapters")
    return [
        ChapterSummary(chapter_id=ch.chapter_id, title=ch.title, book_id=ch.book_id)
        for ch in chapters
    ]


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterDetail)
async def get_chapter(book_id: str, chapter_id: str):
    """获取某章节的完整内容。"""
    loader = get_loader()
    chapter = loader.get_chapter(book_id, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ChapterDetail(
        chapter_id=chapter.chapter_id,
        title=chapter.title,
        book_id=chapter.book_id,
        content=chapter.content,
    )


class SourceResponse(BaseModel):
    """原典分块。``has_more`` 为真时前端可继续请求下一块。"""

    book_id: str
    title: str
    content: str
    offset: int
    limit: int
    total: int
    has_more: bool


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
        raise HTTPException(status_code=404, detail="Source text not available")

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
