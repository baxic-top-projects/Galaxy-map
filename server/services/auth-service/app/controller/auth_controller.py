from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.service import avatar_storage_service as avatar_storage
from app.service import mail_service as mailer
from app.config import settings
from app.db import EmailToken, OAuthAccount, RefreshSession, RoleAudit, User, UserRole, get_db, utcnow
from app.dto.auth import (
    AuthorizationResponse,
    AvatarPatch,
    EmailRequest,
    ExchangeCodeRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PendingVerificationResponse,
    ProfilePatch,
    PromoteRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserResponse,
    VerifyEmailRequest,
)
from app.service.auth_security_service import (
    create_access_token,
    create_oauth_state,
    create_refresh_token,
    decode_oauth_state,
    decode_token,
    hash_password,
    hash_token,
    normalize_email,
    random_token,
    verify_password,
)

router = APIRouter(prefix="/internal/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return user_agent[:512] if user_agent else None, ip[:64] if ip else None


def _issue_pair(db: Session, user: User, request: Request) -> TokenPair:
    session_id = str(uuid.uuid4())
    refresh_token, jti, refresh_expiry = create_refresh_token(user.id, session_id)
    user_agent, ip = _client_metadata(request)
    db.add(
        RefreshSession(
            id=session_id,
            user_id=user.id,
            jti=jti,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expiry,
            user_agent=user_agent,
            ip_address=ip,
        )
    )
    access_token, expires_in = create_access_token(user.id, user.email, user.role)
    db.commit()
    db.refresh(user)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


def _create_email_token(
    db: Session,
    user: User,
    purpose: str,
    minutes: int,
    plain: str | None = None,
) -> str:
    now = utcnow()
    db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    plain = plain or random_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(plain),
            expires_at=now + timedelta(minutes=minutes),
        )
    )
    db.commit()
    return plain


def _six_digit_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _consume_email_token(
    db: Session,
    plain: str,
    purpose: str,
    user_id: str | None = None,
) -> tuple[EmailToken, User]:
    conditions = [
        EmailToken.token_hash == hash_token(plain),
        EmailToken.purpose == purpose,
    ]
    if user_id is not None:
        conditions.append(EmailToken.user_id == user_id)
    row = db.scalar(
        select(EmailToken).where(*conditions).with_for_update()
    )
    if row is None or row.used_at is not None or _aware(row.expires_at) <= utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    row.used_at = utcnow()
    return row, user


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = decode_token(credentials.credentials, "access")
    user = db.get(User, claims["sub"])
    if user is None or user.email != claims.get("email") or user.role != claims.get("role"):
        raise HTTPException(status_code=401, detail="Token is no longer valid")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user


