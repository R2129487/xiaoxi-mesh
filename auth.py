"""小希-Mesh v2 认证模块 (JWT)

支持标准 JWT 认证和带权限信息的 Token 生成/验证。
"""
from __future__ import annotations
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from models import TokenPayload


class Auth:
    def __init__(self, secret_key: str, token_expire_hours: int = 72):
        self.secret_key = secret_key
        self.token_expire_hours = token_expire_hours

    def hash_password(self, password: str) -> str:
        """哈希密码"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, password: str, hashed: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(password.encode(), hashed.encode())

    def create_token(self, agent_id: str, role: str) -> str:
        """创建基础 JWT Token"""
        expire = datetime.now(timezone.utc) + timedelta(hours=self.token_expire_hours)
        payload = {
            "agent_id": agent_id,
            "role": role,
            "exp": expire.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def create_token_with_permissions(self, agent_id: str, role: str,
                                       permissions: List[dict] = None) -> str:
        """创建带权限信息的 JWT Token

        Args:
            agent_id: 智能体 ID
            role: 角色名
            permissions: 权限列表 [{"resource": "message", "action": "send"}, ...]

        Returns:
            JWT Token 字符串
        """
        expire = datetime.now(timezone.utc) + timedelta(hours=self.token_expire_hours)
        payload = {
            "agent_id": agent_id,
            "role": role,
            "permissions": permissions or [],
            "exp": expire.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """验证 JWT Token"""
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=["HS256"],
                options={"verify_exp": True}
            )
            return TokenPayload(
                agent_id=payload["agent_id"],
                role=payload["role"],
                exp=payload["exp"],
                permissions=payload.get("permissions", []),
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    def hash_token(self, token: str) -> str:
        """对 token 做哈希，用于存储比对（用 SHA256，因为 JWT token 可能超过 bcrypt 72字节限制）"""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()
