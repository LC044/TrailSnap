import traceback
from typing import Generator, Optional
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.core.system_config import system_config
from app.crud import user as crud_user
from app.db.models.user import User
from app.schemas.token import TokenPayload
from app.dependencies import get_db

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def get_current_user(
        db: Session = Depends(get_db),
        token: str = Depends(reusable_oauth2)
) -> User:
    if token.startswith("ts_"):
        from app.crud.agent_token import get_token_by_string
        from datetime import datetime
        agent_token = get_token_by_string(db, token)
        if not agent_token:
            raise HTTPException(status_code=401, detail="Invalid token")
        if agent_token.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail="Token has expired")
        user = crud_user.get(db, id=agent_token.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    try:
        payload = jwt.decode(
            token, system_config.config.security.secret_key, algorithms=[system_config.config.security.algorithm]
        )
        token_data = TokenPayload(**payload)
    except ExpiredSignatureError:  # 专门捕获令牌过期异常
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # 401 未授权
            detail="Token has expired",  # 明确提示令牌过期
            headers={"WWW-Authenticate": "Bearer"},  # 符合OAuth2规范
        )
    except (JWTError, ValidationError):  # 捕获其他JWT验证错误
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,  # 403 禁止访问（其他验证错误）
            detail="Could not validate credentials",
        )

    user = crud_user.get(db, id=token_data.sub)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def resolve_user_from_token(token: str, db: Session) -> User:
    """Resolve the user from a query-param token. EventSource cannot send
    an Authorization header, so SSE / polling-fallback endpoints accept
    the JWT (or `ts_` prefixed agent token) as a `?token=` query param
    instead. Mirrors the logic in `get_current_user`."""
    if not token:
        raise HTTPException(status_code=401, detail='Missing token')
    if token.startswith('ts_'):
        from app.crud.agent_token import get_token_by_string
        agent_token = get_token_by_string(db, token)
        if not agent_token:
            raise HTTPException(status_code=401, detail='Invalid token')
        if agent_token.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail='Token has expired')
        user = crud_user.get(db, id=agent_token.user_id)
        if not user:
            raise HTTPException(status_code=401, detail='User not found')
        return user
    try:
        payload = jwt.decode(
            token,
            system_config.config.security.secret_key,
            algorithms=[system_config.config.security.algorithm],
        )
        token_data = TokenPayload(**payload)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token has expired')
    except (JWTError, ValidationError):
        raise HTTPException(status_code=403, detail='Could not validate credentials')
    user = crud_user.get(db, id=token_data.sub)
    if not user:
        raise HTTPException(status_code=401, detail='User not found')
    return user
