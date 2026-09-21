"""阶段 8 权限验收契约。

这里固化的是验收语义和测试数据，不替代现有 ``rbac`` 或文档访问 Service。
真实请求仍须经过数据库中的实时角色、资源权限和业务 Service；本模块不读
数据库，也不返回任何文档正文、价格或路径。
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionRole(str, Enum):
    ADMIN = "ADMIN"
    PRODUCT_MANAGER = "PRODUCT_MANAGER"
    SALES = "SALES"


class PermissionOperation(str, Enum):
    DOCUMENT_LIST = "document_list"
    DOCUMENT_DETAIL = "document_detail"
    DOCUMENT_DOWNLOAD = "document_download"
    RAG_SEARCH = "rag_search"
    TOOL_SEARCH_PRODUCT_KNOWLEDGE = "tool_search_product_knowledge"
    TOOL_READ_DOCUMENT = "tool_read_document"
    TOOL_QUERY_PRODUCT_PRICE = "tool_query_product_price"
    TOOL_COMPARE_PRODUCTS = "tool_compare_products"
    INTERNAL_QUOTE = "internal_quote"
    AUDIT_QUERY = "audit_query"
    # 常用简称/旧接口名称均指向同一个操作值，不增加新的矩阵项。
    DOCUMENT_READ = "document_detail"
    RAG = "rag_search"
    TOOL_READ = "tool_read_document"
    PRICE_INTERNAL = "internal_quote"
    AUDIT = "audit_query"
    LIST = "document_list"
    READ = "document_detail"
    DOWNLOAD = "document_download"
    SEARCH = "rag_search"
    INVOKE = "tool_compare_products"
    QUERY = "tool_query_product_price"


class ResourceType(str, Enum):
    DOCUMENT = "DOCUMENT"
    RAG = "RAG"
    TOOL = "TOOL"
    PRICE = "PRICE"
    AUDIT = "AUDIT"


class PermissionOutcome(str, Enum):
    """验收对外可观察的结果。

    ``FORBIDDEN`` 和 ``NOT_FOUND`` 的值直接采用 HTTP 状态，便于测试矩阵
    与 API 响应一一对应；列表/RAG 的资源级拒绝使用 200 + ``FILTERED``。
    """

    ALLOW = "ALLOW"
    FORBIDDEN = "403"
    NOT_FOUND = "404"
    FILTERED = "FILTERED"
    ALLOWED = "ALLOW"
    OK = "ALLOW"
    DENIED = "403"
    NOT_ACCESSIBLE = "404"


class ResourceScope(str, Enum):
    GLOBAL = "GLOBAL"
    AUTHORIZED_ONLY = "AUTHORIZED_ONLY"
    NONE = "NONE"


class StrictPermissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=False)


def _enum_or_member(value: object, enum_type: type[Enum]) -> object:
    if not isinstance(value, str):
        return value
    value = value.strip()
    try:
        return enum_type(value)
    except ValueError:
        try:
            return enum_type[value]
        except KeyError:
            return value


class PermissionExpectation(StrictPermissionModel):
    """一个角色对一个操作的预期结果。"""

    role: PermissionRole
    operation: PermissionOperation
    outcome: PermissionOutcome
    http_status: int = Field(ge=200, le=599)
    resource_scope: ResourceScope
    audit_result: str = Field(pattern=r"^(SUCCESS|FAILED|DENIED)$")
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("role", "operation", "outcome", "resource_scope", mode="before")
    @classmethod
    def trim_enum_input(cls, value: object) -> object:
        # 既接受枚举值（如 ``document_list``），也接受验收表中常见的成员名
        # （如 ``DOCUMENT_LIST``），最终仍收敛为固定 Enum。
        for enum_type in (PermissionRole, PermissionOperation, PermissionOutcome, ResourceScope):
            candidate = _enum_or_member(value, enum_type)
            if isinstance(candidate, Enum):
                return candidate
        return value

    @classmethod
    def for_result(
        cls,
        role: PermissionRole | str,
        operation: PermissionOperation | str,
        outcome: PermissionOutcome,
        *,
        reason: str,
        resource_scope: ResourceScope = ResourceScope.AUTHORIZED_ONLY,
    ) -> "PermissionExpectation":
        if not isinstance(outcome, PermissionOutcome):
            outcome = _enum_or_member(outcome, PermissionOutcome)  # type: ignore[assignment]
        if not isinstance(outcome, PermissionOutcome):
            raise ValueError("未知的权限判定结果")
        status = {
            PermissionOutcome.ALLOW: 200,
            PermissionOutcome.FILTERED: 200,
            PermissionOutcome.FORBIDDEN: 403,
            PermissionOutcome.NOT_FOUND: 404,
        }[outcome]
        audit = "SUCCESS" if outcome in (PermissionOutcome.ALLOW, PermissionOutcome.FILTERED) else "DENIED"
        return cls(
            role=role,
            operation=operation,
            outcome=outcome,
            http_status=status,
            resource_scope=resource_scope,
            audit_result=audit,
            reason=reason,
        )

    @property
    def allowed(self) -> bool:
        return self.outcome in (PermissionOutcome.ALLOW, PermissionOutcome.FILTERED)

    @property
    def status_code(self) -> int:
        return self.http_status


_ALL_ROLES = tuple(PermissionRole)


def _build_matrix() -> dict[PermissionOperation, dict[PermissionRole, PermissionExpectation]]:
    matrix: dict[PermissionOperation, dict[PermissionRole, PermissionExpectation]] = {}

    def add(
        operation: PermissionOperation,
        outcomes: Mapping[PermissionRole, PermissionOutcome],
        scope: ResourceScope,
        reason: str,
    ) -> None:
        matrix[operation] = {
            role: PermissionExpectation.for_result(
                role,
                operation,
                outcomes[role],
                resource_scope=scope,
                reason=reason,
            )
            for role in _ALL_ROLES
        }

    # 列表与检索只返回允许资源；因此资源级拒绝是 FILTERED，而不是暴露 404。
    for operation in (
        PermissionOperation.DOCUMENT_LIST,
        PermissionOperation.RAG_SEARCH,
        PermissionOperation.TOOL_SEARCH_PRODUCT_KNOWLEDGE,
    ):
        add(
            operation,
            {role: PermissionOutcome.ALLOW for role in _ALL_ROLES},
            ResourceScope.AUTHORIZED_ONLY,
            "仅返回当前角色获授权且状态可用的资源",
        )

    # 详情、下载和 read_document 对未授权/不存在统一使用 404 语义。
    for operation in (
        PermissionOperation.DOCUMENT_DETAIL,
        PermissionOperation.DOCUMENT_DOWNLOAD,
        PermissionOperation.TOOL_READ_DOCUMENT,
    ):
        add(
            operation,
            {role: PermissionOutcome.ALLOW for role in _ALL_ROLES},
            ResourceScope.AUTHORIZED_ONLY,
            "资源不存在或当前角色无权访问时统一返回 404",
        )

    add(
        PermissionOperation.TOOL_QUERY_PRODUCT_PRICE,
        {role: PermissionOutcome.ALLOW for role in _ALL_ROLES},
        ResourceScope.AUTHORIZED_ONLY,
        "价格类型在工具内按当前角色再次过滤",
    )
    add(
        PermissionOperation.TOOL_COMPARE_PRODUCTS,
        {role: PermissionOutcome.ALLOW for role in _ALL_ROLES},
        ResourceScope.AUTHORIZED_ONLY,
        "比较只聚合本轮已授权的产品、价格和引用",
    )
    add(
        PermissionOperation.INTERNAL_QUOTE,
        {
            PermissionRole.ADMIN: PermissionOutcome.ALLOW,
            PermissionRole.PRODUCT_MANAGER: PermissionOutcome.ALLOW,
            PermissionRole.SALES: PermissionOutcome.FORBIDDEN,
        },
        ResourceScope.AUTHORIZED_ONLY,
        "内部报价仅允许管理员和产品经理",
    )
    add(
        PermissionOperation.AUDIT_QUERY,
        {
            PermissionRole.ADMIN: PermissionOutcome.ALLOW,
            PermissionRole.PRODUCT_MANAGER: PermissionOutcome.FORBIDDEN,
            PermissionRole.SALES: PermissionOutcome.FORBIDDEN,
        },
        ResourceScope.GLOBAL,
        "审计日志为管理员只读资源",
    )
    return matrix


_MATRIX = _build_matrix()

# 外部只能读取快照，避免测试/页面随意改变契约。
PERMISSION_MATRIX: Mapping[PermissionOperation, Mapping[PermissionRole, PermissionExpectation]] = MappingProxyType(
    {operation: MappingProxyType(values) for operation, values in _MATRIX.items()}
)
ACCESS_MATRIX = PERMISSION_MATRIX
PERMISSION_ACCEPTANCE_MATRIX = PERMISSION_MATRIX
ROLE_MATRIX: Mapping[PermissionRole, Mapping[PermissionOperation, PermissionOutcome]] = MappingProxyType(
    {
        role: MappingProxyType({operation: PERMISSION_MATRIX[operation][role].outcome for operation in PermissionOperation})
        for role in PermissionRole
    }
)
PERMISSION_MATRIX_BY_ROLE = ROLE_MATRIX
# Role-oriented view is useful for RBAC tables; operation-oriented
# ``PERMISSION_MATRIX`` remains the canonical lookup for HTTP contracts.
ROLE_PERMISSION_MATRIX = ROLE_MATRIX


_RESOURCE_NOT_FOUND_OPERATIONS = frozenset(
    {
        PermissionOperation.DOCUMENT_DETAIL,
        PermissionOperation.DOCUMENT_DOWNLOAD,
        PermissionOperation.TOOL_READ_DOCUMENT,
    }
)
_FILTER_OPERATIONS = frozenset(
    {
        PermissionOperation.DOCUMENT_LIST,
        PermissionOperation.RAG_SEARCH,
        PermissionOperation.TOOL_SEARCH_PRODUCT_KNOWLEDGE,
    }
)

# 资源不匹配时的统一语义，供验收用例直接引用。
UNAUTHORIZED_RESOURCE_OUTCOMES: Mapping[PermissionOperation, PermissionOutcome] = MappingProxyType(
    {
        **{operation: PermissionOutcome.FILTERED for operation in _FILTER_OPERATIONS},
        **{operation: PermissionOutcome.NOT_FOUND for operation in _RESOURCE_NOT_FOUND_OPERATIONS},
        PermissionOperation.TOOL_QUERY_PRODUCT_PRICE: PermissionOutcome.FORBIDDEN,
        PermissionOperation.TOOL_COMPARE_PRODUCTS: PermissionOutcome.FORBIDDEN,
        PermissionOperation.INTERNAL_QUOTE: PermissionOutcome.FORBIDDEN,
        PermissionOperation.AUDIT_QUERY: PermissionOutcome.FORBIDDEN,
    }
)

def _build_sensitive_matrix() -> Mapping[PermissionRole, Mapping[PermissionOperation, PermissionOutcome]]:
    """固定敏感文档夹具下的角色结果，供验收表直接读取。"""

    result: dict[PermissionRole, dict[PermissionOperation, PermissionOutcome]] = {}
    for role in PermissionRole:
        row: dict[PermissionOperation, PermissionOutcome] = {}
        for operation in PermissionOperation:
            if operation in (*_FILTER_OPERATIONS, *_RESOURCE_NOT_FOUND_OPERATIONS):
                # 管理员可看到敏感文档，其余角色按夹具隐藏/过滤。
                row[operation] = (
                    PermissionOutcome.ALLOW
                    if role is PermissionRole.ADMIN
                    else UNAUTHORIZED_RESOURCE_OUTCOMES[operation]
                )
            else:
                # 价格/比较/内部报价/审计沿用角色本身的功能权限。
                row[operation] = PERMISSION_MATRIX[operation][role].outcome
        result[role] = row
    return MappingProxyType({role: MappingProxyType(row) for role, row in result.items()})


SENSITIVE_PERMISSION_MATRIX = _build_sensitive_matrix()
DOCUMENT_ACCESS_MATRIX = SENSITIVE_PERMISSION_MATRIX


def get_permission_expectation(
    role: PermissionRole | str,
    operation: PermissionOperation | str,
) -> PermissionExpectation:
    """取得静态验收矩阵中的一项。"""

    try:
        normalized_role = role if isinstance(role, PermissionRole) else _enum_or_member(role, PermissionRole)
        normalized_operation = (
            operation if isinstance(operation, PermissionOperation) else _enum_or_member(operation, PermissionOperation)
        )
        if not isinstance(normalized_role, PermissionRole) or not isinstance(normalized_operation, PermissionOperation):
            raise ValueError("未知的权限角色或操作")
        return PERMISSION_MATRIX[normalized_operation][normalized_role]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("未知的权限角色或操作") from exc


def evaluate_permission(
    role: PermissionRole | str,
    operation: PermissionOperation | str,
    *,
    resource_allowed: bool = True,
) -> PermissionExpectation:
    """将资源是否匹配当前角色映射为验收中的 ALLOW/403/404/FILTERED。

    该函数是纯契约辅助函数，实际服务仍需在数据库查询和工具执行前鉴权。
    """

    expected = get_permission_expectation(role, operation)
    if resource_allowed:
        return expected
    if expected.outcome is PermissionOutcome.FORBIDDEN:
        return expected
    if expected.operation in _FILTER_OPERATIONS:
        return expected.model_copy(
            update={
                "outcome": PermissionOutcome.FILTERED,
                "http_status": 200,
                "audit_result": "SUCCESS",
                "reason": "资源已从列表或检索结果中过滤",
            }
        )
    if expected.operation in _RESOURCE_NOT_FOUND_OPERATIONS:
        return expected.model_copy(
            update={
                "outcome": PermissionOutcome.NOT_FOUND,
                "http_status": 404,
                "audit_result": "DENIED",
                "reason": "资源不存在或当前角色无权访问",
            }
        )
    # 价格和比较等操作的资源级拒绝不暴露内部数据，沿用 403。
    return expected.model_copy(
        update={
            "outcome": PermissionOutcome.FORBIDDEN,
            "http_status": 403,
            "audit_result": "DENIED",
            "reason": "当前角色没有访问该资源的权限",
        }
    )


def iter_permission_expectations() -> tuple[PermissionExpectation, ...]:
    return tuple(expectation for values in PERMISSION_MATRIX.values() for expectation in values.values())


PERMISSION_CASES = iter_permission_expectations()


# 便于不同层按自然语言命名引用同一契约，不复制数据。
PermissionResult = PermissionExpectation
PermissionCheck = PermissionExpectation
PermissionCase = PermissionExpectation
AccessDecision = PermissionOutcome
PermissionDecision = PermissionOutcome
PermissionAction = PermissionOperation
ResourceAction = PermissionOperation
Role = PermissionRole
Operation = PermissionOperation
permission_result = evaluate_permission


__all__ = [
    "ACCESS_MATRIX",
    "AccessDecision",
    "Operation",
    "PERMISSION_MATRIX",
    "PERMISSION_MATRIX_BY_ROLE",
    "PERMISSION_ACCEPTANCE_MATRIX",
    "PERMISSION_CASES",
    "PermissionAction",
    "PermissionCase",
    "PermissionCheck",
    "PermissionDecision",
    "PermissionExpectation",
    "PermissionOperation",
    "PermissionOutcome",
    "PermissionResult",
    "PermissionRole",
    "ROLE_PERMISSION_MATRIX",
    "ROLE_MATRIX",
    "ResourceScope",
    "ResourceAction",
    "ResourceType",
    "Role",
    "evaluate_permission",
    "get_permission_expectation",
    "iter_permission_expectations",
    "permission_result",
    "UNAUTHORIZED_RESOURCE_OUTCOMES",
    "SENSITIVE_PERMISSION_MATRIX",
    "DOCUMENT_ACCESS_MATRIX",
]
