"""Unit tests covering 2026-08-15 nightly coverage gap scan (round 2).

Target: ``app/service/tasks/visual_description.py`` (31.8% baseline,
116 missed lines in coverage scan).

The existing ``test_tasks_visual_description.py`` only exercises
``encode_image`` and ``create_client`` -- every line in ``process``,
``process_single_photo``, and the error-path branches for ``process``
is uncovered. This file fills that gap with mocked LLM and DB so the
strategy's logic (single-photo vs. generator, JSON code-block stripping,
screenshot skip, file-not-found) is observable.

Note on CI budget enforcement (test_process_generator_respects_remaining_budget):
the strategy reads ``ci_remaining_budget`` and is *supposed* to stop
queueing once ``generated_count >= remaining``, but ``generated_count``
is incremented **after** the inner loop completes -- never inside it --
so the early-break check always sees 0 and the loop runs to the end of
the batch. The test below pins the current (buggy) behaviour so a future
fix is visible. See ``tests/artifacts/nightly/2026-08-15-run2/`` for the
repro and the cross-check against ``ocr.py`` which has the same pattern.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload, owner_id="user-1", task_id="task-vd"):
    return SimpleNamespace(
        id=task_id,
        type="VISUAL_DESCRIPTION",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_photo(pid, *, file_type="image", marker=False, owner_id="user-1", file_path="E:/photos/x.jpg", image_type="normal", photo_time=None):
    return SimpleNamespace(
        id=pid,
        file_type=file_type,
        image_type=image_type,
        processed_tasks={"visual_description": True} if marker else {},
        owner_id=owner_id,
        file_path=file_path,
        photo_time=photo_time,
    )


def _settings_with_connection(connection_id="conn-1", model_name="m"):
    connection = MagicMock()
    connection.id = connection_id
    connection.enable = True
    connection.api_key = "secret"
    connection.api_base = "https://example.com"

    settings = MagicMock()
    settings.analysis_connection_id = connection_id
    settings.analysis_model_name = model_name
    settings.connections = [connection]
    settings.visual_evaluation_prompt = "eval prompt"
    settings.visual_narrative_prompt = "narrative prompt"
    return settings


def _mock_chat_client(content):
    """A LangChain-compatible client whose ``ainvoke`` returns ``content``."""
    eval_response = MagicMock()
    eval_response.content = content
    client = MagicMock()
    client.ainvoke = AsyncMock(return_value=eval_response)
    return client


def _description_row(description="x", memory_score=1, quality_score=1, tags=None, reason="r", narrative="n"):
    """A SimpleNamespace standing in for an ``ImageDescription`` ORM row.

    The strategy returns ``desc.description`` / ``desc.quality_score`` /
    ``desc.narrative`` after persisting, so the mock must expose those attrs.
    """
    return SimpleNamespace(
        description=description,
        memory_score=memory_score,
        quality_score=quality_score,
        tags=list(tags or []),
        reason=reason,
        narrative=narrative,
    )


# --- process() error-path branches (config validation) --------------------


@pytest.mark.asyncio
async def test_process_raises_when_analysis_connection_id_missing():
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai.analysis_connection_id = None
    user_cfg.ai.analysis_model_name = "m"

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with pytest.raises(ValueError, match="Visual Model not configured"):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=MagicMock()
            )


@pytest.mark.asyncio
async def test_process_raises_when_model_name_missing():
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai.analysis_connection_id = "conn-1"
    user_cfg.ai.analysis_model_name = ""

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with pytest.raises(ValueError, match="Visual Model not configured"):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=MagicMock()
            )


@pytest.mark.asyncio
async def test_process_raises_when_connection_id_not_found():
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai.analysis_connection_id = "missing"
    user_cfg.ai.analysis_model_name = "m"
    user_cfg.ai.connections = []

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with pytest.raises(ValueError, match="connection not found"):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=MagicMock()
            )


@pytest.mark.asyncio
async def test_process_raises_when_connection_disabled():
    from app.service.tasks import visual_description as vd_mod

    conn = MagicMock()
    conn.id = "conn-1"
    conn.enable = False
    conn.api_key = "k"

    user_cfg = MagicMock()
    user_cfg.ai.analysis_connection_id = "conn-1"
    user_cfg.ai.analysis_model_name = "m"
    user_cfg.ai.connections = [conn]

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with pytest.raises(ValueError, match="disabled"):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=MagicMock()
            )


@pytest.mark.asyncio
async def test_process_raises_when_api_key_missing():
    from app.service.tasks import visual_description as vd_mod

    conn = MagicMock()
    conn.id = "conn-1"
    conn.enable = True
    conn.api_key = ""

    user_cfg = MagicMock()
    user_cfg.ai.analysis_connection_id = "conn-1"
    user_cfg.ai.analysis_model_name = "m"
    user_cfg.ai.connections = [conn]

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with pytest.raises(ValueError, match="api_key"):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=MagicMock()
            )


# --- process() single-photo branches ---------------------------------------


@pytest.mark.asyncio
async def test_process_single_photo_skips_when_photo_not_found():
    """An unknown ``photo_id`` returns ``skipped`` without touching the LLM."""
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        result = await vd_mod.VisualDescriptionStrategy().process(
            worker=None, task=_build_task({"photo_id": "missing"}), db=db
        )

    assert result == {"status": "skipped", "reason": "photo not found"}


@pytest.mark.asyncio
async def test_process_single_photo_skips_when_already_processed():
    """Marker present on the photo means we skip without re-running the LLM."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1", marker=True)
    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        result = await vd_mod.VisualDescriptionStrategy().process(
            worker=None, task=_build_task({"photo_id": "p-1"}), db=db
        )

    assert result == {"status": "skipped", "reason": "already processed"}


