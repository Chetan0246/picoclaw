import os
import subprocess
import shlex
import fnmatch
import re
import html
import urllib.request
import urllib.parse
import shutil
import json
from datetime import datetime
from typing import Dict, Any
from app.database import SessionLocal, Conversation, ConversationFact

# Root workspace directory to avoid directory traversal escape
WORKSPACE_ROOT = os.path.abspath(os.environ.get("WORKSPACE_ROOT", os.getcwd()))

def safe_path(relative_path: str) -> str:
    """Resolve and check path safety, preventing traversal outside workspace root."""
    full_path = os.path.abspath(os.path.join(WORKSPACE_ROOT, relative_path))
    # Ensure it matches the prefix and has a directory separator if it's a child
    prefix = WORKSPACE_ROOT if WORKSPACE_ROOT.endswith(os.path.sep) else WORKSPACE_ROOT + os.path.sep
    if full_path != WORKSPACE_ROOT and not full_path.startswith(prefix):
        raise ValueError(f"Access denied: Path '{relative_path}' lies outside the workspace root.")
    return full_path

def list_dir(path: str = ".") -> str:
    """Lists files and folders in a relative path."""
    try:
        target = safe_path(path)
        if not os.path.exists(target):
            return f"Error: Path '{path}' does not exist."
        items = os.listdir(target)
        result = []
        for item in items:
            full_item = os.path.join(target, item)
            is_dir = "DIR" if os.path.isdir(full_item) else "FILE"
            size = f"{os.path.getsize(full_item)}B" if not os.path.isdir(full_item) else ""
            result.append(f"[{is_dir}] {item} {size}".strip())
        return "\n".join(result) if result else "Directory is empty."
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def read_file(path: str, start: int = 1, end: int = 200) -> str:
    """Reads lines from a file (1-indexed, inclusive). Saves context tokens."""
    try:
        target = safe_path(path)
        if not os.path.exists(target):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target):
            return f"Error: Path '{path}' is a directory, not a file."
        
        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start = max(1, start)
        end = min(total_lines, end)
        
        if start > total_lines:
            return f"Error: Start line {start} exceeds total file lines ({total_lines})."
            
        sliced = lines[start-1:end]
        header = f"--- Reading {path} (Lines {start}-{end} of {total_lines}) ---\n"
        return header + "".join(sliced)
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with content."""
    try:
        target = safe_path(path)
        # Ensure directories exist
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File '{path}' written successfully ({len(content)} chars)."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def execute_command(command: str, conversation_id: int = None) -> str:
    """Executes a bash/cmd command inside the context-cwd and environment of the conversation session."""
    try:
        cwd = WORKSPACE_ROOT
        env = os.environ.copy()
        
        db = None
        conv = None
        if conversation_id is not None:
            db = SessionLocal()
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                if conv.current_cwd and conv.current_cwd != ".":
                    cwd = safe_path(conv.current_cwd)
                if conv.env_json:
                    try:
                        stored_envs = json.loads(conv.env_json)
                        env.update(stored_envs)
                    except Exception:
                        pass

        # Handle 'cd' directory changes (supporting chained commands like cd folder && command)
        cmd_stripped = command.strip()
        if cmd_stripped.startswith("cd"):
            parts = re.split(r'\s*(?:&&|;|\|\|)\s*', cmd_stripped, maxsplit=1)
            cd_part = parts[0].strip()
            remaining_cmd = parts[1].strip() if len(parts) > 1 else None
            
            cd_cmd_parts = shlex.split(cd_part)
            if len(cd_cmd_parts) < 2:
                target_dir = WORKSPACE_ROOT
            else:
                target_dir = os.path.abspath(os.path.join(cwd, cd_cmd_parts[1]))
                if not target_dir.startswith(WORKSPACE_ROOT):
                    if db:
                        db.close()
                    return f"Error: Access denied: Path '{cd_cmd_parts[1]}' lies outside the workspace root."
            
            new_rel_cwd = os.path.relpath(target_dir, WORKSPACE_ROOT)
            if db and conv:
                conv.current_cwd = new_rel_cwd
                db.commit()
            
            # Update cwd for the remaining command in this subprocess run
            cwd = target_dir
            
            if not remaining_cmd:
                if db:
                    db.close()
                return f"Success: Changed directory to '{new_rel_cwd}'"
            else:
                # Replace command with the remaining part to execute inside the new folder
                command = remaining_cmd

        # Handle environment variables set via 'export'
        cmd_parts = shlex.split(command)
        if cmd_parts and cmd_parts[0] == "export" and len(cmd_parts) > 1:
            var_part = cmd_parts[1]
            if "=" in var_part:
                key, val = var_part.split("=", 1)
                key = key.strip()
                val = val.strip()
                if db and conv:
                    stored_envs = json.loads(conv.env_json) if conv.env_json else {}
                    stored_envs[key] = val
                    conv.env_json = json.dumps(stored_envs)
                    db.commit()
                if db:
                    db.close()
                return f"Success: Environment variable '{key}' set to '{val}'"

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if db:
            db.close()

        output = ""
        if result.stdout:
            output += f"--- STDOUT ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- STDERR ---\n{result.stderr}\n"
        if not output:
            output = "Command executed successfully with no output."
        return f"Exit Code: {result.returncode}\n{output}"
        
    except subprocess.TimeoutExpired:
        if db:
            db.close()
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        if db:
            db.close()
        return f"Error executing command: {str(e)}"

def grep_search(query: str, path: str = ".") -> str:
    """Recursively searches for query text inside files in a relative path."""
    try:
        target = safe_path(path)
        results = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_idx, line in enumerate(f, 1):
                            if query.lower() in line.lower():
                                relative_file = os.path.relpath(file_path, WORKSPACE_ROOT)
                                results.append(f"{relative_file}:{line_idx}: {line.strip()}")
                except Exception:
                    continue
        if not results:
            return f"No matches found for query: '{query}' under '{path}'."
        limited = results[:100]
        header = f"--- Grep Search Results for '{query}' (Found {len(results)} matches) ---\n"
        output = "\n".join(limited)
        if len(results) > 100:
            output += "\n...[output truncated due to match limits]..."
        return header + output
    except Exception as e:
        return f"Error executing grep: {str(e)}"

def find_files(pattern: str, path: str = ".") -> str:
    """Finds files matching a glob pattern (e.g. '*.py') recursively in a relative path."""
    try:
        target = safe_path(path)
        results = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if fnmatch.fnmatch(file, pattern):
                    file_path = os.path.join(root, file)
                    relative_file = os.path.relpath(file_path, WORKSPACE_ROOT)
                    results.append(relative_file)
        if not results:
            return f"No files found matching pattern '{pattern}' under '{path}'."
        return "\n".join(results)
    except Exception as e:
        return f"Error finding files: {str(e)}"

def fetch_webpage(url: str) -> str:
    """Fetches a URL and extracts clean text (useful for reading online docs)."""
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (PicoClaw Agent)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            
        text = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL)
        text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        
        lines = [line.strip() for line in text.split('\n')]
        clean_lines = [line for line in lines if line]
        clean_text = "\n".join(clean_lines)
        
        if len(clean_text) > 3000:
            return clean_text[:3000] + "\n...[webpage content truncated to save tokens]..."
        return clean_text
    except Exception as e:
        return f"Error fetching url '{url}': {str(e)}"

def file_info(path: str) -> str:
    """Returns metadata about a file (size, line count, modified time)."""
    try:
        target = safe_path(path)
        if not os.path.exists(target):
            return f"Error: Path '{path}' does not exist."
            
        is_dir = os.path.isdir(target)
        size = os.path.getsize(target)
        mtime = datetime.fromtimestamp(os.path.getmtime(target)).strftime('%Y-%m-%d %H:%M:%S')
        
        info = [
            f"Path: {path}",
            f"Type: {'Directory' if is_dir else 'File'}",
            f"Size: {size} bytes",
            f"Last Modified: {mtime}"
        ]
        
        if not is_dir:
            try:
                with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f)
                info.append(f"Line Count: {line_count}")
            except Exception:
                pass
                
        return "\n".join(info)
    except Exception as e:
        return f"Error getting file info: {str(e)}"

def make_directory(path: str) -> str:
    """Creates a new directory (and any parent directories) inside the workspace."""
    try:
        target = safe_path(path)
        os.makedirs(target, exist_ok=True)
        return f"Success: Directory '{path}' created."
    except Exception as e:
        return f"Error creating directory: {str(e)}"

def delete_file(path: str) -> str:
    """Deletes a file from the workspace."""
    try:
        target = safe_path(path)
        if not os.path.exists(target):
            return f"Error: Path '{path}' does not exist."
        if os.path.isdir(target):
            return f"Error: '{path}' is a directory. Use execute_command to delete directories."
        os.remove(target)
        return f"Success: File '{path}' deleted."
    except Exception as e:
        return f"Error deleting file: {str(e)}"

def move_file(source: str, destination: str) -> str:
    """Moves or renames a file/directory inside the workspace."""
    try:
        src = safe_path(source)
        dest = safe_path(destination)
        if not os.path.exists(src):
            return f"Error: Source '{source}' does not exist."
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        return f"Success: Moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving file: {str(e)}"

def git_diff() -> str:
    """Runs git diff to inspect code modifications made so far."""
    try:
        check_git = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True
        )
        if check_git.returncode != 0:
            return "Error: Workspace is not inside a git repository."
        result = subprocess.run(
            ["git", "diff"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode != 0:
            return f"Error running git diff: {result.stderr}"
        return result.stdout if result.stdout else "No changes detected (clean working tree)."
    except Exception as e:
        return f"Error running git diff: {str(e)}"

def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo Lite and returns top results with snippets."""
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html_content = response.read().decode("utf-8", errors="ignore")
            
        results = []
        matches = re.findall(r'(<a[^>]+class=[\'"]result-link[\'"][^>]*>.*?</a>)', html_content, re.DOTALL)
        snippet_matches = re.findall(r'<td[^>]*class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', html_content, re.DOTALL)
        
        for idx, match in enumerate(matches[:5]):
            href_m = re.search(r'href=[\'"]([^\'"]+)[\'"]', match)
            link = href_m.group(1) if href_m else ""
            
            title_m = re.search(r'>(.*?)</a>', match, re.DOTALL)
            title = title_m.group(1) if title_m else "No Title"
            title = re.sub(r'<[^>]+>', '', title).strip()
            
            snippet = "No snippet available."
            if idx < len(snippet_matches):
                snippet = re.sub(r'<[^>]+>', '', snippet_matches[idx]).strip()
                snippet = html.unescape(snippet)
            
            title = html.unescape(title)
            parsed_link = urllib.parse.urlparse(link)
            if parsed_link.path == "/l/":
                query_params = urllib.parse.parse_qs(parsed_link.query)
                if "uddg" in query_params:
                    link = query_params["uddg"][0]
                    
            results.append(f"[{idx+1}] {title}\nURL: {link}\nSnippet: {snippet}\n")
            
        if not results:
            return "No web search results found."
        return "\n".join(results)
    except Exception as e:
        return f"Error executing web search: {str(e)}"

