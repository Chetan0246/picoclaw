import os
import httpx
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_or_create_conversation, save_message, get_history
from app.agent import execute_agent_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PicoClawWorker")

# Outgoing webhook URLs (can be loaded from env or passed dynamically)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

async def send_client_notification(channel_type: str, external_chat_id: str, text: str, callback_url: str = None):
    """Sends progress notifications back to Slack, Discord, or generic webhooks."""
    logger.info(f"[{channel_type} | {external_chat_id}] Notification: {text[:80]}...")
    
    # Priority 1: Use specific callback_url if provided by the webhook payload
    target_url = callback_url
    
    # Priority 2: Fallback to global env-configured webhooks
    if not target_url:
        if channel_type == "slack":
            target_url = SLACK_WEBHOOK_URL
        elif channel_type == "discord":
            target_url = DISCORD_WEBHOOK_URL
            
    if not target_url:
        # If no webhook is configured, just log locally
        return

    try:
        async with httpx.AsyncClient() as client:
            if "slack.com" in target_url or channel_type == "slack":
                # Slack webhook format
                payload = {"text": text}
            elif "discord.com" in target_url or channel_type == "discord":
                # Discord webhook format
                payload = {"content": text}
            else:
                # Generic JSON webhook
                payload = {"chat_id": external_chat_id, "message": text}
                
            await client.post(target_url, json=payload, timeout=10.0)
    except Exception as e:
        logger.error(f"Failed to send client notification: {str(e)}")

async def run_agent_background(
    channel_type: str, 
    external_chat_id: str, 
    user_prompt: str,
    callback_url: str = None
):
    """Executes the agent loop in the background, updating the user asynchronously."""
    db: Session = SessionLocal()
    try:
        # 1. Fetch or create conversation
        conv = get_or_create_conversation(db, channel_type, external_chat_id)
        
        # 2. Save user prompt
        save_message(db, conv.id, "user", user_prompt)
        
        # 3. Load chronological history
        messages_objs = get_history(db, conv.id, limit=12)
        messages_payload = [{"role": msg.role, "content": msg.content} for msg in messages_objs]
        
        # 4. Notify user that the agent has started working
        await send_client_notification(
            channel_type, 
            external_chat_id, 
            "🤖 *PicoClaw is analyzing your request...*", 
            callback_url
        )
        
        # Define step callback to notify users about tools being run
        async def step_callback(role: str, content: str):
            # Save step back to database for full traceability
            save_message(db, conv.id, role, content)
            
            # Format and send live updates to user
            if role == "assistant":
                # Only post tool calls or responses, trim to avoid huge messages
                if "<tool:" in content:
                    tool_desc = content.split("\n")[0] # Get first line of tool call
                    await send_client_notification(
                        channel_type, 
                        external_chat_id, 
                        f"⚙️ *Tool execution initiated:*\n`{tool_desc}`", 
                        callback_url
                    )
            elif role == "user" and "--- Tool Output" in content:
                # Truncate output to avoid flooding chat logs
                preview = content[:300] + ("\n...[output truncated]..." if len(content) > 300 else "")
                await send_client_notification(
                    channel_type, 
                    external_chat_id, 
                    f"📤 *Tool output preview:*\n```\n{preview}\n```", 
                    callback_url
                )

        # 5. Run the actual agent loop
        final_history = await execute_agent_loop(
            messages_payload, 
            on_step_callback=step_callback,
            max_steps=8,
            conversation_id=conv.id
        )
        
        # 6. Retrieve the final response (the last assistant message)
        final_response = None
        for msg in reversed(final_history):
            if msg["role"] == "assistant":
                final_response = msg["content"]
                break
                
        if final_response:
            # Post final clean answer to user channel
            await send_client_notification(
                channel_type, 
                external_chat_id, 
                final_response, 
                callback_url
            )
            
    except Exception as e:
        logger.error(f"Worker execution failed: {str(e)}")
        await send_client_notification(
            channel_type, 
            external_chat_id, 
            f"❌ *Error during execution:* {str(e)}", 
            callback_url
        )
    finally:
        db.close()
