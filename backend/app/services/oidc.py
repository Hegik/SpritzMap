"""
OIDC-Anbindung an Authentik (Authorization Code Flow mit PKCE, Confidential Client).

Das Backend ist der OIDC-Client: Es leitet zum Login weiter, tauscht den Code gegen Tokens und prüft das
ID-Token. Danach stellt es wie bisher ein eigenes SpritzMap-JWT aus – Rollen, Städte und alle geschützten
Endpunkte bleiben unverändert.
"""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from jose import jwt

from app.core.config import settings

SCOPES = "openid email profile"
_CACHE_TTL = 3600
_discovery: tuple[float, dict] | None = None
_jwks: tuple[float, dict] | None = None


class OidcError(Exception):
    pass


def issuer() -> str:
    return f"{settings.AUTHENTIK_URL.rstrip('/')}/application/o/{settings.OIDC_APP_SLUG}/"


def server_url(public_url: str) -> tuple[str, dict]:
    """Öffentliche Authentik-URL → (URL für Server-zu-Server-Aufruf, Header).

    Mit AUTHENTIK_INTERNAL_URL geht der Aufruf direkt an den Container, der Host-Header bleibt aber der
    öffentliche – so löst Authentik dieselbe Brand und denselben Issuer auf wie im Browser.
    """
    if not settings.AUTHENTIK_INTERNAL_URL:
        return public_url, {}
    pub = urlsplit(public_url)
    internal = urlsplit(settings.AUTHENTIK_INTERNAL_URL)
    return urlunsplit((internal.scheme, internal.netloc, pub.path, pub.query, "")), {"Host": pub.netloc}


async def _get_json(public_url: str) -> dict:
    url, headers = server_url(public_url)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def discovery() -> dict:
    global _discovery
    if _discovery and time.time() - _discovery[0] < _CACHE_TTL:
        return _discovery[1]
    data = await _get_json(f"{issuer()}.well-known/openid-configuration")
    _discovery = (time.time(), data)
    return data


async def _jwks_keys(force: bool = False) -> dict:
    global _jwks
    if not force and _jwks and time.time() - _jwks[0] < _CACHE_TTL:
        return _jwks[1]
    data = await _get_json((await discovery())["jwks_uri"])
    _jwks = (time.time(), data)
    return data


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def authorize_url(state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{(await discovery())['authorization_endpoint']}?{urlencode(params)}"


def enrollment_url(authorize: str) -> str:
    """Direkt in den Registrierungs-Flow; danach setzt Authentik mit der Autorisierung fort (`next`)."""
    parts = urlsplit(authorize)
    next_path = f"{parts.path}?{parts.query}"  # Authentik akzeptiert nur relative Ziele
    return f"{settings.AUTHENTIK_URL.rstrip('/')}/if/flow/{settings.OIDC_ENROLLMENT_FLOW}/?{urlencode({'next': next_path})}"


def account_url() -> str:
    return f"{settings.AUTHENTIK_URL.rstrip('/')}/if/user/"


def unenrollment_url() -> str:
    return f"{settings.AUTHENTIK_URL.rstrip('/')}/if/flow/{settings.OIDC_UNENROLLMENT_FLOW}/"


async def logout_url(post_logout_redirect: str) -> str:
    endpoint = (await discovery()).get("end_session_endpoint")
    if not endpoint:
        return post_logout_redirect
    return f"{endpoint}?{urlencode({'post_logout_redirect_uri': post_logout_redirect, 'client_id': settings.OIDC_CLIENT_ID})}"


async def exchange_code(code: str, code_verifier: str) -> dict:
    url, headers = server_url((await discovery())["token_endpoint"])
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            url,
            headers=headers,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.OIDC_REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            # strip(): beim Einfügen in Coolify rutscht leicht ein Leerzeichen oder Zeilenumbruch mit
            auth=(settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET.strip()),
        )
    if r.status_code != 200:
        # error/error_description aus der OAuth-Antwort enthalten keine Geheimnisse, helfen aber bei der Fehlersuche
        try:
            body = r.json()
            detail = f"{body.get('error')}: {body.get('error_description', '')}"[:300]
        except ValueError:
            detail = "keine JSON-Antwort"
        raise OidcError(f"Token-Austausch fehlgeschlagen ({r.status_code}, {detail})")
    return r.json()


async def verify_id_token(id_token: str, access_token: str, nonce: str) -> dict:
    """Prüft Signatur, Issuer, Audience, Ablauf, at_hash und nonce des ID-Tokens."""
    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:
        raise OidcError("ID-Token nicht lesbar") from exc

    for attempt in range(2):  # bei unbekanntem Schlüssel (Key-Rotation) einmal JWKS neu laden
        keys = (await _jwks_keys(force=attempt == 1)).get("keys", [])
        key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key:
            break
    else:
        raise OidcError("Signaturschlüssel des ID-Tokens unbekannt")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=settings.OIDC_CLIENT_ID,
            issuer=issuer(),
            access_token=access_token,
        )
    except Exception as exc:
        raise OidcError(f"ID-Token ungültig: {exc}") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("nonce stimmt nicht")
    if not claims.get("sub"):
        raise OidcError("sub fehlt")
    return claims