def remember_fact(key: str, value: str, conversation_id: int = None) -> str:
    """Saves a key-value fact into the persistent memory for this conversation (Hermes closed-loop learning)."""
    if conversation_id is None:
        return "Error: conversation_id context is missing."
    db = SessionLocal()
    try:
        fact = db.query(ConversationFact).filter(
            ConversationFact.conversation_id == conversation_id,
            ConversationFact.key == key
        ).first()
        if fact:
            fact.value = value
            action = "Updated"
        else:
            fact = ConversationFact(conversation_id=conversation_id, key=key, value=value)
            db.add(fact)
            action = "Remembered"
        db.commit()
        return f"Success: {action} fact '{key}' -> '{value}'."
    except Exception as e:
        return f"Error remembering fact: {str(e)}"
    finally:
        db.close()

def recall_facts(query: str, conversation_id: int = None) -> str:
    """Searches the persistent memory facts for this conversation."""
    if conversation_id is None:
        return "Error: conversation_id context is missing."
    db = SessionLocal()
    try:
        facts = db.query(ConversationFact).filter(
            ConversationFact.conversation_id == conversation_id
        ).all()
        
        matches = []
        for fact in facts:
            if query.lower() in fact.key.lower() or query.lower() in fact.value.lower():
                matches.append(f"Fact '{fact.key}': {fact.value}")
                
        if not matches:
            return f"No facts found matching query '{query}'."
        return "\n".join(matches)
    except Exception as e:
        return f"Error recalling facts: {str(e)}"
    finally:
        db.close()

# Registry of tools for easy lookup
TOOL_REGISTRY = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "execute_command": execute_command,
    "grep_search": grep_search,
    "find_files": find_files,
    "fetch_webpage": fetch_webpage,
    "file_info": file_info,
    "make_directory": make_directory,
    "delete_file": delete_file,
    "move_file": move_file,
    "git_diff": git_diff,
    "web_search": web_search,
    "remember_fact": remember_fact,
    "recall_facts": recall_facts
}