@pytest.mark.asyncio
async def test_process_single_photo_force_reruns_even_when_marker_set():
    """``force`` flag bypasses the marker short-circuit."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1", marker=True)
    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    strategy = vd_mod.VisualDescriptionStrategy()
    sentinel = {"status": "completed"}
    with patch.object(strategy, "process_single_photo", new=AsyncMock(return_value=sentinel)) as single:
        with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
            with patch("app.service.tasks.visual_description.ci_task_limit_reached", return_value=False):
                result = await strategy.process(
                    worker=None, task=_build_task({"photo_id": "p-1", "force": True}), db=db
                )

    assert result == sentinel
    single.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_single_photo_skips_when_ci_budget_consumed():
    """CI mode short-circuits to ``skipped`` once the budget is hit."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1")
    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_task_limit_reached", return_value=True):
            result = await vd_mod.VisualDescriptionStrategy().process(
                worker=None, task=_build_task({"photo_id": "p-1"}), db=db
            )

    assert result["status"] == "skipped"
    assert "CI" in result["reason"]


# --- process_single_photo() branches ---------------------------------------


@pytest.mark.asyncio
async def test_process_single_photo_skips_screenshot():
    """Screenshots never reach the LLM."""
    from app.service.tasks import visual_description as vd_mod

    class _ImageType:
        SCREENSHOT = "screenshot"

    vd_mod.ImageType = _ImageType()
    photo = _make_photo("p-1", image_type="screenshot")
    db = MagicMock()

    result = await vd_mod.VisualDescriptionStrategy().process_single_photo(
        worker=None, photo=photo, db=db, settings=MagicMock()
    )

    assert result == {"status": "skipped", "reason": "screenshot not supported"}


