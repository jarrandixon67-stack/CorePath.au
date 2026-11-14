import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet, InvalidToken
from psycopg import sql
from psycopg_pool import ConnectionPool

from app.migrations import load_migrations, migrate
from persy.models import Message, Missing, PrivacyChange, PrivacyRequired, Reply, ResearchProposal
from persy.repository import Repository
from persy.runtime import Runtime
from persy.security import Member
from persy.settings import Settings
from persy.vault import Vault
from specialists.models import (
    BudgetExceeded,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
)
from specialists.registry import Domain

MIGRATIONS = Path(__file__).resolve().parents[2] / "persy/database/migrations"


def fresh(member):
    return replace(member, request_id=str(uuid4()))


def privacy(revision=0, **changes):
    return PrivacyChange(expected_revision=revision, model_processing_enabled=True, **changes)


def proposal():
    return ResearchProposal(
        question="What does general evidence say about spaced learning?",
        allowed_domains=["learning-intelligence"],
        max_specialist_calls=1,
        specialist_mode="auto",
        allow_collaboration=False,
    )


class Model:
    def __init__(self, *, research=False, effect=None):
        self.calls, self.research, self.effect = [], research, effect

    def reply(self, context):
        self.calls.append(context)
        if self.effect:
            self.effect()
        return Reply(
            message="Let's choose one manageable next step.",
            next_steps=["Try one short practice session."],
            follow_up="What would help you get started?",
            research_proposal=proposal() if self.research else None,
        )


class Connected:
    def __init__(self):
        self.profile_calls, self.research_calls = [], []
        self.context = [
            {
                "id": str(uuid4()),
                "statement": "Prefers short explanations",
                "category": "personal_growth_development",
                "dimensions": ["self_identity"],
                "understanding_level": "confirmed_understanding",
            }
        ]

    def profile(self, member, action, body=None, item_id=None):
        self.profile_calls.append((member.subject, action, body, item_id))
        return self.context if action == "context" else {"review_required": True}

    def research(self, member, question, operation_id):
        self.research_calls.append((member.subject, question.model_dump(mode="json")))
        return {
            "state": "needs_evidence",
            "findings": [],
            "message": "More approved evidence is needed.",
        }


@pytest.fixture
def persy_store():
    url = os.getenv("PERSY_DATABASE_URL")
    if not url:
        pytest.skip("requires a separate disposable Persy PostgreSQL database")
    schema = "persy_test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        if not conn.execute("SELECT current_database()").fetchone()[0].endswith("_test"):
            pytest.fail("Persy tests require a disposable *_test database")
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        pool = None
        try:
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            migrations = load_migrations(MIGRATIONS)
            assert len(migrate(conn, migrations)) == 1
            assert migrate(conn, migrations) == []
            pool = ConnectionPool(
                url,
                min_size=1,
                max_size=5,
                open=True,
                kwargs={
                    "autocommit": False,
                    "options": f"-c search_path={schema} -c statement_timeout=5000",
                },
            )
            pool.wait(timeout=10)
            repo = Repository(pool, Vault(Fernet(Fernet.generate_key())))
            member = Member(
                "synthetic-owner-" + uuid4().hex,
                str(uuid4()),
                int(time.time()) + 240,
                "synthetic-member-assertion",
            )
            repo.set_privacy(member, privacy())
            conversation = UUID(
                repo.create_conversation(fresh(member), Settings())["conversation_id"]
            )
            yield repo, conn, member, conversation, Settings()
        finally:
            if pool:
                pool.close()
            conn.execute("SET search_path TO public")
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_chat_defaults_to_plain_language_and_no_history_profiling_or_research(persy_store):
    repo, conn, member, conversation, settings = persy_store
    model, connected = Model(research=True), Connected()
    reply = Runtime(repo, model, connected, settings).chat(
        fresh(member),
        conversation,
        Message(message="Synthetic private goal: learn a little each day"),
    )
    assert reply["name"] == "Persy" and not reply["history_saved"]
    assert reply["research_proposal"]["review_required"]
    assert model.calls[0]["communication_style"] == "plain"
    assert model.calls[0]["approved_profile_context"] == []
    assert connected.profile_calls == [] and connected.research_calls == []
    assert repo.history(member, conversation) == []
    assert conn.execute("SELECT payload_ciphertext FROM persy_operations").fetchone()[0] is None


