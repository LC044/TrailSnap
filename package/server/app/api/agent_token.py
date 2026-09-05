from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.agent_token import AGENT_TOKEN_READ_SCOPES, AgentTokenResponse, AgentTokenCreateAPI
from app.crud import agent_token as crud_agent_token
from app.crud import user as crud_user
from app.dependencies import get_db
from app.api.deps import get_current_user
from app.db.models.user import User

router = APIRouter()

@router.get("", response_model=List[AgentTokenResponse])
def get_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    获取当前用户的所有令牌。
    """
    return crud_agent_token.get_tokens_by_user(db, user_id=current_user.id)

@router.post("", response_model=AgentTokenResponse)
def create_token(
    token_in: AgentTokenCreateAPI,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    创建一个新的令牌。需要验证用户密码。
    """
    # 验证密码
    user_auth = crud_user.authenticate(db, email=current_user.email, password=token_in.password)
    if not user_auth:
        raise HTTPException(status_code=400, detail="密码错误")

    invalid_scopes = sorted(set(token_in.scopes) - set(AGENT_TOKEN_READ_SCOPES))
    if invalid_scopes:
        raise HTTPException(status_code=400, detail=f"不支持的令牌权限: {', '.join(invalid_scopes)}")
    if not token_in.scopes:
        raise HTTPException(status_code=400, detail="至少选择一个令牌权限")

    return crud_agent_token.create_agent_token(
        db=db,
        user_id=current_user.id,
        name=token_in.name,
        expires_at=token_in.expires_at,
        scopes=list(dict.fromkeys(token_in.scopes)),
    )

@router.delete("/{token_id}")
def delete_token(
    token_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    删除一个令牌。
    """
    success = crud_agent_token.delete_agent_token(db, token_id=token_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Token not found or already deleted")
    return {"message": "Token deleted successfully"}