@pytest.mark.asyncio
async def test_process_single_photo_returns_failed_when_file_missing():
    """If ``storage.get_available_photo_path`` returns ``None`` we surface ``failed``."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()
    client = _mock_chat_client("unused")

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value=None):
                result = await vd_mod.VisualDescriptionStrategy().process_single_photo(
                    worker=None, photo=photo, db=db, settings=MagicMock()
                )

    assert result == {"status": "failed", "error": "file not found"}


@pytest.mark.asyncio
async def test_process_single_photo_persists_description_from_clean_json():
    """Happy path: LLM returns clean JSON -> row is upserted, payload echoed."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1", photo_time="2026-01-02T10:00:00")

    ai_settings = _settings_with_connection()
    user_cfg = MagicMock()
    user_cfg.ai = ai_settings

    client = _mock_chat_client(
        "{\"description\": \"nice shot\", \"memory_score\": 88, \"beauty_score\": 77, \"tags\": [\"\u65c5\u884c\"], \"reason\": \"ok\", \"narrative\": \"\u6587\u6848\"}"
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    row = _description_row(description="nice shot", memory_score=88, quality_score=77, tags=["\u65c5\u884c"], reason="ok", narrative="\u6587\u6848")

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value="/tmp/p-1.jpg"):
                with patch("app.service.tasks.visual_description.get_user_roots", return_value=[]):
                    with patch("app.service.tasks.visual_description.compute_browse_path", return_value=("", "x.jpg")):
                        with patch("app.service.tasks.visual_description.encode_image", return_value="BASE64DATA"):
                            with patch.object(vd_mod, "ImageDescription", return_value=row):
                                result = await vd_mod.VisualDescriptionStrategy().process_single_photo(
                                    worker=None, photo=photo, db=db, settings=ai_settings
                                )

    assert result["status"] == "completed"
    assert result["description"] == "nice shot"
    assert result["quality"] == 77
    assert result["narrative"] == "文案"

    # One insert, one commit; photo.processed_tasks is updated to mark done.
    db.add.assert_called_once_with(row)
    db.commit.assert_called_once()
    assert photo.processed_tasks == {"visual_description": True}


@pytest.mark.asyncio
async def test_process_single_photo_strips_json_code_fence_before_parsing():
    """LLM responses wrapped in ```json ...``` fences are stripped before parsing."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1")

    ai_settings = _settings_with_connection()
    user_cfg = MagicMock()
    user_cfg.ai = ai_settings

    client = _mock_chat_client(
        "```json\n{\"description\": \"stripped\", \"memory_score\": 50, \"beauty_score\": 60, \"tags\": [], \"reason\": \"r\", \"narrative\": \"n\"}\n```"
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    row = _description_row(description="stripped", memory_score=50, quality_score=60)

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value="/tmp/p-1.jpg"):
                with patch("app.service.tasks.visual_description.get_user_roots", return_value=[]):
                    with patch("app.service.tasks.visual_description.compute_browse_path", return_value=("", "")):
                        with patch("app.service.tasks.visual_description.encode_image", return_value="BASE64"):
                            with patch.object(vd_mod, "ImageDescription", return_value=row):
                                result = await vd_mod.VisualDescriptionStrategy().process_single_photo(
                                    worker=None, photo=photo, db=db, settings=ai_settings
                                )

    assert result["description"] == "stripped"
    assert result["quality"] == 60


@pytest.mark.asyncio
async def test_process_single_photo_propagates_json_decode_error():
    """Malformed JSON from the LLM is re-raised so the worker records a failure."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1")
    ai_settings = _settings_with_connection()
    user_cfg = MagicMock()
    user_cfg.ai = ai_settings

    client = _mock_chat_client("not-json")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value="/tmp/p-1.jpg"):
                with patch("app.service.tasks.visual_description.get_user_roots", return_value=[]):
                    with patch("app.service.tasks.visual_description.compute_browse_path", return_value=("", "")):
                        with patch("app.service.tasks.visual_description.encode_image", return_value="BASE64"):
                            with pytest.raises(Exception):
                                await vd_mod.VisualDescriptionStrategy().process_single_photo(
                                    worker=None, photo=photo, db=db, settings=ai_settings
                                )


