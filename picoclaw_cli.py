import os
import sys
import asyncio
import argparse
import uuid

# Add parent directory to sys.path if running directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db, SessionLocal, get_or_create_conversation, save_message, get_history
from app.agent import execute_agent_loop

# ANSI Terminal colors
COLOR_RESET = "\033[0m"
COLOR_USER = "\033[94m"      # Blue
COLOR_AGENT = "\033[92m"     # Green
COLOR_TOOL = "\033[93m"      # Yellow
COLOR_SYSTEM = "\033[96m"    # Cyan
COLOR_ERROR = "\033[91m"     # Red
COLOR_HEADER = "\033[95m"    # Magenta

def print_header(session_id: str):
    print(f"{COLOR_HEADER}==================================================")
    print("                PicoClaw CLI Assistant             ")
    print("==================================================")
    print(f"Session ID : {session_id}")
    print(f"Workspace  : {os.path.abspath(os.environ.get('WORKSPACE_ROOT', os.getcwd()))}")
    print("Commands   : type 'exit' or 'quit' to close session.")
    print("             type 'clear' to reset history.")
    print(f"=================================================={COLOR_RESET}\n")

async def step_callback(role: str, content: str):
    """Processes intermediate tool calls and outputs to print to stdout in real-time."""
    if role == "assistant":
        if "<tool:" in content:
            # Extract tag for clean display
            print(f"\n{COLOR_TOOL}[PicoClaw Tool Action]{COLOR_RESET} {content.strip()}")
        else:
            # Print direct thoughts or explanation
            print(f"\n{COLOR_AGENT}[PicoClaw]{COLOR_RESET} {content.strip()}")
    elif role == "user" and "--- Tool Output" in content:
        # Format tool results
        lines = content.split("\n")
        header = lines[0]
        body = "\n".join(lines[1:])
        # Truncate output preview if too long
        if len(body) > 400:
            body = body[:400] + "\n...[output truncated for display]..."
        print(f"\n{COLOR_SYSTEM}[System Tool Output] ({header}){COLOR_RESET}\n{body}")
    elif role == "system" and "Running tool" in content:
        print(f"{COLOR_SYSTEM}[Execution]{COLOR_RESET} {content}")

async def main_loop(session_id: str, clear_history: bool):
    # 1. Initialize SQLite Database
    init_db()
    db = SessionLocal()
    
    try:
        conv = get_or_create_conversation(db, "cli", session_id)
        
        if clear_history:
            # Delete old messages in this conversation
            from app.database import Message, ConversationFact
            db.query(ConversationFact).filter(ConversationFact.conversation_id == conv.id).delete()
            db.query(Message).filter(Message.conversation_id == conv.id).delete()
            db.commit()
            print(f"{COLOR_SYSTEM}Cleared history for session {session_id}.{COLOR_RESET}")
            
        print_header(session_id)
        
        # Load and print previous history
        history = get_history(db, conv.id, limit=30)
        if history:
            print(f"{COLOR_SYSTEM}--- Restoring Chat History ({len(history)} messages) ---{COLOR_RESET}")
            for msg in history:
                if msg.role == "user" and "--- Tool Output" in msg.content:
                    continue # Skip raw tool outputs in history restore
                role_color = COLOR_USER if msg.role == "user" else COLOR_AGENT
                role_name = "You" if msg.role == "user" else "PicoClaw"
                print(f"{role_color}[{role_name}]{COLOR_RESET} {msg.content}")
            print(f"{COLOR_SYSTEM}-----------------------------------------------------{COLOR_RESET}\n")

        # 2. Main Prompt loop
        while True:
            try:
                user_input = input(f"{COLOR_USER}You: {COLOR_RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{COLOR_SYSTEM}Goodbye!{COLOR_RESET}")
                break
                
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit"]:
                print(f"{COLOR_SYSTEM}Exiting session. Goodbye!{COLOR_RESET}")
                break
                
            if user_input.lower() == "clear":
                # Clear session db entries
                from app.database import Message, ConversationFact
                db.query(Message).filter(Message.conversation_id == conv.id).delete()
                db.query(ConversationFact).filter(ConversationFact.conversation_id == conv.id).delete()
                db.commit()
                print(f"\n{COLOR_SYSTEM}History cleared.{COLOR_RESET}\n")
                continue

            # Save user input to DB
            save_message(db, conv.id, "user", user_input)
            
            # Retrieve updated history payload to feed the LLM
            history_objs = get_history(db, conv.id, limit=12)
            messages_payload = [{"role": m.role, "content": m.content} for m in history_objs]
            
            # Execute agent runner loop (passes conversation_id for stateful tools)
            try:
                await execute_agent_loop(
                    messages_payload,
                    on_step_callback=step_callback,
                    max_steps=10,
                    conversation_id=conv.id
                )
                print() # Print empty line after agent run
            except Exception as e:
                print(f"\n{COLOR_ERROR}[Execution Error] {str(e)}{COLOR_RESET}\n")
                
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PicoClaw CLI Chat Assistant")
    parser.add_argument(
        "--session", "-s", 
        type=str, 
        default="cli_default_session",
        help="Session ID to persist chat history and tool settings."
    )
    parser.add_argument(
        "--clear", "-c", 
        action="store_true", 
        help="Clear history for the specified session on startup."
    )
    args = parser.parse_args()
    
    # Run the async loop
    asyncio.run(main_loop(args.session, args.clear))
