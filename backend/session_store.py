import asyncio
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ChatSession:
    at_session_id: str           # AgentTrust session ID
    at_credential: str           # AgentTrust registration credential for this session
    user_email: str
    user_role: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

_store: dict[str, ChatSession] = {}

def create(chat_id: str, at_session_id: str, at_credential: str,
           user_email: str, user_role: str) -> ChatSession:
    s = ChatSession(at_session_id=at_session_id, at_credential=at_credential,
                    user_email=user_email, user_role=user_role)
    _store[chat_id] = s
    return s

def get(chat_id: str) -> Optional[ChatSession]:
    return _store.get(chat_id)

def delete(chat_id: str) -> None:
    _store.pop(chat_id, None)
