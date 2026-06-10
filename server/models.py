"""Pydantic v2 models shared by API and CLI."""

from pydantic import BaseModel, Field

# --- User models ---


class UserCreate(BaseModel):
    external_id: str = Field(min_length=1)
    username: str = Field(min_length=3, pattern=r"^[a-z][a-z0-9_]*[a-z0-9]$")
    display_name: str = Field(min_length=1)
    report_to: str | None = None  # username


class UserUpdate(BaseModel):
    external_id: str | None = None
    username: str | None = Field(default=None, min_length=3, pattern=r"^[a-z][a-z0-9_]*[a-z0-9]$")
    display_name: str | None = None
    report_to: str | None = None  # username
    role: str | None = None
    role_id: int | None = None
    disabled: int | None = None


class UserResponse(BaseModel):
    id: int
    external_id: str
    username: str
    display_name: str
    report_to: int | None
    role: str | None = None
    role_id: int | None = None
    disabled: int = 0


# --- Role models ---


class RoleBoardPermission(BaseModel):
    board_id: int
    actions: list[str]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    permissions: list[str] = []  # default (all-boards) actions
    board_permissions: list[RoleBoardPermission] = []  # per-board overrides


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None  # default actions
    board_permissions: list[RoleBoardPermission] | None = None  # per-board overrides


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str
    built_in: int = 0
    permissions: list[str] = []  # defaults
    board_permissions: list[RoleBoardPermission] = []  # per-board


# --- Token models ---


class TokenCreate(BaseModel):
    label: str = ""
    user_id: int | None = None  # admin can create for others


class TokenResponse(BaseModel):
    id: int
    user_id: int
    token: str  # raw token, only on creation
    label: str
    created_time: float


class TokenListResponse(BaseModel):
    id: int
    user_id: int
    label: str
    created_time: float
    last_used_time: float | None


# --- Board Permission models ---




# --- Board models ---


class BoardCreate(BaseModel):
    name: str
    description: str = ""


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    archived: bool | None = None


class BoardResponse(BaseModel):
    id: int
    name: str
    description: str
    created_time: float
    archived: bool = False


# --- Tag models ---


class TagResponse(BaseModel):
    id: int
    name: str


# --- Task models ---


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    assignee_id: int | None = None
    assignee: str | None = None  # username
    importance: int = Field(default=0, ge=0, le=100)
    estimated_effort: int = Field(default=0, ge=0)
    tags: list[str] = []
    blockers: list[int] = []
    status: str = "NEW"
    parent_task_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    importance: int | None = Field(default=None, ge=0, le=100)
    estimated_effort: int | None = Field(default=None, ge=0)


class TaskResponse(BaseModel):
    id: int
    title: str
    assignee_id: int | None
    assignee_name: str | None
    assignee_username: str | None
    description: str
    importance: int
    estimated_effort: int
    created_time: float
    status: str
    tags: list[str]
    blockers: list[int]
    parent_task_id: int | None
    creator_id: int | None = None
    text_comment_count: int = 0
    last_activity_time: float = 0


class TaskEdit(BaseModel):
    title: str | None = None
    description: str | None = None
    importance: int | None = Field(default=None, ge=0, le=100)
    estimated_effort: int | None = Field(default=None, ge=0)
    status: str | None = None
    status_reason: str | None = None  # required for NOT_REPRODUCIBLE
    assignee_id: int | None = None
    assignee: str | None = None  # username
    tags: list[str] | None = None
    blockers: list[int] | None = None
    parent_task_id: int | None = None


# --- Comment models ---


class CommentCreate(BaseModel):
    content: str
    as_user: str | None = None  # username; admin-only override of the commenter
    comment_type: str = "TEXT"


class CommentResponse(BaseModel):
    id: int
    task_id: int
    commenter_id: int | None
    commenter_name: str | None
    commenter_username: str | None
    content: str
    comment_type: str
    created_time: float


# --- Partial update models ---


class StatusUpdate(BaseModel):
    status: str


class AssigneeUpdate(BaseModel):
    user_id: int | None = None


class TagsUpdate(BaseModel):
    tags: list[str]


class BlockersUpdate(BaseModel):
    task_ids: list[int]


# --- Attachment models ---


class AttachmentResponse(BaseModel):
    id: int
    task_id: int
    board_id: int
    filename: str
    original_name: str
    content_type: str
    size: int
    uploader_id: int | None
    created_time: float
    comment_id: int | None
