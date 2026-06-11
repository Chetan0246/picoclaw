import os
import re
import httpx
from typing import List, Dict, Any, Tuple
from app.tools import TOOL_REGISTRY

# Configure local LLM endpoint (defaulting to local llama.cpp / Ollama)
LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:8080/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "lfm-2.5-8b")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "no-key-required")

SYSTEM_PROMPT = """You are PicoClaw, an autonomous, lightweight developer assistant.
You help developers edit files, run commands, and debug code.
You interact with the workspace using XML tags representing tool calls.

Available tools:
1. List files/folders in a directory:
   <tool:list_dir path="relative_path" />
2. Read a file's lines (use to save token context):
   <tool:read_file path="relative_path" start="1" end="200" />
3. Write or overwrite a file:
   <tool:write_file path="relative_path">
   file_content_here
   </tool:write_file>
4. Execute a bash/cmd command (CD & exports are stateful and persist across turns!):
   <tool:execute_command command="command_string" />
5. Search recursively for text in files:
   <tool:grep_search query="search_string" path="relative_path" />
6. Find files by glob pattern recursively (e.g. *.js):
   <tool:find_files pattern="glob_pattern" path="relative_path" />
7. Fetch and read web documentation / API refs:
   <tool:fetch_webpage url="https://example.com" />
8. Get metadata about a file (size, line count, modified time):
   <tool:file_info path="relative_path" />
9. Create a new directory and any parents:
   <tool:make_directory path="relative_path" />
10. Delete a file:
    <tool:delete_file path="relative_path" />
11. Move or rename a file or directory:
    <tool:move_file source="relative_path" destination="relative_path" />
12. View current git diff/changes:
    <tool:git_diff />
13. Search the web for info, docs, and code:
    <tool:web_search query="search_query" />
14. Save a fact or skill into persistent memory (Hermes closed-loop learning):
    <tool:remember_fact key="key_name" value="fact_value" />
15. Search persistent memory facts:
    <tool:recall_facts query="search_query" />

CRITICAL GUIDELINES:
- Output ONLY ONE tool call per response turn.
- If you call a tool, stop writing further text. The system will run the tool and supply the result.
- Always use relative paths starting from the current directory.
- Never wrap tool tags in markdown block code fences like ```xml. Write them as raw text.
- If you have finished the task, explain your results to the user without calling any tools.
"""

def parse_tool_call(text: str) -> Tuple[str, Dict[str, Any]]:
    """Robust regex parser for PicoClaw XML tool syntax."""
    # 1. Parse block tool call (e.g. write_file)
    write_match = re.search(
        r'<tool:write_file\s+path="([^"]+)"\s*>(.*?)</tool:write_file>', 
        text, 
        re.DOTALL
    )
    if write_match:
        return "write_file", {"path": write_match.group(1), "content": write_match.group(2)}

    # 2. Parse self-closing tool calls (e.g. execute_command, read_file, list_dir, git_diff)
    # Allows for zero or more attributes before the slash
    self_closing_match = re.search(r'<tool:(\w+)(?:\s+([^>]*?))?\s*/>', text)
    if self_closing_match:
        tool_name = self_closing_match.group(1)
        attr_str = self_closing_match.group(2)
        
        attrs = {}
        if attr_str:
            # Parse attributes (key="value")
            for attr_match in re.finditer(r'(\w+)="([^"]*)"', attr_str):
                key = attr_match.group(1)
                val = attr_match.group(2)
                # Convert numeric arguments if applicable
                if val.isdigit():
                    attrs[key] = int(val)
                else:
                    attrs[key] = val
        return tool_name, attrs

    return None, None

async def query_llm(messages: List[Dict[str, str]]) -> str:
    """Asynchronously calls local llama.cpp / OpenAI-compatible endpoint."""
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.2, # Low temperature for reliable tool calling
        "max_tokens": 1024
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(LLM_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"Error connecting to local LLM: {str(e)}"

async def execute_agent_loop(
    messages: List[Dict[str, str]], 
    on_step_callback=None,
    max_steps: int = 8,
    conversation_id: int = None
) -> List[Dict[str, str]]:
    """Runs the tool-calling loop. Executes tools and returns the complete conversation run."""
    run_history = list(messages)
    
    for step in range(max_steps):
        # Query LLM for the next action
        response = await query_llm(run_history)
        
        # Add assistant message to history
        run_history.append({"role": "assistant", "content": response})
        
        # Fire callback to show progress in UI/Chat channels
        if on_step_callback:
            await on_step_callback("assistant", response)
            
        # Parse for tool calls
        tool_name, tool_args = parse_tool_call(response)
        
        if not tool_name:
            # No tool call parsed -> agent has finished reasoning and answered the user
            break
            
        if tool_name not in TOOL_REGISTRY:
            tool_result = f"Error: Tool '{tool_name}' is not registered."
        else:
            # Execute the tool safely
            if on_step_callback:
                await on_step_callback("system", f"⚙️ Running tool {tool_name} with args: {tool_args}")
            try:
                tool_func = TOOL_REGISTRY[tool_name]
                
                # Dynamic injection of conversation context and parameter filtering
                import inspect
                sig = inspect.signature(tool_func)
                kwargs = {}
                for param in sig.parameters.values():
                    if param.name == "conversation_id" and conversation_id is not None:
                        kwargs["conversation_id"] = conversation_id
                    elif param.name in tool_args:
                        kwargs[param.name] = tool_args[param.name]
                        
                tool_result = tool_func(**kwargs)
            except Exception as e:
                tool_result = f"Error executing tool {tool_name}: {str(e)}"
                
        # Append tool output as system user role back to history
        system_msg = f"--- Tool Output ({tool_name}) ---\n{tool_result}"
        run_history.append({"role": "user", "content": system_msg})
        
        if on_step_callback:
            await on_step_callback("user", system_msg)
            
    return run_history
