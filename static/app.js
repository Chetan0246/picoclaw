// Client-side Session State Management
let activeSessionId = localStorage.getItem("picoclaw_active_session") || "cli_default_session";
let sessions = JSON.parse(localStorage.getItem("picoclaw_sessions")) || ["cli_default_session"];

// DOM elements
const sessionList = document.getElementById("session-list");
const memoryList = document.getElementById("memory-list");
const messagesContainer = document.getElementById("messages-container");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const activeSessionTitle = document.getElementById("active-session-title");
const agentStatus = document.getElementById("agent-status");
const newSessionBtn = document.getElementById("new-session-btn");
const clearHistoryBtn = document.getElementById("clear-history-btn");

// Init App
document.addEventListener("DOMContentLoaded", () => {
    saveSessions();
    renderSessions();
    switchSession(activeSessionId);
    
    // Poll chat history and facts periodically to fetch updates in real-time
    setInterval(pollSessionUpdates, 3000);
});

// Save sessions helper
function saveSessions() {
    localStorage.setItem("picoclaw_sessions", JSON.stringify(sessions));
    localStorage.setItem("picoclaw_active_session", activeSessionId);
}

// Render sessions sidebar
function renderSessions() {
    sessionList.innerHTML = "";
    sessions.forEach(session => {
        const item = document.createElement("div");
        item.className = `session-item ${session === activeSessionId ? 'active' : ''}`;
        item.textContent = session;
        item.title = session;
        item.addEventListener("click", () => switchSession(session));
        sessionList.appendChild(item);
    });
}

// Switch Active Session
function switchSession(sessionId) {
    activeSessionId = sessionId;
    activeSessionTitle.textContent = sessionId;
    saveSessions();
    renderSessions();
    
    // Reset view and load data
    messagesContainer.innerHTML = `<div class="welcome-card glass">
        <h3>Loading history for ${sessionId}...</h3>
    </div>`;
    
    fetchChatHistory(sessionId);
    fetchMemoryVault(sessionId);
}

// Create New Session
newSessionBtn.addEventListener("click", () => {
    const name = prompt("Enter new session name:", `session_${Date.now().toString().slice(-4)}`);
    if (name && name.trim()) {
        const cleanName = name.trim().replace(/\s+/g, "_");
        if (!sessions.includes(cleanName)) {
            sessions.push(cleanName);
        }
        switchSession(cleanName);
    }
});

// Fetch History from API
async function fetchChatHistory(sessionId) {
    try {
        const res = await fetch(`/api/chat/${sessionId}/history`);
        if (!res.ok) throw new Error("Failed to load history");
        const messages = await res.json();
        
        renderMessages(messages);
    } catch (e) {
        console.error("Error loading chat history:", e);
    }
}

// Fetch Memory/Facts from API
async function fetchMemoryVault(sessionId) {
    try {
        const res = await fetch(`/api/chat/${sessionId}/facts`);
        if (!res.ok) throw new Error("Failed to load memory vault");
        const facts = await res.json();
        
        renderMemory(facts);
    } catch (e) {
        console.error("Error loading memory:", e);
    }
}

