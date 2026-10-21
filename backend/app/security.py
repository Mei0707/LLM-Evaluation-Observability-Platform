"""Personal API-token identities, project roles and encrypted server-side secrets."""

import hashlib
import secrets
from urllib.parse import urlsplit
from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from .config import settings
from .db import transaction
from .models import AuditEvent, Credential, Membership, Project, User, uid
from .seed import DEFAULT_PROJECT

LOCAL_USER = "00000000-0000-4000-8000-000000000002"
ADMIN_USER = "00000000-0000-4000-8000-000000000003"


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def initialize(config=settings):
    if config.auth_mode not in {"local", "users"}:
        raise ValueError("EVALSCOPE_AUTH_MODE must be local or users")
    with transaction() as session:
        if config.auth_mode == "users":
            if not session.get(User, ADMIN_USER):
                if len(config.bootstrap_token) < 32:
                    raise ValueError(
                        "First secure startup requires EVALSCOPE_BOOTSTRAP_TOKEN with at least 32 characters"
                    )
                session.add(
                    User(
                        id=ADMIN_USER,
                        name="Workspace administrator",
                        token_hash=token_hash(config.bootstrap_token),
                        is_admin=True,
                    )
                )
                session.flush()
                session.add(
                    Membership(
                        project_id=DEFAULT_PROJECT, user_id=ADMIN_USER, role="admin"
                    )
                )
        elif not session.get(User, LOCAL_USER):
            # This identity cannot authenticate in users mode.
            session.add(
                User(
                    id=LOCAL_USER,
                    name="Local developer",
                    token_hash=token_hash(secrets.token_urlsafe(64)),
                    active=False,
                )
            )


def identify(request, config=settings):
    if config.auth_mode == "local":
        return {
            "id": LOCAL_USER,
            "name": "Local developer",
            "is_admin": True,
            "local": True,
        }
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    with transaction() as session:
        user = session.scalar(
            select(User).where(
                User.token_hash == token_hash(token), User.active.is_(True)
            )
        )
        if not token or not user:
            raise HTTPException(401, "An active personal access token is required")
        return {
            "id": user.id,
            "name": user.name,
            "is_admin": user.is_admin,
            "local": False,
        }


def principal(request):
    return request.state.principal


def admin(request: Request):
    user = principal(request)
    if not user["is_admin"]:
        raise HTTPException(403, "System administrator access required")
    return user


def authorize_project(
    request: Request, x_project_id: str = Header(default=DEFAULT_PROJECT)
):
    user = principal(request)
    with transaction() as session:
        if not session.get(Project, x_project_id):
            raise HTTPException(404, "Project not found")
        member = session.scalar(
            select(Membership).where(
                Membership.project_id == x_project_id, Membership.user_id == user["id"]
            )
        )
        role = "admin" if user["is_admin"] else member.role if member else None
    if not role:
        raise HTTPException(403, "Project membership required")
    request.state.role = role
    path, method = request.url.path, request.method
    review_path = "/review-campaigns" in path
    if role == "reviewer" and not review_path and not path.endswith("/workspace"):
        raise HTTPException(403, "Blind reviewers can access review campaigns only")
    protected = any(
        part in path
        for part in ("/members", "/credentials", "/targets", "/retention", "/audit")
    )
    if protected and method != "GET" and role != "admin":
        raise HTTPException(403, "Project administrator access required")
    if method not in {"GET", "HEAD", "OPTIONS"}:
        label = review_path and path.endswith("/labels")
        reading_operation = path.endswith("/comparisons")
        if role == "reader" and not reading_operation:
            raise HTTPException(403, "Read-only project membership")
        if role == "reviewer" and not label:
            raise HTTPException(403, "Reviewer role can submit labels only")
    return x_project_id


def cipher():
    from cryptography.fernet import Fernet

    if not settings.master_key:
        raise HTTPException(
            503,
            "Configure EVALSCOPE_MASTER_KEY or its _FILE secret before storing credentials",
        )
    try:
        return Fernet(settings.master_key.encode())
    except ValueError:
        raise HTTPException(503, "Credential encryption key is invalid")


def decrypt_credential(identity, project_id):
    from cryptography.fernet import InvalidToken

    with transaction() as session:
        credential = session.get(Credential, identity)
        if (
            not credential
            or not credential.active
            or credential.project_id != project_id
        ):
            raise ValueError("credential_unavailable")
        try:
            return cipher().decrypt(credential.ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("credential_key_mismatch") from None


def validate_target(url, config=None):
    config = config or settings
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
    ):
        raise HTTPException(
            422, "Target must be an HTTP(S) URL without credentials, query, or fragment"
        )
    allowed = {host.strip().lower() for host in config.target_allowed_hosts}
    if parsed.hostname.lower() not in allowed:
        raise HTTPException(
            422, "Target host must be explicitly registered in EVALSCOPE_TARGET_HOSTS"
        )
    if config.require_https and parsed.scheme != "https":
        raise HTTPException(422, "HTTPS targets are required in this deployment")
    return url


def audit(session, action, project_id=None, actor_id=None, target_id=None, **details):
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            details=details,
        )
    )
