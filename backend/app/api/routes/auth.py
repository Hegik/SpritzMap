import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update, func
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import User
from app.models.price_entry import PriceEntry
from app.models.location import Location
from app.models.drink import Drink
from app.models.user_deletion_log import UserDeletionLog
from app.models.photo import Photo
from app.api.routes.photos import photo_to_dict, delete_photo_files
from app.core.config import settings
from app.schemas.user import UserRegister, UserOut, Token, ForgotPassword, ResetPassword, UpdateProfile, UpdatePassword
from fastapi.responses import JSONResponse
from app.api.deps import get_current_user, moderated_city_ids
from app.services.email import send_verification_email, send_reset_email
from app.services import oidc
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


# ── Übergang zu Authentik (siehe routes/oidc.py) ──────────────────────────────
# legacy:    alles wie bisher
# both:      alter Login/Reset läuft weiter, aber KEINE neuen lokalen Konten (sonst entstünden unverknüpfte Konten)
# authentik: lokale Konten sind abgeschaltet
def legacy_registration() -> None:
    if settings.AUTH_MODE != "legacy":
        raise HTTPException(status_code=410, detail="Registrierung läuft jetzt über den SpritzMap-Login (Authentik)")


def legacy_login() -> None:
    if settings.AUTH_MODE == "authentik":
        raise HTTPException(status_code=410, detail="Anmeldung läuft jetzt über den SpritzMap-Login (Authentik)")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(legacy_registration)])
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


@router.get("/verify", dependencies=[Depends(legacy_login)])
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.verification_token == token))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Ungültiger oder abgelaufener Link")

    user.is_verified = True
    user.verification_token = None
    await db.commit()
    return {"detail": "E-Mail-Adresse bestätigt"}


@router.post("/login", response_model=Token, dependencies=[Depends(legacy_login)])
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="E-Mail-Adresse noch nicht bestätigt")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token}


@router.post("/forgot-password", dependencies=[Depends(legacy_login)])
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    # Immer 200 zurückgeben — kein Hinweis ob E-Mail existiert
    if not user or user.authentik_sub:
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


@router.post("/reset-password", dependencies=[Depends(legacy_login)])
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
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out = UserOut.model_validate(current_user)
    allowed = await moderated_city_ids(current_user, db)
    out.moderated_city_ids = None if allowed is None else sorted(allowed)
    return out


@router.put("/me", response_model=UserOut, dependencies=[Depends(legacy_login)])
async def update_me(
    data: UpdateProfile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.hashed_password or not verify_password(data.current_password, current_user.hashed_password):
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


@router.put("/me/password", dependencies=[Depends(legacy_login)])
async def change_password(
    data: UpdatePassword,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.hashed_password or not verify_password(data.current_password, current_user.hashed_password):
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
                "glass_type": e.glass_type.value if e.glass_type else None,
                "ai_color_value": e.ai_color_value,
                "ai_glass_type": e.ai_glass_type.value if e.ai_glass_type else None,
            }
            for e in user_with_entries.price_entries
        ],
        "photos": [
            photo_to_dict(p)
            for p in (await db.execute(select(Photo).where(Photo.user_id == current_user.id))).scalars().all()
        ],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="spritzmap-meine-daten.json"'},
    )


@router.get("/me/entries")
async def my_entries(
    page: int = 1,
    page_size: int = 12,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count()).select_from(PriceEntry).where(PriceEntry.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    rows_result = await db.execute(
        select(PriceEntry, Location, Drink)
        .join(Location, PriceEntry.location_id == Location.id)
        .join(Drink, PriceEntry.drink_id == Drink.id)
        .where(PriceEntry.user_id == current_user.id)
        .order_by(PriceEntry.reported_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_result.all()

    entry_ids = [entry.id for entry, _, _ in rows]
    photos_by_entry: dict[int, list[dict]] = {}
    if entry_ids:
        photo_rows = await db.execute(
            select(Photo).where(Photo.price_entry_id.in_(entry_ids)).order_by(Photo.created_at)
        )
        for p in photo_rows.scalars().all():
            photos_by_entry.setdefault(p.price_entry_id, []).append(photo_to_dict(p))

    items = [
        {
            "id": entry.id,
            "location_id": entry.location_id,
            "location_name": location.name,
            "drink_id": entry.drink_id,
            "drink_name": drink.name,
            "drink_color_hex": drink.color_hex,
            "price": entry.price,
            "price_tier": settings.get_price_tier(entry.price) if not entry.unavailable else None,
            "color_value": entry.color_value,
            "reported_at": entry.reported_at.isoformat(),
            "note": entry.note,
            "unavailable": entry.unavailable,
            "is_current": entry.is_current,
            "glass_type": entry.glass_type.value if entry.glass_type else None,
            "ai_glass_type": entry.ai_glass_type.value if entry.ai_glass_type else None,
            "photos": photos_by_entry.get(entry.id, []),
        }
        for entry, location, drink in rows
    ]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.delete("/me")
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Fotos können Personen zeigen → beim Löschen des Kontos vollständig entfernen
    user_photos = (await db.execute(select(Photo).where(Photo.user_id == current_user.id))).scalars().all()
    for photo in user_photos:
        await db.delete(photo)

    # Anonymize all price entries by this user
    await db.execute(
        sa_update(PriceEntry)
        .where(PriceEntry.user_id == current_user.id)
        .values(user_id=None)
    )
    linked = current_user.authentik_sub is not None
    db.add(UserDeletionLog())
    await db.delete(current_user)
    await db.commit()
    for photo in user_photos:
        delete_photo_files(photo)
    # Das Authentik-Konto löscht der Nutzer selbst im Löschflow (nur reine SpritzMap-Konten, siehe Blueprint).
    # So braucht das Backend kein Authentik-Token mit Rechten über andere Konten.
    return {"deleted": True, "unenrollment_url": oidc.unenrollment_url() if linked else None}