@pytest.mark.asyncio
async def test_process_single_photo_overwrites_existing_description():
    """An existing ``ImageDescription`` row is replaced, not appended."""
    from app.service.tasks import visual_description as vd_mod

    photo = _make_photo("p-1")
    ai_settings = _settings_with_connection()
    user_cfg = MagicMock()
    user_cfg.ai = ai_settings

    client = _mock_chat_client(
        "{\"description\": \"new\", \"memory_score\": 80, \"beauty_score\": 70, \"tags\": [], \"reason\": \"r\", \"narrative\": \"n\"}"
    )

    existing = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    row = _description_row(description="new", memory_score=80, quality_score=70)

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value="/tmp/p-1.jpg"):
                with patch("app.service.tasks.visual_description.get_user_roots", return_value=[]):
                    with patch("app.service.tasks.visual_description.compute_browse_path", return_value=("", "")):
                        with patch("app.service.tasks.visual_description.encode_image", return_value="BASE64"):
                            with patch.object(vd_mod, "ImageDescription", return_value=row):
                                await vd_mod.VisualDescriptionStrategy().process_single_photo(
                                    worker=None, photo=photo, db=db, settings=ai_settings
                                )

    db.delete.assert_called_once_with(existing)
    db.flush.assert_called_once()
    db.add.assert_called_once_with(row)


# --- process() generator mode ----------------------------------------------
#
# In the real strategy the SQLAlchemy filter ``Photo.file_type != FileType.video
# AND Photo.image_type != ImageType.SCREENSHOT`` excludes videos and screenshots
# at the DB layer. The Python strategy only filters by ``processed_tasks``. So
# these mocks mirror that contract: the DB returns only photos that already
# passed the SQL filter.


@pytest.mark.asyncio
async def test_process_generator_returns_zero_when_no_photos():
    """Generator mode with no photos emits the ``generated_tasks=0`` envelope."""
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = []
    db.query.return_value = query

    worker = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=None):
            result = await vd_mod.VisualDescriptionStrategy().process(
                worker=worker, task=_build_task({}), db=db
            )

    assert result["generated_tasks"] == 0
    assert "Generated 0 Visual Description tasks" in result["message"]
    worker.add_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_process_generator_queues_only_unmarked_photos():
    """Generator mode skips photos that already have the ``visual_description`` marker."""
    from app.service.tasks import visual_description as vd_mod

    pending = _make_photo("p-a", marker=False)
    already = _make_photo("p-b", marker=True)

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.side_effect = [[pending, already], []]
    db.query.return_value = query

    worker = MagicMock()
    worker.add_tasks = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=None):
            result = await vd_mod.VisualDescriptionStrategy().process(
                worker=worker, task=_build_task({}), db=db
            )

    assert result["generated_tasks"] == 1
    worker.add_tasks.assert_called_once()
    queued = worker.add_tasks.call_args[0][1]
    assert len(queued) == 1
    assert queued[0]["payload"]["photo_id"] == "p-a"


@pytest.mark.asyncio
async def test_process_generator_force_queues_already_marked_photo():
    """``force=True`` overrides the marker so already-processed photos get re-queued."""
    from app.service.tasks import visual_description as vd_mod

    already = _make_photo("p-b", marker=True)

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.side_effect = [[already], []]
    db.query.return_value = query

    worker = MagicMock()
    worker.add_tasks = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=None):
            result = await vd_mod.VisualDescriptionStrategy().process(
                worker=worker, task=_build_task({"force": True}), db=db
            )

    assert result["generated_tasks"] == 1
    queued = worker.add_tasks.call_args[0][1]
    assert queued[0]["payload"]["force"] is True


@pytest.mark.asyncio
async def test_process_generator_scopes_query_to_owner():
    """When ``owner_id`` is set on the task the generator scopes the query by it."""
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = []
    db.query.return_value = chain

    worker = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=None):
            await vd_mod.VisualDescriptionStrategy().process(
                worker=worker, task=_build_task({}, owner_id="user-7"), db=db
            )

    # filter() must have been called at least twice: once to exclude video,
    # once to scope by owner_id.
    assert chain.filter.call_count >= 2


