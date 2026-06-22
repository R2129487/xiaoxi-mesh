"""小希-Mesh v2 权限控制模块

实现 RBAC (基于角色的访问控制)：
- admin: 管理员，拥有所有权限
- agent: 智能体，可发送/接收消息、执行任务、调用公开能力
- external: 外部系统，只读 + 接收消息
- readonly: 只读，仅查看
"""
from __future__ import annotations
import logging
from typing import Optional

log = logging.getLogger("xiaoxi-mesh.permissions")


# ── 默认权限配置 ──

DEFAULT_PERMISSIONS = {
    "admin": {
        "message": ["send", "receive", "broadcast"],
        "file": ["upload", "download", "delete"],
        "command": ["execute", "manage"],
        "task": ["create", "delegate", "manage", "complete", "delete"],
        "agent": ["register", "manage", "delete"],
        "admin": ["manage", "config", "audit"],
        "token": ["create", "revoke", "list"],
        "invoke": ["call", "manage"],
    },
    "agent": {
        "message": ["send", "receive"],
        "file": ["upload", "download"],
        "command": ["execute"],
        "task": ["create", "complete", "delegate"],
        "agent": ["list"],
        "token": ["list"],
        "invoke": ["call"],
    },
    "external": {
        "message": ["receive"],
        "file": ["download"],
        "command": [],
        "task": ["list"],
        "agent": ["list"],
        "admin": [],
        "token": [],
        "invoke": [],
    },
    "readonly": {
        "message": ["receive"],
        "file": ["download"],
        "command": [],
        "task": ["list"],
        "agent": ["list"],
        "admin": [],
        "token": [],
        "invoke": [],
    },
}


class PermissionManager:
    """权限管理器

    基于 RBAC 模型提供权限检查、管理功能。
    """

    def __init__(self, custom_config: dict = None):
        # 深拷贝默认配置
        self._permissions: dict[str, dict[str, list[str]]] = {}
        for role, resources in DEFAULT_PERMISSIONS.items():
            self._permissions[role] = {}
            for resource, actions in resources.items():
                self._permissions[role][resource] = list(actions)

        # 应用自定义配置
        if custom_config:
            for role, resources in custom_config.items():
                if role not in self._permissions:
                    self._permissions[role] = {}
                for resource, actions in resources.items():
                    if isinstance(actions, list):
                        self._permissions[role][resource] = actions

    def check(self, role: str, resource: str, action: str) -> bool:
        role_perms = self._permissions.get(role, {})
        resource_actions = role_perms.get(resource, [])
        return action in resource_actions

    def get_role_permissions(self, role: str) -> dict[str, list[str]]:
        return dict(self._permissions.get(role, {}))

    def get_all_roles(self) -> list[str]:
        return list(self._permissions.keys())

    def set_role_permissions(self, role: str, permissions: dict[str, list[str]]):
        self._permissions[role] = permissions
        log.info(f"权限变更: 角色 {role} 的权限已更新")

    def add_permission(self, role: str, resource: str, action: str):
        if role not in self._permissions:
            self._permissions[role] = {}
        if resource not in self._permissions[role]:
            self._permissions[role][resource] = []
        if action not in self._permissions[role][resource]:
            self._permissions[role][resource].append(action)

    def remove_permission(self, role: str, resource: str, action: str):
        if role in self._permissions and resource in self._permissions[role]:
            if action in self._permissions[role][resource]:
                self._permissions[role][resource].remove(action)

    def get_permissions_for_token(self, role: str) -> list[dict]:
        perms = self.get_role_permissions(role)
        result = []
        for resource, actions in perms.items():
            for action in actions:
                result.append({"resource": resource, "action": action})
        return result

    def check_token_permissions(self, token_permissions: list[dict],
                                 resource: str, action: str) -> bool:
        for perm in token_permissions:
            if perm.get("resource") == resource and perm.get("action") == action:
                return True
        return False

    @staticmethod
    def is_valid_role(role: str) -> bool:
        return role in ("admin", "agent", "external", "readonly")