def test_history_is_encrypted_bound_to_owner_and_used_only_when_enabled(persy_store):
    repo, conn, member, conversation, settings = persy_store
    repo.set_privacy(
        fresh(member), privacy(1, history_enabled=True, communication_style="detailed")
    )
    model = Model()
    runtime = Runtime(repo, model, Connected(), settings)
    first = runtime.chat(
        fresh(member),
        conversation,
        Message(message="Synthetic private marker 47: I prefer direct explanations"),
    )
    runtime.chat(fresh(member), conversation, Message(message="Help me make a plan"))
    assert model.calls[-1]["communication_style"] == "detailed"
    assert model.calls[-1]["recent_conversation"][0]["user_message"].startswith(
        "Synthetic private marker 47"
    )
    assert len(repo.history(member, conversation)) == 2
    raw = conn.execute(
        "SELECT payload_ciphertext FROM persy_operations WHERE id = %s", (UUID(first["turn_id"]),)
    ).fetchone()[0]
    assert b"Synthetic private marker 47" not in bytes(raw)
    for table in ("persy_audit", "persy_nonces", "persy_members"):
        assert "Synthetic private marker 47" not in str(
            conn.execute(
                sql.SQL("SELECT row_to_json(t) FROM {} t").format(sql.Identifier(table))
            ).fetchall()
        )


def test_history_withdrawal_erases_existing_text_and_invalidates_proposals(persy_store):
    repo, conn, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True))
    reply = Runtime(repo, Model(research=True), Connected(), settings).chat(
        fresh(member), conversation, Message(message="A synthetic private message")
    )
    repo.set_privacy(fresh(member), privacy(2, history_enabled=False))
    assert repo.history(member, conversation) == []
    assert conn.execute(
        "SELECT payload_ciphertext, state FROM persy_research_proposals"
    ).fetchone() == (None, "cancelled")
    with pytest.raises(RunConflict):
        Runtime(repo, Model(), Connected(), settings).research(
            fresh(member), conversation, UUID(reply["research_proposal"]["id"])
        )


@pytest.mark.parametrize("attack", ["read", "chat", "delete", "selected_messages", "research"])
def test_another_member_cannot_access_conversations_turns_or_proposals(persy_store, attack):
    repo, _, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True))
    reply = Runtime(repo, Model(research=True), Connected(), settings).chat(
        fresh(member), conversation, Message(message="Owned private content")
    )
    other = replace(member, subject="synthetic-other-" + uuid4().hex, request_id=str(uuid4()))
    repo.set_privacy(other, privacy(history_enabled=True))
    with pytest.raises(Missing):
        if attack == "read":
            repo.history(other, conversation)
        elif attack == "chat":
            Runtime(repo, Model(), Connected(), settings).chat(
                fresh(other), conversation, Message(message="Try to access another owner")
            )
        elif attack == "delete":
            repo.delete_conversation(fresh(other), conversation)
        elif attack == "selected_messages":
            repo.selected_messages(other, [UUID(reply["turn_id"])])
        else:
            Runtime(repo, Model(), Connected(), settings).research(
                fresh(other), conversation, UUID(reply["research_proposal"]["id"])
            )


def test_research_requires_explicit_approval_and_sends_only_the_exact_stored_question(persy_store):
    repo, conn, member, conversation, settings = persy_store
    connected = Connected()
    runtime = Runtime(repo, Model(research=True), connected, settings)
    reply = runtime.chat(
        fresh(member),
        conversation,
        Message(message="My private name and account details must not become the research payload"),
    )
    assert connected.research_calls == []
    result = runtime.research(fresh(member), conversation, UUID(reply["research_proposal"]["id"]))
    assert result["state"] == "needs_evidence"
    expected = proposal().model_dump(mode="json")
    expected.update(allowed_domains=[d.value for d in Domain], max_specialist_calls=11)
    assert connected.research_calls[0][1] == expected
    assert "private name" not in str(connected.research_calls)
    assert conn.execute(
        "SELECT state, payload_ciphertext FROM persy_research_proposals"
    ).fetchone() == ("completed", None)
    with pytest.raises(RunConflict):
        runtime.research(fresh(member), conversation, UUID(reply["research_proposal"]["id"]))


def test_expired_research_proposal_cannot_call_the_coordinator(persy_store):
    repo, conn, member, conversation, settings = persy_store
    connected = Connected()
    runtime = Runtime(repo, Model(research=True), connected, settings)
    reply = runtime.chat(
        fresh(member), conversation, Message(message="Help investigate general evidence")
    )
    conn.execute("UPDATE persy_research_proposals SET expires_at = now() - interval '1 second'")
    with pytest.raises(RunConflict):
        runtime.research(fresh(member), conversation, UUID(reply["research_proposal"]["id"]))
    assert not connected.research_calls


