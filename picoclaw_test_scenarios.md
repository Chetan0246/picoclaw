# PicoClaw 🐾 Test Scenarios & Playbook

Use these scenarios to test PicoClaw's XML-based tool execution loop, stateful database context tracking, and web scraping capabilities. You can run these prompts via the **Interactive CLI** or the **Glassmorphic Web Dashboard**.

---

## Scenario 1: File Creation, Inspection, & Execution
> **Goal:** Test file writing, metadata checking, and command execution.

### Prompt to Send
> "Create a Python file named `calculator.py` in the current folder. It should contain a function `is_even(n)` that returns True if a number is even, and False otherwise. After creating it, view the file details (size, line count) and execute it to test the function with the input `42`."

### Expected PicoClaw Tool Execution sequence
1. `<tool:write_file path="calculator.py">...code...</tool:write_file>`
2. `<tool:file_info path="calculator.py" />`
3. `<tool:execute_command command="python calculator.py" />`

---

## Scenario 2: Stateful Terminal Directory Tracking & Git
> **Goal:** Test PicoClaw's ability to persist directory changes (`cd`) and environment exports across message turns.

### Prompt to Send
> "Create a directory named `git_sandbox`, change directory into it, initialize a new Git repository, and run git status."

### Expected PicoClaw Tool Execution sequence
1. `<tool:make_directory path="git_sandbox" />`
2. `<tool:execute_command command="cd git_sandbox && git init" />`
3. `<tool:execute_command command="git status" />`
*(Notice that subsequent commands are run inside the `git_sandbox` directory, thanks to database state persistence!)*

---

## Scenario 3: Web Search & Regex Scraping (DuckDuckGo Lite)
> **Goal:** Test search engine query parsing and snippet extraction without keys.

### Prompt to Send
> "Search the web for the latest release version of FastAPI on PyPI and tell me the version number and the URL you found."

### Expected PicoClaw Tool Execution sequence
1. `<tool:web_search query="FastAPI latest version pypi" />`
2. Agent reads the search results, extracts the version, and returns the response to you.

---

## Scenario 4: Web Document Ingestion & Parsing
> **Goal:** Test fetching web pages, stripping HTML tags, and summarizing API docs.

### Prompt to Send
> "Fetch the page https://httpbin.org/ip, read its content, and tell me the IP address shown in the response."

### Expected PicoClaw Tool Execution sequence
1. `<tool:fetch_webpage url="https://httpbin.org/ip" />`
2. Agent parses the JSON string content and prints it for you.

---

## Scenario 5: Memory Vault (Hermes Closed-Loop Learning)
> **Goal:** Test persistent memory injection and matching.

### Prompt 1 to Send:
> "Remember that our staging database host is `staging-db.internal` and the username is `admin_user`."

### Expected PicoClaw Tool Execution sequence
1. `<tool:remember_fact key="staging_db_host" value="staging-db.internal" />`
2. `<tool:remember_fact key="staging_db_user" value="admin_user" />`

### Prompt 2 to Send (in a new turn or session):
> "Search our memory vault for the staging database credentials."

### Expected PicoClaw Tool Execution sequence
1. `<tool:recall_facts query="staging" />`

---

## Scenario 6: Codebase Grepping & Context Slicing
> **Goal:** Test recursive grep search and token-efficient file slice reading.

### Prompt to Send
> "Find where `WORKSPACE_ROOT` is defined in the workspace, and read lines 10 to 30 of that file."

### Expected PicoClaw Tool Execution sequence
1. `<tool:grep_search query="WORKSPACE_ROOT" path="." />`
2. `<tool:read_file path="app/tools.py" start="10" end="30" />`
