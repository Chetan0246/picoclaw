import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "picoclaw.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    channel_type = Column(String, nullable=False) # e.g., 'slack', 'discord', 'telegram'
    external_chat_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    current_cwd = Column(String, default=".")
    env_json = Column(Text, default="{}")

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    facts = relationship("ConversationFact", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False) # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

class ConversationFact(Base):
    __tablename__ = "conversation_facts"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="facts")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper functions for message persistence
def get_or_create_conversation(db, channel_type: str, external_chat_id: str) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.external_chat_id == external_chat_id).first()
    if not conv:
        conv = Conversation(channel_type=channel_type, external_chat_id=external_chat_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv

def save_message(db, conversation_id: int, role: str, content: str) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def get_history(db, conversation_id: int, limit: int = 10):
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
        .all()
    )[::-1] # Reverse to get chronological order
