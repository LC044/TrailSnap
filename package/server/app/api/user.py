from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.user import UserCreate, UserResponse, UserUpdateMe
from app.crud.user import create, reset_password, delete
from app.dependencies import get_db
from app.api import deps
from app.db.models.user import User
from app.db.models.photo import Photo
from app.db.models.album import Album

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve users.
    """
    if not current_user.is_superuser:
        return [current_user]
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.post("/", response_model=UserResponse)
def create_new_user(
    user_in: UserCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Create new user.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")

    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
         raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
        
    return create(db, user_in)

@router.put("/{user_id}/password", response_model=UserResponse)
def update_user_password(
    user_id: UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update user password.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not current_user.is_superuser and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
        
    password = payload.get("password")
    if not password or len(password) < 6:
         raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
         
    user = reset_password(db, user, password)
    return user

@router.get("/me", response_model=UserResponse)
def read_user_me(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.put("/me", response_model=UserResponse)
def update_user_me(
    payload: UserUpdateMe,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update current user.
    """
    if payload.nickname is not None:
        current_user.nickname = payload.nickname
    if payload.avatar is not None:
        current_user.avatar = payload.avatar
        
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.delete("/{user_id}", response_model=UserResponse)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Delete a user.
    """
    if not current_user.is_superuser and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")

    return delete(db, user_id)