def require_internal_token(x_internal_service_token: str | None = Header(default=None)) -> None:
    expected = settings.internal_service_token.get_secret_value()
    if not expected:
        raise HTTPException(status_code=503, detail="Internal service authentication is not configured")
    if not x_internal_service_token or not secrets.compare_digest(x_internal_service_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal service token")


@router.post("/register", response_model=PendingVerificationResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email = normalize_email(str(payload.email))
    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.USER.value,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
    verification = _create_email_token(
        db,
        user,
        "VERIFY_EMAIL",
        settings.email_token_minutes,
        _six_digit_code(),
    )
    background.add_task(mailer.send_verification_email, user.email, user.display_name, verification)
    return PendingVerificationResponse(
        message="На вашу почту отправлен код подтверждения из 6 цифр.",
        email=user.email,
    )


@router.post("/login", response_model=TokenPair | PendingVerificationResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = _user_by_email(db, str(payload.email))
    if user is None:
        verify_password(payload.password, None)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.email_verified:
        return PendingVerificationResponse(
            message="Требуется подтверждение email.",
            email=user.email,
        )
    return _issue_pair(db, user, request)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    claims = decode_token(payload.refresh_token, "refresh")
    row = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == claims.get("sid"), RefreshSession.jti == claims["jti"])
        .with_for_update()
    )
    if (
        row is None
        or row.user_id != claims["sub"]
        or row.revoked_at is not None
        or _aware(row.expires_at) <= utcnow()
        or not secrets.compare_digest(row.token_hash, hash_token(payload.refresh_token))
    ):
        raise HTTPException(status_code=401, detail="Refresh token is invalid or has been revoked")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")

    new_session_id = str(uuid.uuid4())
    new_token, new_jti, expiry = create_refresh_token(user.id, new_session_id)
    user_agent, ip = _client_metadata(request)
    now = utcnow()
    row.revoked_at = now
    row.last_used_at = now
    row.replaced_by_jti = new_jti
    db.add(
        RefreshSession(
            id=new_session_id,
            user_id=user.id,
            jti=new_jti,
            token_hash=hash_token(new_token),
            expires_at=expiry,
            user_agent=user_agent,
            ip_address=ip,
        )
    )
    access, seconds = create_access_token(user.id, user.email, user.role)
    db.commit()
    return TokenPair(
        access_token=access,
        refresh_token=new_token,
        expires_in=seconds,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    claims = decode_token(payload.refresh_token, "refresh")
    row = db.scalar(
        select(RefreshSession).where(
            RefreshSession.id == claims.get("sid"),
            RefreshSession.jti == claims["jti"],
        )
    )
    if row and secrets.compare_digest(row.token_hash, hash_token(payload.refresh_token)):
        row.revoked_at = row.revoked_at or utcnow()
        db.commit()
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user


@router.post("/verify-email", response_model=TokenPair)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _user_by_email(db, str(payload.email))
    if user is None:
        raise HTTPException(status_code=400, detail="Неверный код подтверждения")
    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email уже подтверждён")
    _consume_email_token(db, payload.code, "VERIFY_EMAIL", user.id)
    user.email_verified = True
    db.commit()
    return _issue_pair(db, user, request)


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: EmailRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = _user_by_email(db, str(payload.email))
    if user and not user.email_verified:
        token = _create_email_token(
            db, user, "VERIFY_EMAIL", settings.email_token_minutes, _six_digit_code()
        )
        background.add_task(mailer.send_verification_email, user.email, user.display_name, token)
    return MessageResponse(message="If the account needs verification, an email has been sent")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: EmailRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = _user_by_email(db, str(payload.email))
    if user:
        token = _create_email_token(
            db, user, "RESET_PASSWORD", settings.reset_token_minutes, _six_digit_code()
        )
        background.add_task(mailer.send_reset_email, user.email, user.display_name, token)
    return MessageResponse(message="If the account exists, a password reset email has been sent")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = _user_by_email(db, str(payload.email))
    if user is None:
        raise HTTPException(status_code=400, detail="Неверный код")
    _consume_email_token(db, payload.code, "RESET_PASSWORD", user.id)
    user.password_hash = hash_password(payload.password)
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    return MessageResponse(message="Password reset")


@router.patch("/profile", response_model=UserResponse)
def patch_profile(
    payload: ProfilePatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(user)
    return user


@router.patch("/avatar", response_model=UserResponse)
def patch_avatar(
    payload: AvatarPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if "avatar_key" in payload.model_fields_set:
        user.avatar_key = payload.avatar_key
    if "avatar_url" in payload.model_fields_set:
        user.avatar_url = str(payload.avatar_url) if payload.avatar_url else None
    db.commit()
    db.refresh(user)
    return user


@router.post("/profile/avatar", response_model=UserResponse)
async def upload_profile_avatar(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    old_key = user.avatar_key
    key, url = await avatar_storage.put_upload(user.id, file)
    user.avatar_key = key
    user.avatar_url = url
    db.commit()
    db.refresh(user)
    if old_key and old_key != key:
        try:
            avatar_storage.delete(old_key)
        except Exception:
            pass
    return user


@router.delete("/profile/avatar", response_model=UserResponse)
def delete_profile_avatar(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    old_key = user.avatar_key
    user.avatar_key = None
    user.avatar_url = None
    db.commit()
    db.refresh(user)
    try:
        avatar_storage.delete(old_key)
    except Exception:
        pass
    return user


@router.get("/google/start")
def google_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    state = create_oauth_state()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": str(settings.google_redirect_uri),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{settings.google_authorize_url}?{query}", status_code=302)
    response.set_cookie(
        "galaxy_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=str(settings.google_redirect_uri).startswith("https://"),
        samesite="lax",
        path="/internal/v1/auth/google/callback",
    )
    return response


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    state_cookie = request.cookies.get("galaxy_oauth_state")
    if not state_cookie or not secrets.compare_digest(state_cookie, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    decode_oauth_state(state)
    if not settings.google_client_id or not settings.google_client_secret.get_secret_value():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            str(settings.google_token_url),
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "redirect_uri": str(settings.google_redirect_uri),
                "grant_type": "authorization_code",
            },
        )
        if token_response.is_error:
            raise HTTPException(status_code=400, detail="Google authorization failed")
        google_access = token_response.json().get("access_token")
        if not google_access:
            raise HTTPException(status_code=400, detail="Google authorization failed")
        info_response = await client.get(
            str(settings.google_userinfo_url),
            headers={"Authorization": f"Bearer {google_access}"},
        )
        if info_response.is_error:
            raise HTTPException(status_code=400, detail="Unable to load Google profile")
        profile = info_response.json()

    subject = str(profile.get("sub", ""))
    email = normalize_email(str(profile.get("email", "")))
    if not subject or not email or not profile.get("email_verified"):
        raise HTTPException(status_code=400, detail="Google account email is not verified")
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_subject == subject,
        )
    )
    if account:
        user = db.get(User, account.user_id)
    else:
        user = _user_by_email(db, email)
        if user is None:
            user = User(
                email=email,
                display_name=str(profile.get("name") or email.split("@", 1)[0])[:120],
                role=UserRole.USER.value,
                email_verified=True,
            )
            db.add(user)
            db.flush()
        else:
            user.email_verified = True
        db.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_subject=subject,
                provider_email=email,
            )
        )
    if user is None:
        raise HTTPException(status_code=400, detail="Unable to resolve Google account")
    picture = str(profile.get("picture") or "")
    if picture and not user.avatar_key:
        imported = await avatar_storage.import_google_avatar(user.id, picture)
        if imported:
            user.avatar_key, user.avatar_url = imported
            db.commit()
    exchange_code = _create_email_token(db, user, "OAUTH_EXCHANGE", settings.exchange_code_minutes)
    response = RedirectResponse(
        f"{settings.frontend_url_value}/auth/callback?{urlencode({'code': exchange_code})}",
        status_code=302,
    )
    response.delete_cookie("galaxy_oauth_state", path="/internal/v1/auth/google/callback")
    return response


@router.post("/exchange-code", response_model=TokenPair)
def exchange_code(
    payload: ExchangeCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _, user = _consume_email_token(db, payload.code, "OAUTH_EXCHANGE")
    db.commit()
    return _issue_pair(db, user, request)


@router.post(
    "/admin/promote",
    response_model=UserResponse,
    dependencies=[Depends(require_internal_token)],
)
def promote(
    payload: PromoteRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = _user_by_email(db, str(payload.email))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role != UserRole.ADMIN.value:
        old_role = target.role
        target.role = UserRole.ADMIN.value
        db.add(
            RoleAudit(
                target_user_id=target.id,
                actor_user_id=actor.id,
                old_role=old_role,
                new_role=UserRole.ADMIN.value,
                reason=payload.reason,
            )
        )
        db.commit()
        db.refresh(target)
    return target


@router.get(
    "/authorize/admin",
    response_model=AuthorizationResponse,
    dependencies=[Depends(require_internal_token)],
)
def authorize_admin(user: User = Depends(require_admin)):
    return AuthorizationResponse(
        active=True,
        subject=user.id,
        email=user.email,
        role=user.role,
        admin=True,
    )
