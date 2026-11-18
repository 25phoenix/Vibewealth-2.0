"""Tenant-scoped conversation persistence and read-only DTO projection."""

from datetime import timezone
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models import AssistantConversation, AssistantMessage, AssistantTurn, User
from app.schemas.assistant import (
    MAX_CONVERSATIONS, TURN_ERROR_MESSAGES, ConversationCreateRequest,
    ConversationDto, ConversationPageDto, HttpErrorCode, MessageDto,
    MessagePageDto, MessageTurnMetadata, PaginationRequest, PersistedFailureCode,
    TurnDto, TurnError, TurnStatus,
)
from app.services.assistant_contracts import ContractViolation, project_lifecycle


def owned_conversation(db: Session, *, user_id: UUID, conversation_id: UUID, lock=False):
    statement = select(AssistantConversation).where(
        AssistantConversation.user_id == user_id, AssistantConversation.id == conversation_id,
    )
    if lock:
        statement = statement.with_for_update()
    conversation = db.scalar(statement.execution_options(populate_existing=True))
    if conversation is None:
        raise ContractViolation(HttpErrorCode.CONVERSATION_NOT_FOUND)
    return conversation


def _creation_lookup(db: Session, conversation_id: UUID):
    # Global UUID lookup is restricted to create-collision classification.
    return db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
    ).execution_options(populate_existing=True))


def resolve_creation(db: Session, *, user_id: UUID, payload: ConversationCreateRequest):
    existing = _creation_lookup(db, payload.id)
    if existing is None or existing.user_id != user_id:
        raise ContractViolation(HttpErrorCode.CONVERSATION_NOT_FOUND)
    existing = owned_conversation(db, user_id=user_id, conversation_id=payload.id, lock=True)
    if existing.title != payload.title:
        raise ContractViolation(HttpErrorCode.CONVERSATION_CREATE_CONFLICT)
    return existing


def _insert_conversation(db: Session, *, user_id: UUID, payload: ConversationCreateRequest):
    conversation = AssistantConversation(id=payload.id, user_id=user_id, title=payload.title)
    db.add(conversation)
    db.flush()
    return conversation


def create_conversation(db: Session, *, user_id: UUID, payload: ConversationCreateRequest):
    """Caller already holds its authenticated session lock and owns commit/rollback."""
    if _creation_lookup(db, payload.id) is not None:
        return resolve_creation(db, user_id=user_id, payload=payload), False
    # Do not take a conversation lock before this owner-capacity lock.
    if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
        raise ContractViolation(HttpErrorCode.AUTHENTICATION_REQUIRED)
    # Another session of this user may have created while we waited for User.
    if _creation_lookup(db, payload.id) is not None:
        return resolve_creation(db, user_id=user_id, payload=payload), False
    count = db.scalar(select(func.count()).select_from(AssistantConversation).where(
        AssistantConversation.user_id == user_id,
    ))
    if count >= MAX_CONVERSATIONS:
        raise ContractViolation(HttpErrorCode.CONVERSATION_LIMIT_REACHED)
    return _insert_conversation(db, user_id=user_id, payload=payload), True


def is_creation_primary_key_conflict(error) -> bool:
    original = error.orig
    return (
        (getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)) == "23505"
        and getattr(getattr(original, "diag", None), "constraint_name", None) == "pk_assistant_conversations"
    )


def delete_conversation(db: Session, *, user_id: UUID, conversation_id: UUID):
    conversation = owned_conversation(db, user_id=user_id, conversation_id=conversation_id, lock=True)
    db.delete(conversation)  # Database cascades only assistant messages and turns.
    db.flush()


def _utc(value):
    return value.astimezone(timezone.utc) if value is not None else None


def _metadata(turn):
    return MessageTurnMetadata(id=turn.id, status=turn.status, attempt_no=turn.attempt_no)


def _message_dto(message, metadata=None):
    return MessageDto(
        id=message.id, conversation_id=message.conversation_id, sequence_no=message.sequence_no,
        role=message.role, content=message.content, created_at=_utc(message.created_at), turn=metadata,
    )


