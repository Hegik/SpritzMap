import io
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from PIL import Image, UnidentifiedImageError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.location import Location
from app.models.photo import Photo
from app.models.price_entry import PriceEntry
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)
router = APIRouter(tags=["photos"])


def _user_or_ip(request: Request) -> str:
    # Pro Token limitieren: hinter dem Reverse-Proxy teilen sich sonst alle Nutzer eine IP
    return request.headers.get("authorization") or get_remote_address(request)


limiter = Limiter(key_func=_user_or_ip)

ALLOWED_FORMATS = {"WEBP": "webp", "JPEG": "jpg"}


def photo_to_dict(photo: Photo) -> dict:
    return {
        "id": photo.id,
        "location_id": photo.location_id,
        "price_entry_id": photo.price_entry_id,
        "user_id": photo.user_id,
        "url": f"/media/{photo.filename}",
        "thumb_url": f"/media/{photo.thumb_filename}",
        "width": photo.width,
        "height": photo.height,
        "created_at": photo.created_at.isoformat() if photo.created_at else None,
    }


async def _validate_image(upload: UploadFile) -> tuple[bytes, str, int, int]:
    """Prüft Größe, Format und Abmessungen. Das Bild wird nicht neu kodiert —
    Kompression und EXIF-Entfernung passieren bereits im Browser."""
    data = await upload.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Bild zu groß")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            fmt, (width, height) = img.format, img.size
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(status_code=415, detail="Ungültige Bilddatei")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=415, detail="Nur WebP oder JPEG erlaubt")
    if max(width, height) > settings.MAX_IMAGE_DIMENSION:
        raise HTTPException(status_code=413, detail="Bildabmessungen zu groß")
    return data, ALLOWED_FORMATS[fmt], width, height


def delete_photo_files(photo: Photo) -> None:
    root = Path(settings.MEDIA_ROOT)
    for name in (photo.filename, photo.thumb_filename):
        try:
            (root / name).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not delete photo file %s: %s", name, e)


@router.post("/photos", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def upload_photo(
    request: Request,
    location_id: int = Form(...),
    price_entry_id: int | None = Form(None),
    file: UploadFile = File(...),
    thumb: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    location = await db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    if price_entry_id is not None:
        entry = await db.get(PriceEntry, price_entry_id)
        if not entry or entry.location_id != location_id or entry.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid price entry")

    full_data, full_ext, width, height = await _validate_image(file)
    thumb_data, thumb_ext, _, _ = await _validate_image(thumb)

    rel_dir = Path(str(location_id))
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    filename = (rel_dir / f"{stem}.{full_ext}").as_posix()
    thumb_filename = (rel_dir / f"{stem}_thumb.{thumb_ext}").as_posix()
    (Path(settings.MEDIA_ROOT) / filename).write_bytes(full_data)
    (Path(settings.MEDIA_ROOT) / thumb_filename).write_bytes(thumb_data)

    photo = Photo(
        location_id=location_id,
        price_entry_id=price_entry_id,
        user_id=current_user.id,
        filename=filename,
        thumb_filename=thumb_filename,
        width=width,
        height=height,
    )
    db.add(photo)
    try:
        await db.commit()
    except Exception:
        delete_photo_files(photo)
        raise
    await db.refresh(photo)
    return photo_to_dict(photo)


@router.get("/locations/{location_id}/photos")
async def list_location_photos(
    location_id: int,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Photo)
        .where(Photo.location_id == location_id)
        .where(Photo.is_hidden == False)
        .order_by(Photo.created_at.desc())
        .limit(min(limit, 50))
    )
    return [photo_to_dict(p) for p in result.scalars().all()]


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.user_id != current_user.id and current_user.role not in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.delete(photo)
    await db.commit()
    delete_photo_files(photo)
