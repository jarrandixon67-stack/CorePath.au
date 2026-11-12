from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_life_profile_bot import ModelDouble, proposal
from test_life_profile_repository import profiles as profiles_fixture
from test_life_profile_security import gateway as gateway_fixture

from life_profile.bot import LifeProfileBot
from life_profile.journal import (
    EntryCreate,
    EntryUpdate,
    JournalService,
    JournalSettings,
    JournalStore,
)
from life_profile.models import AnalyseRequest, Consent, Decision, SourceMessage
from life_profile.repository import ConsentRequired, ProfileConflict, ProfileMissing

profiles = profiles_fixture
gateway = gateway_fixture


def entry(**changes):
    return EntryCreate(
        title="A useful reflection",
        content="I prefer short answers.",
        entry_date=date(2026, 11, 12),
        client_reference=uuid4(),
        disclosure_version=1,
        **changes,
    )


class JournalModel:
    def __init__(self, during=None):
        self.calls = 0
        self.during = during

    def propose(self, context):
        self.calls += 1
        if self.during:
            self.during()
        result = proposal()
        message = context["messages"][0]
        result.observations[0].evidence[0].message_id = message["message_id"]
        result.observations[0].evidence[0].quote = "I prefer short answers."
        return result


def test_journal_disclosure_and_strict_identity_fields_are_required():
    with pytest.raises(ValidationError):
        EntryCreate.model_validate(
            {"content": "Reflection", "entry_date": "2026-11-12", "client_reference": str(uuid4())}
        )
    with pytest.raises(ValidationError):
        EntryCreate.model_validate({**entry().model_dump(), "subject": "another-person"})


def test_default_inclusion_does_not_grant_model_processing_consent(profiles):
    repo, _, owner, _, _ = profiles
    repo.set_consent(owner, Consent(purpose="Understand my life"), "disable-model")
    store = JournalStore(repo)
    model = JournalModel()
    saved, _ = store.create(owner, entry(), "save")
    result = JournalService(store, LifeProfileBot(repo, model)).analyse(
        owner, UUID(saved["id"]), "analyse"
    )
    assert result["entry"]["include_in_profile"] is True
    assert result["entry"]["analysis_state"] == "awaiting_consent"
    assert model.calls == 0


def test_content_is_encrypted_and_owner_access_is_enforced(profiles):
    repo, pool, owner, other, _ = profiles
    store = JournalStore(repo)
    data = entry()
    saved, created = store.create(owner, data, "save")
    assert created
    with pool.connection() as conn:
        encrypted = bytes(
            conn.execute(
                "SELECT payload_ciphertext FROM life_profile_journal_entries WHERE id=%s",
                (UUID(saved["id"]),),
            ).fetchone()[0]
        )
        assert b"short answers" not in encrypted
        assert b"useful reflection" not in encrypted
    with pytest.raises(ProfileMissing):
        store.get(other, UUID(saved["id"]), "read")
    assert store.list(other, "list")["entries"] == []
    again, created = store.create(owner, data, "retry")
    assert not created and again["id"] == saved["id"]
    assert "content" not in store.list(owner, "list")["entries"][0]


def test_global_default_is_for_future_entries_and_explicit_exclusion_wins(profiles):
    repo, _, owner, _, _ = profiles
    store = JournalStore(repo)
    included, _ = store.create(owner, entry(), "first")
    store.set_settings(
        owner,
        JournalSettings(default_include_in_profile=False, disclosure_version=1, expected_version=0),
        "prefs",
    )
    future, _ = store.create(owner, entry(), "second")
    assert included["include_in_profile"] is True
    assert future["include_in_profile"] is False
    with pytest.raises(ProfileConflict):
        store.set_settings(
            owner,
            JournalSettings(
                default_include_in_profile=True, disclosure_version=1, expected_version=0
            ),
            "stale",
        )
    model = JournalModel()
    JournalService(store, LifeProfileBot(repo, model)).analyse(
        owner, UUID(future["id"]), "excluded"
    )
    assert model.calls == 0


def test_a_delayed_create_retry_cannot_restore_a_deleted_entry(profiles):
    repo, _, owner, _, _ = profiles
    store = JournalStore(repo)
    data = entry()
    saved, _ = store.create(owner, data, "save")
    store.delete(owner, UUID(saved["id"]), 1, "delete")
    with pytest.raises(ProfileConflict):
        store.create(owner, data, "late-retry")
    assert store.list(owner, "review")["entries"] == []


def test_included_current_entry_produces_pending_reviewable_observations(profiles):
    repo, _, owner, _, _ = profiles
    store = JournalStore(repo)
    model = JournalModel()
    saved, _ = store.create(owner, entry(), "save")
    service = JournalService(store, LifeProfileBot(repo, model))
    result = service.analyse(owner, UUID(saved["id"]), "analyse")
    assert result["entry"]["analysis_state"] == "processed"
    items = repo.snapshot(owner, "review")["items"]
    assert len(items) == 1 and items[0]["state"] == "pending"
    assert items[0]["source_context"][0]["source_type"] == "journal_entry"
    assert repo.context(owner, "context") == []
    service.analyse(owner, UUID(saved["id"]), "retry")
    assert model.calls == 1


