import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import User
from app.models.price_entry import PriceEntry
from app.schemas.user import UserRegister, UserOut, Token, ForgotPassword, ResetPassword, UpdateProfile, UpdatePassword
from fastapi.responses import JSONResponse
from app.api.deps import get_current_user
from app.services.email import send_verification_email, send_reset_email
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, data: UserRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    token = secrets.token_urlsafe(32)
    user = User(
        email=data.email,
        username=data.username,
        hashed_password=get_password_hash(data.password),
        is_verified=False,
        verification_token=token,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    try:
        await send_verification_email(user.email, token)
    except Exception as e:
        logger.error("Failed to send verification email: %s", e)

    return user


@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.verification_token == token))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Ungültiger oder abgelaufener Link")

    user.is_verified = True
    user.verification_token = None
    await db.commit()
    return {"detail": "E-Mail-Adresse bestätigt"}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="E-Mail-Adresse noch nicht bestätigt")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token}


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    # Immer 200 zurückgeben — kein Hinweis ob E-Mail existiert
    if not user:
        return {"detail": "Falls die E-Mail existiert, wurde ein Link gesendet"}

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    try:
        await send_reset_email(user.email, token)
    except Exception as e:
        logger.error("Failed to send reset email: %s", e)

    return {"detail": "Falls die E-Mail existiert, wurde ein Link gesendet"}


@router.post("/reset-password")
async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.reset_token == data.token))
    user = result.scalar_one_or_none()
    if not user or not user.reset_token_expires:
        raise HTTPException(status_code=400, detail="Ungültiger oder abgelaufener Link")
    if user.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Link abgelaufen")

    user.hashed_password = get_password_hash(data.password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()
    return {"detail": "Passwort erfolgreich geändert"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
async def update_me(
    data: UpdateProfile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Falsches Passwort")

    if data.username and data.username != current_user.username:
        result = await db.execute(select(User).where(User.username == data.username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Nutzername bereits vergeben")
        current_user.username = data.username

    if data.email and data.email != current_user.email:
        result = await db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="E-Mail bereits registriert")
        current_user.email = data.email

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/me/password")
async def change_password(
    data: UpdatePassword,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Falsches aktuelles Passwort")
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    return {"detail": "Passwort erfolgreich geändert"}


@router.get("/me/export")
async def export_my_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(User)
        .options(selectinload(User.price_entries))
        .where(User.id == current_user.id)
    )
    user_with_entries = result.scalar_one()

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user_with_entries.id,
            "email": user_with_entries.email,
            "username": user_with_entries.username,
            "role": user_with_entries.role.value,
            "is_active": user_with_entries.is_active,
            "is_verified": user_with_entries.is_verified,
        },
        "price_entries": [
            {
                "id": e.id,
                "location_id": e.location_id,
                "drink_id": e.drink_id,
                "price": e.price,
                "color_value": e.color_value,
                "reported_at": e.reported_at.isoformat(),
                "note": e.note,
            }
            for e in user_with_entries.price_entries
        ],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="spritzmap-meine-daten.json"'},
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Anonymize all price entries by this user
    await db.execute(
        sa_update(PriceEntry)
        .where(PriceEntry.user_id == current_user.id)
        .values(user_id=None)
    )
    await db.delete(current_user)
    await db.commit()