def test_profile_context_needs_both_local_permission_and_explicit_per_turn_selection(persy_store):
    repo, _, member, conversation, settings = persy_store
    model, connected = Model(), Connected()
    runtime = Runtime(repo, model, connected, settings)
    with pytest.raises(PrivacyRequired):
        runtime.chat(
            fresh(member),
            conversation,
            Message(message="Help me reflect", use_profile_context=True),
        )
    assert model.calls == [] and connected.profile_calls == []
    repo.set_privacy(fresh(member), privacy(1, profile_context_enabled=True))
    runtime.chat(fresh(member), conversation, Message(message="Still no automatic profiling"))
    assert connected.profile_calls == []
    runtime.chat(
        fresh(member),
        conversation,
        Message(message="Use my shared understanding", use_profile_context=True),
    )
    assert len(connected.profile_calls) == 2
    assert model.calls[-1]["approved_profile_context"] == connected.context
    assert all(call[1] == "context" for call in connected.profile_calls)


@pytest.mark.parametrize("change", ["privacy", "delete", "profile_context", "member_inactive"])
def test_revocation_or_deletion_during_a_model_call_prevents_accepting_the_reply(
    persy_store, change
):
    repo, conn, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True, profile_context_enabled=True))
    connected = Connected()

    def mutate():
        if change == "privacy":
            repo.set_privacy(
                fresh(member), PrivacyChange(expected_revision=2, model_processing_enabled=False)
            )
        elif change == "delete":
            repo.delete_conversation(fresh(member), conversation)
        elif change == "member_inactive":
            conn.execute("UPDATE persy_members SET is_active = FALSE")
        else:
            connected.context = []

    runtime = Runtime(repo, Model(effect=mutate), connected, settings)
    with pytest.raises((RunConflict, Missing, PrivacyRequired, InvalidEvidence)):
        runtime.chat(
            fresh(member),
            conversation,
            Message(
                message="This reply must not survive revoked permission",
                use_profile_context=change == "profile_context",
            ),
        )
    assert (
        conn.execute(
            "SELECT count(*) FROM persy_operations WHERE payload_ciphertext IS NOT NULL"
        ).fetchone()[0]
        == 0
    )


def test_delete_conversation_purges_text_proposals_and_prevents_budget_reset(persy_store):
    repo, conn, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True))
    runtime = Runtime(repo, Model(research=True), Connected(), settings)
    runtime.chat(fresh(member), conversation, Message(message="Private text to erase"))
    repo.delete_conversation(fresh(member), conversation)
    assert conn.execute("SELECT count(*) FROM persy_research_proposals").fetchone()[0] == 0
    assert conn.execute(
        "SELECT conversation_id, payload_ciphertext FROM persy_operations"
    ).fetchone() == (None, None)
    new_conversation = UUID(repo.create_conversation(fresh(member), settings)["conversation_id"])
    with pytest.raises(BudgetExceeded):
        Runtime(
            repo, Model(), Connected(), settings.model_copy(update={"max_operations_per_24h": 1})
        ).chat(fresh(member), new_conversation, Message(message="Cannot reset the paid-call limit"))


def test_ciphertext_swapping_and_wrong_keys_cannot_return_another_record(persy_store):
    repo, conn, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True))
    runtime = Runtime(repo, Model(), Connected(), settings)
    first = runtime.chat(fresh(member), conversation, Message(message="First private record"))
    second = runtime.chat(fresh(member), conversation, Message(message="Second private record"))
    conn.execute(
        "UPDATE persy_operations SET payload_ciphertext = (SELECT payload_ciphertext FROM persy_operations WHERE id = %s) WHERE id = %s",
        (UUID(first["turn_id"]), UUID(second["turn_id"])),
    )
    with pytest.raises(InvalidToken):
        repo.history(member, conversation)
    with pytest.raises(InvalidToken):
        Repository(repo.pool, Vault(Fernet(Fernet.generate_key()))).history(member, conversation)


def test_replay_parallel_operation_limits_and_expired_leases_are_enforced(persy_store):
    repo, conn, member, conversation, settings = persy_store
    operation_member = fresh(member)
    first, _, _ = repo.begin(operation_member, "chat", settings, conversation)
    with pytest.raises(RunConflict):
        repo.begin(operation_member, "chat", settings, conversation)
    with pytest.raises(BudgetExceeded):
        repo.begin(fresh(member), "chat", settings, conversation)
    conn.execute("UPDATE persy_operations SET lease_expires_at = now() - interval '1 second'")
    second, _, _ = repo.begin(fresh(member), "chat", settings, conversation)
    assert (
        conn.execute("SELECT error_code FROM persy_operations WHERE id = %s", (first,)).fetchone()[
            0
        ]
        == "execution_lease_expired"
    )
    repo.fail(member, second, "synthetic_cleanup")

    def begin(_):
        try:
            repo.begin(fresh(member), "chat", settings, conversation)
            return "started"
        except BudgetExceeded:
            return "limited"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(begin, range(2))) == ["limited", "started"]


