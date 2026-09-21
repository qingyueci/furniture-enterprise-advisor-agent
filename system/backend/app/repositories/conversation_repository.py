from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Message


class ConversationRepository:
    def get_owned(self, session: Session, *, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        return session.scalar(select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        ))

    def list_owned(self, session: Session, *, user_id: UUID, page: int,
                   page_size: int, include_deleted: bool = False) -> tuple[list[Conversation], int]:
        base = select(Conversation).where(Conversation.user_id == user_id)
        base = base.where(Conversation.deleted_at.is_not(None) if include_deleted else Conversation.deleted_at.is_(None))
        total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = list(session.scalars(
            base.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ))
        return items, total

    def get_owned_including_deleted(self, session: Session, *, conversation_id: UUID,
                                    user_id: UUID) -> Conversation | None:
        return session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id,
        ).with_for_update())

    def soft_delete(self, session: Session, *, conversation_id: UUID, user_id: UUID) -> bool:
        conversation = self.get_owned_including_deleted(session, conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            return False
        if conversation.deleted_at is None:
            conversation.deleted_at = func.now()
            session.flush()
        return True

    def soft_delete_many(self, session: Session, *, conversation_ids: list[UUID], user_id: UUID) -> int:
        rows = list(session.scalars(select(Conversation).where(
            Conversation.id.in_(conversation_ids), Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        ).with_for_update()))
        if len(rows) != len(set(conversation_ids)):
            return -1
        for row in rows:
            row.deleted_at = func.now()
        return len(rows)

    def restore(self, session: Session, *, conversation_id: UUID, user_id: UUID) -> bool:
        conversation = self.get_owned_including_deleted(session, conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            return False
        conversation.deleted_at = None
        session.flush()
        return True

    def permanent_delete(self, session: Session, *, conversation_id: UUID, user_id: UUID) -> bool:
        conversation = self.get_owned_including_deleted(session, conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            return False
        session.delete(conversation)
        session.flush()
        return True

    def list_messages(self, session: Session, *, conversation_id: UUID, page: int,
                      page_size: int) -> tuple[list[Message], int]:
        base = select(Message).where(Message.conversation_id == conversation_id)
        total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = list(session.scalars(
            base.order_by(Message.created_at.asc(), Message.id.asc())
            .offset((page - 1) * page_size).limit(page_size)
        ))
        return items, total

    def recent_messages(self, session: Session, *, conversation_id: UUID,
                        limit: int = 12) -> list[Message]:
        items = list(session.scalars(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        ))
        return list(reversed(items))

    def add_exchange(self, session: Session, *, user_id: UUID, conversation_id: UUID | None,
                     title: str, user_content: str, assistant_content: str, task_type: str,
                     citations: list[dict], tool_summary: list[dict],
                     structured_data: dict | None, warnings: list[str] | None = None,
                     ) -> tuple[Conversation, Message]:
        if conversation_id is None:
            conversation = Conversation(user_id=user_id, title=title)
            session.add(conversation)
            session.flush()
        else:
            conversation = self.get_owned(session, conversation_id=conversation_id, user_id=user_id)
            if conversation is None:
                raise LookupError("conversation not accessible")
        user_created_at = datetime.now(timezone.utc)
        session.add(Message(conversation_id=conversation.id, role="USER", content=user_content,
                            citations=[], tool_summary=[], created_at=user_created_at))
        assistant = Message(
            conversation_id=conversation.id,
            role="ASSISTANT",
            content=assistant_content,
            citations=citations,
            tool_summary=tool_summary,
            warnings=list(dict.fromkeys(warnings or [])),
            structured_data=structured_data,
            task_type=task_type,
            created_at=user_created_at + timedelta(microseconds=1),
        )
        session.add(assistant)
        conversation.updated_at = func.now()
        session.flush()
        return conversation, assistant


__all__ = ["ConversationRepository"]
