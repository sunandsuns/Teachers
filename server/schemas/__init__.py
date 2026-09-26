"""接口契约（出入参模型）。

这里是**接口长什么样**的唯一来源：routers 从这里取模型，OpenAPI 从这里生成，
前端的类型也由它生成的 ``openapi.json`` 推出来。

放在 routers 之外的另一个理由是分层：``routers/`` 只该负责"把 HTTP 请求交给
服务层、把结果包成响应"，而模型是双方共用的词汇表——它不该住在一侧。

按域分模块，因为 66 个接口的模型堆在一个文件里会变成新的屎山；``common`` 放
跨域共用的那几个（错误体、删除结果、成功回执）。
"""

from __future__ import annotations


from .common import ErrorBody, DeleteResponse, OkResponse, MessageResponse, RowMutationResponse

from .system import IndexProgress, HealthResponse, RootResponse

from .books import BookSummary, ChapterSummary, ChapterDetail, SourceResponse

from .auth import RegisterRequest, LoginRequest, ChangePasswordRequest, UserInfo, MeResponse

from .search import SearchResponseItem, SearchResponse

from .ask import LLMEndpoint, ConversationTurn, AskRequest, AskResponse, AskPlanRequest, ChatMessage, AskPlanResponse, AskSaveRequest, AskStatusResponse, ProbeResponse

from .history import HistoryItem, TopicItem, HistoryListResponse, TopicListResponse, HistoryStatusResponse, BulkDeleteRequest

from .profile import TraitItem, FigureInfo, ProfileResponse, ExtractResponse, ExtractRequest, FigureResponse, AvatarRequest, AvatarResponse

from .kb import KbNodeModel, KbEdgeModel, GraphResponse, KbLinkModel, ThemeRowModel, CrossRefModel, NodeDetailResponse

from .insight import InsightItem, InsightListResponse, ThemeListResponse

from .shelf import BookSearchResponse, CandidateIn, SearchRequest, AddBookRequest, UpdateBookRequest, ShelfBookOut, ShelfResponse

from .admin import UserRow, UpdateUserRequest, ResetPasswordRequest, ReviewRow, ReviewRequest, OverviewResponse, PublicBookRow, TableInfo, TableColumn, TableDetailResponse, AuditRow


