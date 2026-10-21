import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from .db import transaction
from .models import (
    ApplicationTarget,
    AuditEvent,
    Credential,
    Membership,
    Project,
    RetentionPolicy,
    Run,
    UsageEvent,
    User,
    uid,
)
from .schemas import (
    CredentialInput,
    MembershipInput,
    RetentionInput,
    StrictModel,
    TargetInput,
    UserInput,
)
from .security import (
    admin,
    audit,
    authorize_project,
    cipher,
    principal,
    token_hash,
    validate_target,
)
from .services import columns, require
from . import retention, usage

router = APIRouter(prefix="/api/v1")


def public_user(user):
    return {
        "id": user.id,
        "name": user.name,
        "active": user.active,
        "is_admin": user.is_admin,
    }


@router.get("/me")
def me(request: Request):
    return principal(request)


@router.get("/users")
def users(user=Depends(admin)):
    with transaction() as session:
        return [
            public_user(u)
            for u in session.scalars(select(User).order_by(User.created_at))
            if u.active or u.name != "Local developer"
        ]


@router.post("/users", status_code=201)
def create_user(body: UserInput, user=Depends(admin)):
    token = "es_" + secrets.token_urlsafe(32)
    with transaction() as session:
        created = User(id=uid(), name=body.name, token_hash=token_hash(token))
        session.add(created)
        session.flush()
        audit(session, "user.created", actor_id=user["id"], target_id=created.id)
        return {**public_user(created), "token": token}


class UserState(StrictModel):
    active: bool


@router.patch("/users/{user_id}")
def set_user_state(user_id: str, body: UserState, user=Depends(admin)):
    if user_id == user["id"]:
        raise HTTPException(409, "Cannot disable your own administrator identity")
    with transaction() as session:
        target = require(session, User, user_id)
        target.active = body.active
        audit(
            session,
            "user.enabled" if body.active else "user.disabled",
            actor_id=user["id"],
            target_id=user_id,
        )
        return {**public_user(target), "active": body.active}


@router.post("/users/{user_id}/token")
def rotate_token(user_id: str, request: Request):
    actor = principal(request)
    if not actor["is_admin"] and actor["id"] != user_id:
        raise HTTPException(403, "Cannot rotate another user's token")
    token = "es_" + secrets.token_urlsafe(32)
    with transaction() as session:
        user = require(session, User, user_id)
        user.token_hash = token_hash(token)
        audit(session, "user.token_rotated", actor_id=actor["id"], target_id=user_id)
    return {"token": token}


@router.get("/projects")
def projects(request: Request):
    actor = principal(request)
    with transaction() as session:
        query = select(Project)
        if not actor["is_admin"]:
            query = query.join(Membership).where(Membership.user_id == actor["id"])
        return [columns(p) for p in session.scalars(query)]


@router.post("/projects", status_code=201)
def create_project(body: UserInput, request: Request):
    actor = principal(request)
    with transaction() as session:
        project = Project(id=uid(), name=body.name)
        session.add(project)
        session.flush()
        session.add(
            Membership(project_id=project.id, user_id=actor["id"], role="admin")
        )
        audit(session, "project.created", project.id, actor["id"])
        return columns(project)


@router.get("/members")
def members(project_id=Depends(authorize_project)):
    with transaction() as session:
        return [
            {"user": public_user(user), "role": member.role}
            for member, user in session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(Membership.project_id == project_id)
            )
        ]


@router.put("/members")
def member(
    body: MembershipInput, request: Request, project_id=Depends(authorize_project)
):
    with transaction() as session:
        session.execute(
            select(Project).where(Project.id == project_id).with_for_update()
        ).scalar_one()
        require(session, User, body.user_id)
        existing = session.scalar(
            select(Membership)
            .where(
                Membership.project_id == project_id, Membership.user_id == body.user_id
            )
            .with_for_update()
        )
        if existing and existing.role == "admin" and body.role != "admin":
            others = session.scalars(
                select(Membership).where(
                    Membership.project_id == project_id,
                    Membership.role == "admin",
                    Membership.user_id != body.user_id,
                )
            ).all()
            if not others:
                raise HTTPException(409, "A project must retain an administrator")
        if existing:
            existing.role = body.role
        else:
            session.add(
                Membership(project_id=project_id, user_id=body.user_id, role=body.role)
            )
        audit(
            session,
            "membership.changed",
            project_id,
            principal(request)["id"],
            body.user_id,
            role=body.role,
        )
    return body.model_dump()


