import os
from fastapi import FastAPI, BackgroundTasks, Form, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import init_db, get_db, get_history, get_or_create_conversation, Message, ConversationFact
from app.worker import run_agent_background

# Initialize SQLite tables on startup
init_db()

app = FastAPI(
    title="PicoClaw",
    description="Ultra-lightweight, token-efficient developer agent gateway.",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Input schemas for generic direct chat
class ChatRequest(BaseModel):
    channel_type: str = "web"
    chat_id: str
    message: str
    callback_url: str = None

@app.get("/")
def serve_dashboard():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PicoClaw Gateway",
        "workspace_root": os.path.abspath(os.environ.get("WORKSPACE_ROOT", os.getcwd()))
    }

@app.post("/api/chat")
async def direct_chat(req: ChatRequest, background_tasks: BackgroundTasks):
    """Direct JSON API. Spawns agent in the background and returns receipt."""
    background_tasks.add_task(
        run_agent_background,
        channel_type=req.channel_type,
        external_chat_id=req.chat_id,
        user_prompt=req.message,
        callback_url=req.callback_url
    )
    return {
        "message": "Agent execution started in background.",
        "chat_id": req.chat_id,
        "channel_type": req.channel_type
    }

@app.post("/webhooks/slack")
async def slack_webhook(
    background_tasks: BackgroundTasks,
    channel_id: str = Form(...),
    text: str = Form(...),
    response_url: str = Form(...)
):
    """Slack Slash Command Webhook. Responds instantly and runs agent asynchronously."""
    # Slack requires an immediate reply (HTTP 200) within 3 seconds
    background_tasks.add_task(
        run_agent_background,
        channel_type="slack",
        external_chat_id=channel_id,
        user_prompt=text,
        callback_url=response_url
    )
    return JSONResponse(
        content={
            "response_type": "in_channel",
            "text": "🤖 *PicoClaw* has received your command and is starting work..."
        }
    )

@app.post("/webhooks/discord")
async def discord_webhook(
    req: Request,
    background_tasks: BackgroundTasks
):
    """Generic Discord interaction webhook handler."""
    # Custom parsing depending on Discord interaction body
    body = await req.json()
    chat_id = body.get("channel_id", "discord-default")
    user_message = body.get("content", "")
    
    # Check if this is a health-ping from discord
    if body.get("type") == 1:
        return {"type": 1}
        
    background_tasks.add_task(
        run_agent_background,
        channel_type="discord",
        external_chat_id=chat_id,
        user_prompt=user_message
    )
    return {"content": "🤖 *PicoClaw* is initializing task execution..."}

@app.get("/api/chat/{chat_id}/history")
def get_chat_history(chat_id: str, db: Session = Depends(get_db)):
    """API to retrieve history and debug execution logs for a session."""
    conv = get_or_create_conversation(db, "api", chat_id)
    history = get_history(db, conv.id, limit=50)
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat()
        } for msg in history
    ]

@app.get("/api/chat/{chat_id}/facts")
def get_chat_facts(chat_id: str, db: Session = Depends(get_db)):
    """API to retrieve memory facts saved for a session."""
    conv = get_or_create_conversation(db, "api", chat_id)
    facts = db.query(ConversationFact).filter(ConversationFact.conversation_id == conv.id).all()
    return [
        {
            "id": fact.id,
            "key": fact.key,
            "value": fact.value,
            "created_at": fact.created_at.isoformat()
        } for fact in facts
    ]

@app.post("/api/chat/{chat_id}/clear")
def clear_chat_session(chat_id: str, db: Session = Depends(get_db)):
    """API to delete chat logs and persistent memories for a session."""
    conv = get_or_create_conversation(db, "api", chat_id)
    db.query(Message).filter(Message.conversation_id == conv.id).delete()
    db.query(ConversationFact).filter(ConversationFact.conversation_id == conv.id).delete()
    db.commit()
    return {"message": f"Successfully cleared session {chat_id}."}
