# PicoClaw 🐾

An ultra-lightweight, zero-framework alternative to OpenClaw designed specifically for running developer agents on local **9B or Mixture-of-Experts (MoE)** models (such as `Llama-3.1-8B-Instruct`, `Qwen-2.5-Coder-7B`, or `LFM-2.5-8B-A1B`) served by `llama.cpp` or `Ollama`.

## Why PicoClaw?

Standard agent frameworks (like LangChain, CrewAI, or Agno) fail when paired with local 9B models because they inject bloated system prompts, complex nested JSON tools, and verbose schemas. This causes local models to hallucinate arguments, fail parsing, or run slowly due to context size.

PicoClaw solves this by using:
1. **XML-Based Tool Calling:** XML tags (e.g. `<tool:read_file path="..." />`) are parsed with regex. Local 9B models output XML tags reliably, avoiding JSON syntax failures.
2. **Strict Token Budgeting:** Features line-range reading (`read_file` line slices) and sliding conversation history stored in a local SQLite database to prevent context window bloat.
3. **Zero Framework Dependencies:** Written in pure, dependency-free Python using only **FastAPI** (server), **SQLite** (storage), and **HTTPX** (async communication).
4. **Asynchronous Webhook Worker:** Fast response times (< 3 seconds) for Slack and Discord by dispatching execution to FastAPI's background tasks and streaming intermediate progress/output.

---

## Architecture

```
User/Chat App  ───> FastAPI (Webhooks) ───> background task
                                                 │
                                                 ▼
Llama.cpp/Ollama <─── HTTPX Client <──── Agent Loop (XML Parser)
                                                 │
                                                 ▼
Workspace Files  <─── Local Tools <──────────────┘
```

---

## Project Structure

```text
picoclaw/
├── app/
│   ├── main.py          # FastAPI Gateway (Slack, Discord, JSON endpoints)
│   ├── database.py      # SQLite models and session logger
│   ├── agent.py         # Prompt engineering, LLM connector, XML tag parser
│   ├── tools.py         # File operations & terminal executor (traversal safe)
│   └── worker.py        # Asynchronous background loop and Slack callbacks
├── Dockerfile           # Environment packaging for command isolation
├── requirements.txt     # Python requirements
└── README.md
```

---

## Available Tools

PicoClaw provides a suite of 15 lightweight, modern developer tools:

1. **File Operations:**
   - `<tool:list_dir path="relative_path" />` - Lists directory files/folders.
   - `<tool:read_file path="relative_path" start="1" end="200" />` - Reads a range of file lines (saves context tokens).
   - `<tool:write_file path="relative_path">content</tool:write_file>` - Writes/overwrites file content.
   - `<tool:file_info path="relative_path" />` - Retrieves metadata (size, line count, modified time) about a file.
   - `<tool:make_directory path="relative_path" />` - Creates a new directory (and any parent folders).
   - `<tool:delete_file path="relative_path" />` - Safely deletes a file from the workspace.
   - `<tool:move_file source="relative_path" destination="relative_path" />` - Moves or renames files/directories.
2. **Terminal & Git (Stateful):**
   - `<tool:execute_command command="command" />` - Runs terminal commands (directory changes via `cd` and exports are persistent across turns!).
   - `<tool:git_diff />` - Runs git diff to inspect local changes made so far.
3. **Search & RAG:**
   - `<tool:grep_search query="search_string" path="relative_path" />` - Recursively searches for text/code patterns inside files (like `ripgrep`).
   - `<tool:find_files pattern="glob_pattern" path="relative_path" />` - Recursively locates files matching glob patterns (e.g. `*.py`).
   - `<tool:web_search query="query" />` - Searches the web using DuckDuckGo Lite without requiring API keys.
4. **Persistent Memory & Web Browser:**
   - `<tool:fetch_webpage url="https://example.com" />` - Downloads clean text content from web docs/API references.
   - `<tool:remember_fact key="key" value="value" />` - Saves project facts, setup instructions, or environment keys in the conversation memory.
   - `<tool:recall_facts query="query" />` - Recalls facts stored in memory matching the search query.

---

## Getting Started

### Fedora Linux Prerequisites
To install the required systems on **Fedora Linux**, run:
```bash
sudo dnf install -y git python3 python3-pip sqlite
```

### 1. Start Your Local LLM server
Run your local model using `llama.cpp` or `Ollama`.

For `llama.cpp`:
```bash
./llama-server -m models/lfm-2.5-8b-a1b.Q4_K_M.gguf -c 8192 --port 8080
```

For `Ollama` (ensure standard compatibility port is open):
```bash
ollama run qwen2.5-coder:7b
```

### 2. Configure Environment Variables
Create a `.env` file or export the following values:
```bash
# LLM Endpoint Config
export LLM_API_URL="http://localhost:8080/v1/chat/completions"
# export LLM_API_URL="http://localhost:11434/v1/chat/completions" # for Ollama
export LLM_MODEL="lfm-2.5-8b"

# Slack & Discord Webhooks (Optional for callbacks)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Root directory the agent is allowed to access
export WORKSPACE_ROOT="/path/to/your/project/workspace"
```

### 3. Run Locally
Install dependencies and launch the server:
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.1 Start Interactive CLI Chat (Offline Mode)
You don't need to keep the FastAPI server running to chat with PicoClaw on your terminal. You can run the interactive CLI directly:
```bash
# Start chat session (persists history in SQLite automatically)
python picoclaw_cli.py --session my_project_session

# Reset/clear chat history for a session on startup
python picoclaw_cli.py --session my_project_session --clear
```
### 3.2 Access the Glassmorphic Web Dashboard
Once the FastAPI server is running (`uvicorn app.main:app`), open your browser and navigate to:
`http://localhost:8000/`

From the modern dashboard, you can:
- Create and manage isolated chat sessions.
- View real-time logs of agent tool executions.
- Inspect the **Memory Vault** containing the facts PicoClaw has remembered (Hermes closed-loop learning).
- Clear conversation history.

### 4. Run via Docker (Recommended for Sandboxing)
Running terminal commands locally poses security risks. It is best to run PicoClaw inside a Docker container:
```bash
# Build the image
docker build -t picoclaw .

# Run the container (mounting the target codebase to /workspace)
docker run -d \
  -p 8000:8000 \
  -v /path/to/your/target/codebase:/workspace \
  -e LLM_API_URL=http://host.docker.internal:8080/v1/chat/completions \
  picoclaw
```

---

## API & Webhooks Usage

### Trigger Chat Session (Async Generic API)
Post a prompt to execute:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": "session_123",
    "message": "Create a python script named hello.py that prints hello world, and run it.",
    "channel_type": "web"
  }'
```

### Fetch Chat logs & Tool Output history
```bash
curl http://localhost:8000/api/chat/session_123/history
```

### Setup Slack Slash Command
Point your Slack slash command webhook configuration (e.g., `/picoclaw`) to:
`http://<your-server-ip>:8000/webhooks/slack`
PicoClaw will receive commands, immediately reply to Slack to avoid timeouts, execute tools asynchronously in the background, and output step-by-step progress and final code outputs to the channel.