@router.delete("/members/{user_id}")
def remove_member(
    user_id: str, request: Request, project_id=Depends(authorize_project)
):
    with transaction() as session:
        session.execute(
            select(Project).where(Project.id == project_id).with_for_update()
        ).scalar_one()
        existing = session.scalar(
            select(Membership)
            .where(Membership.project_id == project_id, Membership.user_id == user_id)
            .with_for_update()
        )
        if not existing:
            raise HTTPException(404, "Membership not found")
        if existing.role == "admin" and not session.scalar(
            select(Membership.id).where(
                Membership.project_id == project_id,
                Membership.role == "admin",
                Membership.user_id != user_id,
            )
        ):
            raise HTTPException(409, "A project must retain an administrator")
        session.delete(existing)
        audit(
            session, "membership.removed", project_id, principal(request)["id"], user_id
        )
    return {"removed": True}


def credential_view(value):
    return {k: v for k, v in columns(value).items() if k != "ciphertext"}


@router.get("/credentials")
def credentials(project_id=Depends(authorize_project)):
    with transaction() as session:
        return [
            credential_view(c)
            for c in session.scalars(
                select(Credential).where(Credential.project_id == project_id)
            )
        ]


@router.post("/credentials", status_code=201)
def store_credential(
    body: CredentialInput, request: Request, project_id=Depends(authorize_project)
):
    encrypted = cipher().encrypt(body.value.encode()).decode()
    with transaction() as session:
        value = Credential(
            id=uid(), project_id=project_id, name=body.name, ciphertext=encrypted
        )
        session.add(value)
        session.flush()
        audit(
            session,
            "credential.created",
            project_id,
            principal(request)["id"],
            value.id,
        )
        return credential_view(value)


@router.put("/credentials/{credential_id}")
def rotate_credential(
    credential_id: str,
    body: CredentialInput,
    request: Request,
    project_id=Depends(authorize_project),
):
    encrypted = cipher().encrypt(body.value.encode()).decode()
    with transaction() as session:
        value = require(session, Credential, credential_id, project_id)
        value.ciphertext, value.name, value.version = (
            encrypted,
            body.name,
            value.version + 1,
        )
        audit(
            session,
            "credential.rotated",
            project_id,
            principal(request)["id"],
            value.id,
            version=value.version,
        )
        return credential_view(value)


@router.delete("/credentials/{credential_id}")
def disable_credential(
    credential_id: str, request: Request, project_id=Depends(authorize_project)
):
    with transaction() as session:
        value = require(session, Credential, credential_id, project_id)
        value.active = False
        audit(
            session,
            "credential.disabled",
            project_id,
            principal(request)["id"],
            value.id,
        )
    return {"disabled": True}


@router.get("/targets")
def targets(project_id=Depends(authorize_project)):
    with transaction() as session:
        return [
            columns(t)
            for t in session.scalars(
                select(ApplicationTarget).where(
                    ApplicationTarget.project_id == project_id
                )
            )
        ]


@router.post("/targets", status_code=201)
def target(body: TargetInput, request: Request, project_id=Depends(authorize_project)):
    validate_target(body.url)
    with transaction() as session:
        if body.credential_id:
            require(session, Credential, body.credential_id, project_id)
        value = ApplicationTarget(id=uid(), project_id=project_id, **body.model_dump())
        session.add(value)
        session.flush()
        audit(session, "target.created", project_id, principal(request)["id"], value.id)
        return columns(value)


@router.get("/runs/{run_id}/usage")
def run_usage(run_id: str, project_id=Depends(authorize_project)):
    with transaction() as session:
        require(session, Run, run_id, project_id)
        return {
            "summary": usage.summary(session, [run_id]),
            "events": [
                columns(e)
                for e in session.scalars(
                    select(UsageEvent)
                    .where(UsageEvent.run_id == run_id)
                    .order_by(UsageEvent.created_at)
                )
            ],
        }


@router.get("/retention")
def policy(project_id=Depends(authorize_project)):
    with transaction() as session:
        value = session.scalar(
            select(RetentionPolicy).where(RetentionPolicy.project_id == project_id)
        )
        return columns(value) if value else RetentionInput().model_dump()


@router.put("/retention")
def set_policy(
    body: RetentionInput, request: Request, project_id=Depends(authorize_project)
):
    with transaction() as session:
        value = session.scalar(
            select(RetentionPolicy)
            .where(RetentionPolicy.project_id == project_id)
            .with_for_update()
        )
        if not value:
            value = RetentionPolicy(project_id=project_id)
            session.add(value)
        for key, item in body.model_dump().items():
            setattr(value, key, item)
        audit(
            session,
            "retention.configured",
            project_id,
            principal(request)["id"],
            **body.model_dump(),
        )
    return body.model_dump()


class SweepInput(StrictModel):
    dry_run: bool = True


@router.post("/retention/sweep")
def sweep(body: SweepInput, request: Request, project_id=Depends(authorize_project)):
    return retention.sweep(project_id, body.dry_run, principal(request)["id"])


@router.get("/audit")
def audit_events(
    limit: int = Query(100, ge=1, le=500), project_id=Depends(authorize_project)
):
    with transaction() as session:
        return [
            columns(e)
            for e in session.scalars(
                select(AuditEvent)
                .where(AuditEvent.project_id == project_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
            )
        ]
