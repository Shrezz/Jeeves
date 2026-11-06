"""Thin HTTP endpoints. Authentication is injectable by the separate login workstream."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.workflow_api import ResumeRun, RunView, StartRun
from app.services.workflow import Conflict, WorkflowService

router = APIRouter()


async def current_user(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ],
) -> str:
    resolver = getattr(request.app.state, "principal_resolver", None)
    if resolver is None:
        raise HTTPException(503, "Connect the authenticated-session resolver")
    return await resolver(request)


def workflow(request: Request) -> WorkflowService:
    service = getattr(request.app.state, "workflow", None)
    if service is None:
        raise HTTPException(503, "Connect workflow adapters or enable explicit demo mode")
    return service


User = Annotated[str, Depends(current_user)]
Service = Annotated[WorkflowService, Depends(workflow)]


@router.post("/agent/runs", response_model=RunView)
async def start_run(body: StartRun, user: User, service: Service):
    try:
        return await service.start(user, body)
    except PermissionError:
        raise HTTPException(404, "Selected policy or claim not found") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/agent/runs/{run_id}", response_model=RunView)
async def get_run(run_id: str, user: User, service: Service):
    try:
        return service.view(user, run_id)
    except PermissionError:
        raise HTTPException(404, "Run not found") from None


@router.post("/agent/runs/{run_id}/responses", response_model=RunView)
async def resume_run(run_id: str, body: ResumeRun, user: User, service: Service):
    try:
        return await service.resume(user, run_id, body)
    except PermissionError:
        raise HTTPException(404, "Run not found") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/artifacts/{artifact_id}")
async def download_artifact(artifact_id: str, user: User, service: Service):
    if service.artifacts is None:
        raise HTTPException(503, "Connect the artifact storage adapter")
    try:
        artifact = await service.artifacts.read_artifact(user, artifact_id)
    except PermissionError:
        raise HTTPException(404, "Artifact not found") from None
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": 'attachment; filename="claim-packet.html"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