// Render Messages bubbles
function renderMessages(messages) {
    if (messages.length === 0) {
        messagesContainer.innerHTML = `<div class="welcome-card glass">
            <h3>Start Chatting with PicoClaw</h3>
            <p>Type a instruction below to execute terminal commands, manage files, or search the web.</p>
        </div>`;
        return;
    }
    
    messagesContainer.innerHTML = "";
    messages.forEach(msg => {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message message-${msg.role}`;
        
        const header = document.createElement("div");
        header.className = "msg-header";
        const date = new Date(msg.timestamp);
        header.textContent = msg.role === "user" ? `You • ${date.toLocaleTimeString()}` : `PicoClaw • ${date.toLocaleTimeString()}`;
        
        // Check if message is a tool output structure
        if (msg.role === "user" && msg.content.startsWith("--- Tool Output")) {
            msgDiv.className = "message message-system";
            header.textContent = `⚙️ Tool Output • ${date.toLocaleTimeString()}`;
        }
        
        const bubble = document.createElement("div");
        bubble.className = "bubble";
        bubble.textContent = msg.content;
        
        msgDiv.appendChild(header);
        msgDiv.appendChild(bubble);
        messagesContainer.appendChild(msgDiv);
    });
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Render Memory Vault list
function renderMemory(facts) {
    memoryList.innerHTML = "";
    if (facts.length === 0) {
        memoryList.innerHTML = `<div class="fact-card" style="color:var(--text-muted); text-align:center;">
            Memory vault is currently empty. Ask the agent to remember facts or settings.
        </div>`;
        return;
    }
    
    facts.forEach(fact => {
        const card = document.createElement("div");
        card.className = "fact-card";
        card.innerHTML = `<strong>${fact.key}</strong>${fact.value}`;
        memoryList.appendChild(card);
    });
}

// Send Message handler
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt) return;
    
    chatInput.value = "";
    agentStatus.className = "status-badge status-running";
    agentStatus.textContent = "Running";
    
    // Optimistically render user message
    const tempMsg = {
        role: "user",
        content: prompt,
        timestamp: new Date().toISOString()
    };
    
    // Add message
    const msgDiv = document.createElement("div");
    msgDiv.className = "message message-user";
    const header = document.createElement("div");
    header.className = "msg-header";
    header.textContent = `You • ${new Date().toLocaleTimeString()}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = prompt;
    msgDiv.appendChild(header);
    msgDiv.appendChild(bubble);
    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                chat_id: activeSessionId,
                message: prompt,
                channel_type: "web"
            })
        });
        
        if (!res.ok) throw new Error("Network call failed");
        
        // Wait for agent execution. Polling will handle drawing updates.
    } catch (err) {
        console.error("Error sending query:", err);
        agentStatus.className = "status-badge status-idle";
        agentStatus.textContent = "Error";
    }
});

// Clear history action
clearHistoryBtn.addEventListener("click", async () => {
    if (!confirm(`Are you sure you want to clear chat and memories for session ${activeSessionId}?`)) return;
    
    try {
        // Since we don't have a direct REST delete endpoint, we can invoke it via a mock chat text trigger
        // or add an endpoint. Let's just invoke direct JSON payload clear trigger if we add it.
        // To keep it simple, let's call the API to delete session history if we add a DELETE endpoint.
        // We'll write the delete handler in app/main.py!
        const res = await fetch(`/api/chat/${activeSessionId}/clear`, { method: "POST" });
        if (res.ok) {
            switchSession(activeSessionId);
        }
    } catch (e) {
        console.error("Failed to clear history:", e);
    }
});

// Poll session state updates
let isRunning = false;
async function pollSessionUpdates() {
    try {
        const res = await fetch(`/api/chat/${activeSessionId}/history`);
        if (!res.ok) return;
        const messages = await res.json();
        
        // Simple logic to detect if agent is running:
        // If the last message is a user prompt (and not assistant reply or tool output), it's probably running!
        if (messages.length > 0) {
            const lastMsg = messages[messages.length - 1];
            // If last message is User prompt, or system run indicator, agent is likely running
            if (lastMsg.role === "user" && !lastMsg.content.startsWith("--- Tool Output")) {
                isRunning = true;
                agentStatus.className = "status-badge status-running";
                agentStatus.textContent = "Running";
            } else {
                isRunning = false;
                agentStatus.className = "status-badge status-idle";
                agentStatus.textContent = "Idle";
            }
        } else {
            agentStatus.className = "status-badge status-idle";
            agentStatus.textContent = "Idle";
        }
        
        renderMessages(messages);
        fetchMemoryVault(activeSessionId);
    } catch (e) {
        console.error("Polling error:", e);
    }
}