def test_selected_profile_messages_are_only_owned_retained_user_messages(persy_store):
    repo, _, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True))
    reply = Runtime(repo, Model(), Connected(), settings).chat(
        fresh(member), conversation, Message(message="Only this user statement should be profiled")
    )
    selected = repo.selected_messages(member, [UUID(reply["turn_id"])])
    assert selected[0]["speaker"] == "user"
    assert selected[0]["content"] == "Only this user statement should be profiled"
    assert "Try one short practice session" not in str(selected)


def test_profile_control_remains_available_when_model_consent_is_withdrawn(persy_store):
    repo, _, member, _, settings = persy_store
    repo.set_privacy(
        fresh(member), PrivacyChange(expected_revision=1, model_processing_enabled=False)
    )
    connected = Connected()
    runtime = Runtime(repo, Model(), connected, settings)
    assert runtime.profile_action(fresh(member), "review")["review_required"]
    with pytest.raises(PrivacyRequired):
        runtime.profile_action(fresh(member), "analyse")


def test_model_errors_are_recorded_without_raw_messages_or_provider_details(persy_store):
    repo, conn, member, conversation, settings = persy_store

    def fail():
        raise ProviderUnavailable("synthetic-private-upstream-error")

    with pytest.raises(ProviderUnavailable):
        Runtime(repo, Model(effect=fail), Connected(), settings).chat(
            fresh(member), conversation, Message(message="Synthetic private user message")
        )
    rows = conn.execute("SELECT row_to_json(t) FROM persy_operations t").fetchall()
    assert "synthetic-private-upstream-error" not in str(
        rows
    ) and "Synthetic private user message" not in str(rows)
    assert rows[0][0]["state"] == "failed"


def test_previous_profile_assisted_turns_cannot_silently_restore_withdrawn_context(persy_store):
    repo, _, member, conversation, settings = persy_store
    repo.set_privacy(fresh(member), privacy(1, history_enabled=True, profile_context_enabled=True))
    model, connected = Model(), Connected()
    runtime = Runtime(repo, model, connected, settings)
    runtime.chat(
        fresh(member),
        conversation,
        Message(message="Use the shared context", use_profile_context=True),
    )
    assert len(repo.history(member, conversation)) == 1
    runtime.chat(
        fresh(member), conversation, Message(message="Do not use profile context this time")
    )
    assert model.calls[-1]["recent_conversation"] == []
    connected.context = []
    runtime.chat(
        fresh(member),
        conversation,
        Message(message="My shared understanding changed", use_profile_context=True),
    )
    assert len(model.calls[-1]["recent_conversation"]) == 1
    assert not model.calls[-1]["recent_conversation"][0]["profile_context_used"]


def test_restricted_runtime_role_supports_consent_chat_and_erasure_without_other_data_access(
    persy_store,
):
    repo, conn, member, conversation, settings = persy_store
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    role = "persy_role_test_" + uuid4().hex
    template = (MIGRATIONS.parent / "runtime-role.sql").read_text()
    conn.execute(
        template.replace("corepath_persy_runtime", role).replace(
            "SCHEMA public", "SCHEMA " + schema
        )
    )
    restricted_pool = None

    def assume_role(connection):
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        connection.commit()

    try:
        conn.execute("CREATE TABLE life_profiles (private_value TEXT)")
        conn.execute("CREATE TABLE knowledge_sources (private_value TEXT)")
        restricted_pool = ConnectionPool(
            repo.pool.conninfo,
            min_size=1,
            max_size=2,
            open=True,
            kwargs={"options": f"-c search_path={schema}", "autocommit": False},
            configure=assume_role,
        )
        restricted_pool.wait(timeout=10)
        private = Repository(restricted_pool, repo.vault)
        private.set_privacy(fresh(member), privacy(1, history_enabled=True))
        runtime = Runtime(private, Model(research=True), Connected(), settings)
        runtime.chat(fresh(member), conversation, Message(message="Private restricted-role test"))
        assert len(private.history(member, conversation)) == 1
        private.delete_conversation(fresh(member), conversation)
        assert (
            conn.execute(
                "SELECT count(*) FROM persy_operations WHERE payload_ciphertext IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        for forbidden in (
            "SELECT * FROM life_profiles",
            "SELECT * FROM knowledge_sources",
            "UPDATE persy_members SET is_active = FALSE",
            "DELETE FROM persy_nonces",
            "DELETE FROM persy_audit",
        ):
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                restricted_pool.connection() as restricted,
            ):
                restricted.execute(forbidden)
    finally:
        if restricted_pool:
            restricted_pool.close()
        conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
