"""Login über Authentik (OIDC). Siehe services/oidc.py und authentik/README.md."""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.oidc_login import OidcLogin
from app.models.user import User
from app.services import oidc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

LOGIN_TTL = timedelta(minutes=15)
CODE_TTL = timedelta(seconds=60)


def _oidc_enabled() -> None:
    if settings.AUTH_MODE not in ("both", "authentik"):
        raise HTTPException(status_code=404, detail="Authentik-Login ist nicht aktiviert")


def _safe_next(next_path: str | None) -> str:
    # Nur relative Pfade innerhalb von SpritzMap – kein Open Redirect
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    return next_path[:500]


def _frontend(path: str, **params) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}{path}{query}", status_code=302)


@router.get("/config")
async def auth_config():
    """Welcher Login gilt – das Frontend richtet Anmelden/Registrieren/Kontoseite danach aus."""
    enabled = settings.AUTH_MODE in ("both", "authentik")
    return {
        "mode": settings.AUTH_MODE,
        "account_url": oidc.account_url() if enabled else None,
        "unenrollment_url": oidc.unenrollment_url() if enabled else None,
    }


@router.get("/oidc/login")
@limiter.limit("30/minute")
async def oidc_login(
    request: Request,
    next: str | None = None,
    signup: bool = False,
    db: AsyncSession = Depends(get_db),
):
    _oidc_enabled()
    # Aufräumen: abgelaufene, nie abgeschlossene Logins
    await db.execute(delete(OidcLogin).where(OidcLogin.created_at < datetime.now(timezone.utc) - LOGIN_TTL))

    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = oidc.new_pkce()
    db.add(OidcLogin(state=state, code_verifier=verifier, nonce=nonce, next_path=_safe_next(next)))
    await db.commit()

    try:
        url = await oidc.authorize_url(state, nonce, challenge)
    except Exception as exc:
        logger.warning("Authentik nicht erreichbar: %s", exc)
        return _frontend("/auth/callback", error="unavailable")
    return RedirectResponse(oidc.enrollment_url(url) if signup else url, status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    _oidc_enabled()
    login = None
    if state:
        login = (await db.execute(select(OidcLogin).where(OidcLogin.state == state))).scalar_one_or_none()
    if login is None or login.user_id is not None or login.created_at < datetime.now(timezone.utc) - LOGIN_TTL:
        return _frontend("/auth/callback", error="expired")
    if error or not code:
        # z. B. access_denied: Konto hat keinen Zugriff auf die SpritzMap-Application
        await db.delete(login)
        await db.commit()
        return _frontend("/auth/callback", error=error or "cancelled")

    try:
        tokens = await oidc.exchange_code(code, login.code_verifier)
        claims = await oidc.verify_id_token(tokens["id_token"], tokens["access_token"], login.nonce)
    except (oidc.OidcError, KeyError) as exc:
        logger.warning("OIDC-Callback abgelehnt: %s", exc)
        await db.delete(login)
        await db.commit()
        return _frontend("/auth/callback", error="invalid")

    sub = str(claims["sub"])
    email = (claims.get("email") or "").strip().lower() or None
    username = (claims.get("preferred_username") or claims.get("nickname") or "").strip()[:50]

    user = (await db.execute(select(User).where(User.authentik_sub == sub))).scalar_one_or_none()
    if user is None:
        # Keine Verknüpfung über die E-Mail: Bestandskonten sind per Migration über die UUID verknüpft.
        # Ein unverknüpftes Legacy-Konto mit derselben Adresse ist ein Fall für den Admin, nicht für Automatik.
        if email and (await db.execute(select(User.id).where(User.email == email))).first():
            logger.warning("OIDC-Login: E-Mail gehört zu einem unverknüpften Konto (sub=%s)", sub)
            await db.delete(login)
            await db.commit()
            return _frontend("/auth/callback", error="account_conflict")
        user = User(
            authentik_sub=sub,
            email=email or f"{sub}@users.invalid",
            username=await _free_username(db, username or f"spritzer-{sub[:8]}"),
            hashed_password=None,
            is_verified=True,
        )
        db.add(user)
        await db.flush()
    else:
        # Authentik ist die Quelle für Name und Adresse; Kollisionen lassen den alten Wert stehen
        if email and email != user.email and not (await db.execute(select(User.id).where(User.email == email))).first():
            user.email = email
        if username and username != user.username and not (
            await db.execute(select(User.id).where(User.username == username))
        ).first():
            user.username = username
        user.is_verified = True

    if not user.is_active:
        await db.delete(login)
        await db.commit()
        return _frontend("/auth/callback", error="disabled")

    login.user_id = user.id
    login.login_code = secrets.token_urlsafe(32)
    login.login_code_expires = datetime.now(timezone.utc) + CODE_TTL
    await db.commit()
    # Nur ein kurzlebiger Einmal-Code in der URL, nie das Token selbst
    return _frontend("/auth/callback", code=login.login_code)


class ExchangeRequest(BaseModel):
    code: str


@router.post("/oidc/exchange")
@limiter.limit("30/minute")
async def oidc_exchange(request: Request, body: ExchangeRequest, db: AsyncSession = Depends(get_db)):
    _oidc_enabled()
    login = (await db.execute(select(OidcLogin).where(OidcLogin.login_code == body.code))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if login is None or login.exchanged or login.login_code_expires is None or login.login_code_expires < now:
        raise HTTPException(status_code=400, detail="Anmeldung abgelaufen – bitte erneut anmelden")
    next_path = login.next_path
    user_id = login.user_id
    await db.delete(login)  # einmalig
    await db.commit()
    return {"access_token": create_access_token({"sub": str(user_id)}), "token_type": "bearer", "next": next_path}


@router.get("/oidc/logout-url")
async def oidc_logout_url():
    _oidc_enabled()
    try:
        return {"url": await oidc.logout_url(f"{settings.FRONTEND_URL.rstrip('/')}/")}
    except Exception:
        return {"url": f"{settings.FRONTEND_URL.rstrip('/')}/"}


async def _free_username(db: AsyncSession, wanted: str) -> str:
    base = wanted[:44] or "spritzer"
    candidate, n = base, 2
    while (await db.execute(select(User.id).where(User.username == candidate))).first():
        candidate, n = f"{base}-{n}", n + 1
    return candidate
