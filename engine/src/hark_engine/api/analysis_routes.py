"""Routes for analysis, profile and LLM settings."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import ValidationError

from ..analysis import AnalysisService
from ..auth import save_secret
from ..llm import LLM_PROFILES, OllamaProvider, recommend_llm
from ..llm.factory import CLOUD_KEY_NAME
from ..models import (
    Analysis,
    AnalysisStatusInfo,
    CloudKeyUpdate,
    CloudSettingsPatch,
    CloudSettingsView,
    LLMModelProfile,
    LLMPullRequest,
    LLMSettings,
    LLMSettingsPatch,
    ProfileDocument,
    ProfileUpdate,
)
from ..profile import ProfileError, ProfileStore
from ..store import AnalysisRepository, MeetingRepository, SettingsRepository
from ..stt import has_cuda, total_ram_gb
from .deps import ReadScope, UiScope


def add_analysis_routes(
    app: FastAPI,
    *,
    meetings: MeetingRepository,
    analyses: AnalysisRepository,
    service: AnalysisService,
    settings: SettingsRepository,
    profile: ProfileStore,
    data_dir: Path,
) -> None:
    @app.get("/v1/meetings/{meeting_id}/analysis", response_model=Analysis)
    def get_analysis(meeting_id: str, _: ReadScope) -> Analysis:
        meetings.get(meeting_id)
        stored = analyses.get(meeting_id)
        if stored is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no analysis for this meeting")
        return stored.analysis

    @app.post("/v1/meetings/{meeting_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
    def analyze_meeting(meeting_id: str, _: UiScope, force: bool = False) -> dict[str, str]:
        """Explicit user action. Same input + model ⇒ cached result, no LLM call (unless force)."""
        meetings.get(meeting_id)
        if not meetings.segments(meeting_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "the meeting has no transcript yet")
        service.submit(meeting_id, force=force)
        return {"status": "queued"}

    @app.get("/v1/analysis/status", response_model=AnalysisStatusInfo)
    def analysis_status(_: ReadScope) -> AnalysisStatusInfo:
        return service.status()

    # ---- LLM settings -----------------------------------------------------------------
    @app.get("/v1/settings/llm", response_model=LLMSettings)
    def get_llm(_: ReadScope) -> LLMSettings:
        return settings.get_llm()

    @app.patch("/v1/settings/llm", response_model=LLMSettings)
    def patch_llm(body: LLMSettingsPatch, _: UiScope) -> LLMSettings:
        try:
            new = settings.patch_llm(body)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()[0]["msg"]) from exc
        service.retry_pending()
        return new

    @app.get("/v1/llm/models", response_model=list[LLMModelProfile])
    def llm_models(_: ReadScope) -> list[LLMModelProfile]:
        cfg = settings.get_llm()
        try:
            installed = OllamaProvider(cfg.ollama_url, cfg.model).installed_models()
        except Exception:
            installed = []
        best = recommend_llm(total_ram_gb(), has_cuda())
        return [
            LLMModelProfile(
                id=p.id,
                label=p.label,
                description=p.description,
                ollama_model=p.ollama_model,
                download_gb=p.download_gb,
                min_ram_gb=p.min_ram_gb,
                installed=any(
                    m == p.ollama_model or m.startswith(f"{p.ollama_model}:") for m in installed
                ),
                recommended=p.id == best,
            )
            for p in LLM_PROFILES.values()
        ]

    @app.post("/v1/llm/pull", status_code=status.HTTP_202_ACCEPTED)
    def llm_pull(body: LLMPullRequest, _: UiScope) -> dict[str, str]:
        """Asks the local Ollama server to download a model (explicit user action)."""
        service.start_pull(body.model)
        return {"status": "downloading"}

    # ---- optional cloud provider (disabled by default) -----------------------------------
    def cloud_view() -> CloudSettingsView:
        from ..auth import load_secret

        cloud = settings.get_cloud()
        return CloudSettingsView(
            **cloud.model_dump(), has_key=bool(load_secret(data_dir, CLOUD_KEY_NAME))
        )

    @app.get("/v1/settings/cloud", response_model=CloudSettingsView)
    def get_cloud(_: ReadScope) -> CloudSettingsView:
        return cloud_view()

    @app.patch("/v1/settings/cloud", response_model=CloudSettingsView)
    def patch_cloud(body: CloudSettingsPatch, _: UiScope) -> CloudSettingsView:
        try:
            settings.patch_cloud(body)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)[:200]) from exc
        return cloud_view()

    @app.put("/v1/settings/cloud/key", status_code=status.HTTP_204_NO_CONTENT)
    def put_cloud_key(body: CloudKeyUpdate, _: UiScope) -> Response:
        """Stored in the OS credential manager; never returned by the API."""
        data_dir.mkdir(parents=True, exist_ok=True)
        save_secret(data_dir, CLOUD_KEY_NAME, body.key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ---- profile.yaml ------------------------------------------------------------------------
    @app.get("/v1/profile", response_model=ProfileDocument)
    def get_profile(_: ReadScope) -> ProfileDocument:
        return profile.document()

    @app.put("/v1/profile", response_model=ProfileDocument)
    def put_profile(body: ProfileUpdate, _: UiScope) -> ProfileDocument:
        try:
            profile.save(body.yaml)
        except ProfileError as exc:
            raise HTTPException(422, str(exc)) from exc
        return profile.document()