def conversation_dtos(db: Session, *, user_id: UUID, conversations):
    if not conversations:
        return []
    ids = [conversation.id for conversation in conversations]
    last = dict(db.execute(select(
        AssistantMessage.conversation_id, func.max(AssistantMessage.sequence_no),
    ).where(AssistantMessage.user_id == user_id, AssistantMessage.conversation_id.in_(ids))
        .group_by(AssistantMessage.conversation_id)).all())
    unresolved = db.scalars(select(AssistantTurn).where(
        AssistantTurn.user_id == user_id, AssistantTurn.conversation_id.in_(ids),
        AssistantTurn.status.in_(("pending", "failed")),
    )).all()
    messages = {}
    if unresolved:
        positions = [(turn.conversation_id, turn.user_sequence_no) for turn in unresolved]
        # One bounded read for the current user message of each unresolved turn.
        messages = {
            (message.conversation_id, message.sequence_no): message
            for message in db.scalars(select(AssistantMessage).where(
                AssistantMessage.user_id == user_id,
                tuple_(AssistantMessage.conversation_id, AssistantMessage.sequence_no).in_(positions),
            )).all()
        }
    observed_at = _utc(db.scalar(select(func.clock_timestamp())))
    turns = {}
    for turn in unresolved:
        projection = project_lifecycle(
            status=TurnStatus(turn.status), attempt_no=turn.attempt_no,
            lease_expires_at=_utc(turn.lease_expires_at),
            error_code=PersistedFailureCode(turn.error_code) if turn.error_code else None,
            observed_at=observed_at,
        )
        turns[turn.conversation_id] = TurnDto(
            id=turn.id, conversation_id=turn.conversation_id, idempotency_key=turn.idempotency_key,
            status=turn.status, attempt_no=turn.attempt_no,
            user_message=_message_dto(messages[(turn.conversation_id, turn.user_sequence_no)], _metadata(turn)),
            assistant_message=None, created_at=_utc(turn.created_at),
            attempt_started_at=_utc(turn.attempt_started_at), attempt_finished_at=_utc(turn.attempt_finished_at),
            lease_expires_at=_utc(turn.lease_expires_at), context_as_of=_utc(turn.context_as_of),
            financial_date=turn.financial_date, lease_expired=projection.lease_expired,
            can_retry=projection.can_retry, can_abandon=projection.can_abandon,
            error=TurnError(code=projection.error_code, message=TURN_ERROR_MESSAGES[projection.error_code])
            if projection.error_code else None,
        )
    return [ConversationDto(
        id=conversation.id, title=conversation.title, created_at=_utc(conversation.created_at),
        updated_at=_utc(conversation.updated_at), last_sequence_no=last.get(conversation.id, 0),
        unresolved_turn=turns.get(conversation.id),
    ) for conversation in conversations]


def get_conversation(db: Session, *, user_id: UUID, conversation_id: UUID):
    conversation = owned_conversation(db, user_id=user_id, conversation_id=conversation_id)
    return conversation_dtos(db, user_id=user_id, conversations=[conversation])[0]


def list_conversations(db: Session, *, user_id: UUID, pagination: PaginationRequest):
    total = db.scalar(select(func.count()).select_from(AssistantConversation).where(
        AssistantConversation.user_id == user_id,
    ))
    conversations = db.scalars(select(AssistantConversation).where(
        AssistantConversation.user_id == user_id,
    ).order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id.desc())
        .offset(pagination.offset).limit(pagination.limit)).all() if pagination.offset < total else []
    return ConversationPageDto(
        items=conversation_dtos(db, user_id=user_id, conversations=conversations), total=total,
        offset=pagination.offset, limit=pagination.limit,
    )


def list_messages(db: Session, *, user_id: UUID, conversation_id: UUID, pagination: PaginationRequest):
    owned_conversation(db, user_id=user_id, conversation_id=conversation_id)
    conditions = (AssistantMessage.user_id == user_id, AssistantMessage.conversation_id == conversation_id)
    total = db.scalar(select(func.count()).select_from(AssistantMessage).where(*conditions))
    messages = db.scalars(select(AssistantMessage).where(*conditions)
        .order_by(AssistantMessage.sequence_no).offset(pagination.offset).limit(pagination.limit)).all() if pagination.offset < total else []
    metadata = {}
    if messages:
        sequences = [message.sequence_no for message in messages]
        turns = db.scalars(select(AssistantTurn).where(
            AssistantTurn.user_id == user_id, AssistantTurn.conversation_id == conversation_id,
            or_(AssistantTurn.user_sequence_no.in_(sequences), AssistantTurn.assistant_sequence_no.in_(sequences)),
        )).all()
        for turn in turns:
            for sequence in (turn.user_sequence_no, turn.assistant_sequence_no):
                if sequence is not None:
                    if sequence in metadata:
                        raise ValueError("Overlapping turn message links")
                    metadata[sequence] = _metadata(turn)
    return MessagePageDto(
        items=[_message_dto(message, metadata.get(message.sequence_no)) for message in messages],
        total=total, offset=pagination.offset, limit=pagination.limit,
    )