def test_edit_or_exclusion_retracts_derived_understanding_and_conflicts_are_safe(profiles):
    repo, pool, owner, _, _ = profiles
    store = JournalStore(repo)
    saved, _ = store.create(owner, entry(), "save")
    JournalService(store, LifeProfileBot(repo, JournalModel())).analyse(
        owner, UUID(saved["id"]), "analyse"
    )
    update = EntryUpdate(
        title=saved["title"],
        content=saved["content"],
        entry_date=saved["entry_date"],
        include_in_profile=False,
        expected_version=1,
        disclosure_version=1,
    )
    excluded = store.update(owner, UUID(saved["id"]), update, "exclude")
    assert excluded["analysis_state"] == "excluded"
    assert repo.snapshot(owner, "review")["items"] == []
    with pool.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM life_profile_journal_observations WHERE subject=%s", (owner,)
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(ProfileConflict):
        store.update(owner, UUID(saved["id"]), update, "stale")


@pytest.mark.parametrize("change", ["exclude", "edit", "delete", "revoke"])
def test_changes_during_model_work_prevent_stale_proposals(profiles, change):
    repo, _, owner, _, _ = profiles
    store = JournalStore(repo)
    saved, _ = store.create(owner, entry(), "save")
    entry_id = UUID(saved["id"])

    def during():
        if change == "delete":
            store.delete(owner, entry_id, 1, "delete")
        elif change == "revoke":
            repo.set_consent(owner, Consent(purpose="Understand my life"), "revoke")
        else:
            store.update(
                owner,
                entry_id,
                EntryUpdate(
                    title=saved["title"],
                    content=saved["content"] + (" Changed." if change == "edit" else ""),
                    entry_date=saved["entry_date"],
                    include_in_profile=change != "exclude",
                    expected_version=1,
                    disclosure_version=1,
                ),
                "change",
            )

    service = JournalService(store, LifeProfileBot(repo, JournalModel(during)))
    if change == "delete":
        with pytest.raises(ProfileMissing):
            service.analyse(owner, entry_id, "analyse")
    else:
        service.analyse(owner, entry_id, "analyse")
    assert repo.snapshot(owner, "review")["items"] == []


def test_a_journal_source_cannot_be_smuggled_into_ordinary_analysis():
    request = AnalyseRequest(
        purpose="Understand my life",
        messages=[
            SourceMessage(
                message_id="journal:" + str(uuid4()),
                conversation_id="synthetic",
                source_type="journal_entry",
                speaker="user",
                content="Reflection",
            )
        ],
    )
    with pytest.raises(ConsentRequired):
        LifeProfileBot(None, ModelDouble()).analyse("owner", request, "request")


def test_journal_context_dependencies_are_also_retracted(profiles):
    repo, _, owner, _, _ = profiles
    store = JournalStore(repo)
    saved, _ = store.create(owner, entry(), "save")
    JournalService(store, LifeProfileBot(repo, JournalModel())).analyse(
        owner, UUID(saved["id"]), "analyse"
    )
    item = repo.snapshot(owner, "review")["items"][0]
    repo.decide(owner, UUID(item["id"]), Decision(expected_version=1, action="accept"), "accept")
    request = AnalyseRequest(
        purpose="Adapt communication",
        messages=[
            SourceMessage(
                message_id="message-1",
                conversation_id="later-conversation",
                source_type="conversation",
                speaker="user",
                content="I prefer short answers.",
            )
        ],
    )
    LifeProfileBot(repo, ModelDouble()).analyse(owner, request, "later")
    assert len(repo.snapshot(owner, "review")["items"]) == 2
    store.update(
        owner,
        UUID(saved["id"]),
        EntryUpdate(
            title=saved["title"],
            content=saved["content"],
            entry_date=saved["entry_date"],
            include_in_profile=False,
            expected_version=1,
            disclosure_version=1,
        ),
        "exclude",
    )
    assert repo.snapshot(owner, "review")["items"] == []


@pytest.mark.parametrize("actor", ["founder", "administrator", "coordinator_ai", "specialist_ai"])
def test_journal_routes_reject_other_roles(gateway, actor):
    client, token = gateway
    response = client.get(
        "/v1/life-profile/journal/settings",
        headers={"Authorization": "Bearer " + token(actor=actor, scope=["profile:journal_read"])},
    )
    assert response.status_code == 403


def test_journal_route_needs_its_own_scope(gateway):
    client, token = gateway
    assert (
        client.get(
            "/v1/life-profile/journal/settings", headers={"Authorization": "Bearer " + token()}
        ).status_code
        == 403
    )