@pytest.mark.asyncio
async def test_process_generator_propagates_worker_exception():
    """An exception raised inside the loop is surfaced to the worker."""
    from app.service.tasks import visual_description as vd_mod

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.all.side_effect = RuntimeError("db gone")
    db.query.return_value = chain

    worker = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=None):
            with pytest.raises(RuntimeError, match="db gone"):
                await vd_mod.VisualDescriptionStrategy().process(
                    worker=worker, task=_build_task({}), db=db
                )


# --- CI budget behavior (documents a known off-by-one) ----------------------


@pytest.mark.asyncio
async def test_process_generator_respects_remaining_budget():
    """The CI budget is supposed to cap ``generated_tasks`` at ``remaining``.

    TODO(2026-08-15): the inner ``for p in batch`` loop never increments
    ``generated_count`` (it is incremented once *after* the loop), so the
    ``if remaining is not None and generated_count >= remaining: break``
    guard always sees 0 and queues the entire batch. ``ocr.py`` has the
    same pattern. The assertion below pins the current (buggy) behaviour
    so that a future fix becomes visible -- if you change the strategy
    to honour the budget inside the loop, update this test to expect 2.
    """
    from app.service.tasks import visual_description as vd_mod

    pending = [_make_photo(f"p-{i}", marker=False) for i in range(5)]

    user_cfg = MagicMock()
    user_cfg.ai = _settings_with_connection()

    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.side_effect = [pending, []]
    db.query.return_value = query

    worker = MagicMock()
    worker.add_tasks = MagicMock()

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ci_remaining_budget", return_value=2):
            result = await vd_mod.VisualDescriptionStrategy().process(
                worker=worker, task=_build_task({}), db=db
            )

    # The whole batch is queued in one go; ``generated_count`` only updates
    # *after* the loop, so the early-break never fires.
    assert result["generated_tasks"] == 5


# --- additional coverage: metadata injection --------------------------------


@pytest.mark.asyncio
async def test_process_single_photo_includes_metadata_address_when_present():
    """When the photo has a ``PhotoMetadata`` row its address is injected into the prompt."""
    from app.service.tasks import visual_description as vd_mod
    from app.db.models import photo_metadata as pm_module

    photo = _make_photo("p-1", photo_time="2026-01-02T10:00:00")
    ai_settings = _settings_with_connection()
    user_cfg = MagicMock()
    user_cfg.ai = ai_settings

    client = _mock_chat_client(
        "{\"description\": \"x\", \"memory_score\": 1, \"beauty_score\": 1, \"tags\": [], \"reason\": \"r\", \"narrative\": \"n\"}"
    )

    class _FakeMeta:
        address = "Shanghai"

    db = MagicMock()
    db.query.side_effect = lambda model: (
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=_FakeMeta()))))
        if model is pm_module.PhotoMetadata
        else MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    )

    row = _description_row(description="x", memory_score=1, quality_score=1)

    with patch("app.service.tasks.visual_description.config_manager.get_user_config", return_value=user_cfg):
        with patch("app.service.tasks.visual_description.ChatOpenAI", return_value=client):
            with patch("app.service.tasks.visual_description.storage.get_available_photo_path", return_value="/tmp/p-1.jpg"):
                with patch("app.service.tasks.visual_description.get_user_roots", return_value=[]):
                    with patch("app.service.tasks.visual_description.compute_browse_path", return_value=("", "")):
                        with patch("app.service.tasks.visual_description.encode_image", return_value="BASE64"):
                            with patch.object(vd_mod, "ImageDescription", return_value=row):
                                await vd_mod.VisualDescriptionStrategy().process_single_photo(
                                    worker=None, photo=photo, db=db, settings=ai_settings
                                )

    invoke_args = client.ainvoke.call_args[0][0]
    user_message = invoke_args[1]
    text_payload = next(p["text"] for p in user_message["content"] if p.get("type") == "text")
    assert "Shanghai" in text_payload
