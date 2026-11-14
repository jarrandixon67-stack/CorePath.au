import hashlib
import json
from uuid import UUID

from life_profile.models import AnalyseRequest
from persy.models import Message, PrivacyRequired, ProfileAnalysis, Reply
from specialists.models import InvalidEvidence
from specialists.registry import Domain


class Runtime:
    def __init__(self, repository, provider, services, settings):
        self.repository, self.provider, self.services, self.settings = (
            repository,
            provider,
            services,
            settings,
        )

    def chat(self, member, conversation_id: UUID, message: Message):
        repo = self.repository
        operation, privacy, _ = repo.begin(member, "chat", self.settings, conversation_id)
        try:
            if message.use_profile_context and not privacy["profile_context_enabled"]:
                raise PrivacyRequired
            context = (
                self.services.profile(member, "context") if message.use_profile_context else []
            )
            history = (
                repo.history(member, conversation_id, limit=self.settings.history_turns)
                if privacy["history_enabled"]
                else []
            )
            stamp = (
                hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
                if message.use_profile_context
                else None
            )
            # Reading old answers remains an owner control; model context must
            # not silently restore changed or withdrawn profile information.
            history = [
                {key: value for key, value in turn.items() if key != "profile_context_stamp"}
                for turn in history
                if not turn.get("profile_context_used")
                or turn.get("profile_context_stamp") == stamp
            ]
            repo.check(member, operation)
            reply = Reply.model_validate(
                self.provider.reply(
                    {
                        "member_message": message.message,
                        "specialist_preferences": {
                            "mode": message.specialist_mode,
                            "max_specialists": message.max_specialists,
                            "all_eleven_available": True,
                        },
                        "communication_style": privacy["communication_style"],
                        "recent_conversation": history,
                        "approved_profile_context": context,
                        "research_for_current_message_performed": False,
                    }
                )
            )
            if reply.research_proposal:
                # Trusted member controls override model-written preferences.
                # The exact resulting proposal still requires existing approval.
                proposal = reply.research_proposal.model_dump(mode="json")
                proposal.update(
                    specialist_mode=message.specialist_mode,
                    max_specialist_calls=message.max_specialists,
                    allowed_domains=list(Domain),
                )
                reply.research_proposal = type(reply.research_proposal).model_validate(proposal)
            if message.use_profile_context and self.services.profile(member, "context") != context:
                raise InvalidEvidence("Approved context changed while replying")
            proposed = repo.finish(
                member,
                operation,
                {
                    "user_message": message.message,
                    "assistant_reply": reply.model_dump(mode="json"),
                    "profile_context_used": message.use_profile_context,
                    "profile_context_stamp": stamp,
                },
                reply.research_proposal,
                self.settings,
            )
            return {
                "turn_id": str(operation),
                "name": "Persy",
                "message": reply.message,
                "next_steps": reply.next_steps,
                "follow_up": reply.follow_up,
                "research_proposal": proposed,
                "history_saved": privacy["history_enabled"],
                "profile_context_used": message.use_profile_context,
            }
        except Exception:
            repo.fail(member, operation, "reply_unavailable_or_privacy_changed")
            raise

    def research(self, member, conversation_id, proposal_id):
        repo = self.repository
        operation, _, proposal = repo.begin(
            member, "research", self.settings, conversation_id, proposal_id
        )
        try:
            repo.check(member, operation)
            result = self.services.research(member, proposal, operation)
            repo.finish(member, operation, {"research_reply": result})
            return {"turn_id": str(operation), "name": "Persy", **result}
        except Exception:
            repo.fail(member, operation, "research_unavailable_or_privacy_changed")
            raise

    def profile_action(
        self, member, action, body=None, item_id=None, analysis: ProfileAnalysis | None = None
    ):
        repo = self.repository
        operation, _, _ = repo.begin(
            member, "profile_analysis" if action == "analyse" else "profile_control", self.settings
        )
        try:
            if analysis:
                body = AnalyseRequest(
                    purpose=analysis.purpose,
                    messages=repo.selected_messages(member, analysis.turn_ids),
                ).model_dump(mode="json")
            repo.check(member, operation)
            result = self.services.profile(member, action, body, item_id)
            repo.finish(member, operation)
            return result
        except Exception:
            repo.fail(member, operation, "profile_service_unavailable_or_privacy_changed")
            raise
