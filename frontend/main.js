// ——— State ———
const API = window.location.origin + '/api/v1';
let userToken = null;    // Bearer token for /auth/* endpoints
let sessionToken = null; // Bearer token for /chatbot/* endpoints
let activeSessionId = null;
let sessions = [];

// ——— API Helper ———
async function api(method, path, body = null, token = null, isForm = false) {
  const url = `${API}${path}`;
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let reqBody = null;
  if (body) {
    if (isForm) {
      reqBody = new URLSearchParams(body);
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else {
      reqBody = JSON.stringify(body);
      headers['Content-Type'] = 'application/json';
    }
  }

  logRequest(method, path, body);

  const res = await fetch(url, { method, headers, body: reqBody });
  const data = await res.json();

  if (!res.ok) {
    logError(method, path, data);
    throw new Error(data.detail || JSON.stringify(data));
  }

  logResponse(method, path, data);
  return data;
}

// ——— Auth ———
async function register() {
  const email = document.getElementById('authEmail').value;
  const password = document.getElementById('authPassword').value;
  if (!email || !password) return toast('Fill in email and password', 'error');

  try {
    const data = await api('POST', '/auth/register', { email, password });
    userToken = data.token.access_token;
    showAuthStatus(email);
    toast('Registered successfully!', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function login() {
  const email = document.getElementById('authEmail').value;
  const password = document.getElementById('authPassword').value;
  if (!email || !password) return toast('Fill in email and password', 'error');

  try {
    const data = await api('POST', '/auth/login', { username: email, password, grant_type: 'password' }, null, true);
    userToken = data.access_token;
    showAuthStatus(email);
    toast('Logged in!', 'success');
    await loadSessions();
  } catch (e) { toast(e.message, 'error'); }
}

function logout() {
  userToken = null;
  sessionToken = null;
  activeSessionId = null;
  sessions = [];
  document.getElementById('authForms').style.display = '';
  document.getElementById('authStatus').style.display = 'none';
  document.getElementById('newSessionBtn').disabled = true;
  document.getElementById('sessionList').innerHTML = '';
  document.getElementById('loadHistoryBtn').disabled = true;
  document.getElementById('clearHistoryBtn').disabled = true;
  enableChat(false);
  clearMessages();
  updateAffection(0);
  document.getElementById('affectionContainer').style.display = 'none';
  document.getElementById('chatTitle').textContent = 'Select a Session';
  document.getElementById('sessionBadge').style.display = 'none';
  toast('Logged out', 'info');
}

function showAuthStatus(email) {
  document.getElementById('authForms').style.display = 'none';
  document.getElementById('authStatus').style.display = '';
  document.getElementById('userInfo').textContent = email;
  document.getElementById('newSessionBtn').disabled = false;
}

// ——— Sessions ———
async function loadSessions() {
  try {
    const data = await api('GET', '/auth/sessions', null, userToken);
    sessions = data;
    renderSessions();
  } catch (e) { toast(e.message, 'error'); }
}

async function createSession() {
  try {
    const data = await api('POST', '/auth/session', null, userToken);
    toast('Session created!', 'success');
    await loadSessions();
    selectSession(data.session_id, data.token.access_token, data.name);
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteSession(sessionId, token) {
  try {
    await api('DELETE', `/auth/session/${sessionId}`, null, token);
    toast('Session deleted', 'info');
    if (activeSessionId === sessionId) {
      sessionToken = null;
      activeSessionId = null;
      enableChat(false);
      clearMessages();
      document.getElementById('chatTitle').textContent = 'Select a Session';
      document.getElementById('sessionBadge').style.display = 'none';
      document.getElementById('affectionContainer').style.display = 'none';
    }
    await loadSessions();
  } catch (e) { toast(e.message, 'error'); }
}

function selectSession(id, token, name) {
  activeSessionId = id;
  sessionToken = token;
  enableChat(true);
  clearMessages();
  document.getElementById('chatTitle').textContent = name || `Session ${id.substring(0, 8)}…`;
  document.getElementById('sessionBadge').style.display = '';
  document.getElementById('sessionBadge').className = 'status-badge connected';
  document.getElementById('sessionBadgeText').textContent = 'Active';
  document.getElementById('affectionContainer').style.display = 'flex';
  document.getElementById('loadHistoryBtn').disabled = false;
  document.getElementById('clearHistoryBtn').disabled = false;
  updateAffection(0);
  renderSessions();
}

function renderSessions() {
  const list = document.getElementById('sessionList');
  list.innerHTML = '';
  sessions.forEach(s => {
    const li = document.createElement('li');
    li.className = 'session-item' + (s.session_id === activeSessionId ? ' active' : '');
    li.innerHTML = `
          <span class="session-name">${s.name || s.session_id.substring(0, 12) + '…'}</span>
          <button class="session-delete" title="Delete" onclick="event.stopPropagation(); deleteSession('${s.session_id}', '${s.token.access_token}')">×</button>
        `;
    li.onclick = () => selectSession(s.session_id, s.token.access_token, s.name);
    list.appendChild(li);
  });
}

// ——— Chat ———
function enableChat(enabled) {
  document.getElementById('messageInput').disabled = !enabled;
  document.getElementById('sendBtn').disabled = !enabled;
  if (!enabled) {
    document.getElementById('emptyState').style.display = '';
  }
}

function clearMessages() {
  const container = document.getElementById('messagesContainer');
  container.innerHTML = '<div class="empty-state" id="emptyState"><div class="emoji">💬</div><p>Start chatting!</p></div>';
}

function addMessage(role, content) {
  const emptyState = document.getElementById('emptyState');
  if (emptyState) emptyState.remove();

  const container = document.getElementById('messagesContainer');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `
        <span class="message-role">${role}</span>
        <div class="message-bubble">${escapeHtml(content)}</div>
      `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function updateLastBotMessage(content) {
  const msgs = document.querySelectorAll('.message.assistant');
  if (msgs.length === 0) return addMessage('assistant', content);
  const last = msgs[msgs.length - 1];
  last.querySelector('.message-bubble').textContent = content;
  document.getElementById('messagesContainer').scrollTop = document.getElementById('messagesContainer').scrollHeight;
}

async function sendMessage() {
  const input = document.getElementById('messageInput');
  const text = input.value.trim();
  if (!text || !sessionToken) return;

  input.value = '';
  autoResize(input);
  addMessage('user', text);

  const isStream = document.getElementById('streamToggle').checked;
  const body = { messages: [{ role: 'user', content: text }] };

  document.getElementById('sendBtn').disabled = true;
  showTyping(true);

  if (isStream) {
    await sendStream(body);
  } else {
    await sendRegular(body);
  }

  document.getElementById('sendBtn').disabled = false;
  showTyping(false);
}

async function sendRegular(body) {
  try {
    logRequest('POST', '/chatbot/chat', body);
    const res = await fetch(`${API}/chatbot/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${sessionToken}`,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    logResponse('POST', '/chatbot/chat', data);

    // Show only the latest assistant message (the new response)
    const assistantMsgs = data.messages.filter(m => m.role === 'assistant');
    if (assistantMsgs.length > 0) {
      addMessage('assistant', assistantMsgs[assistantMsgs.length - 1].content);
    }

    if (data.affection_score !== undefined) updateAffection(data.affection_score);
  } catch (e) {
    toast(e.message, 'error');
    logError('POST', '/chatbot/chat', e.message);
  }
}

async function sendStream(body) {
  try {
    logRequest('POST', '/chatbot/chat/stream (SSE)', body);
    const res = await fetch(`${API}/chatbot/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${sessionToken}`,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Stream failed');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let msgDiv = null;
    let buffer = ''; // Buffer for partial SSE lines
    let typingHidden = false; // Add flag to track the typing indicator

    // keep typing indicator on until first chunk

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // Split on double-newline (SSE event boundary) or single newlines
      const lines = buffer.split('\n');
      // Keep the last element — it may be an incomplete line
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;
        try {
          const parsed = JSON.parse(trimmed.slice(6));

          if (parsed.content) {
            if (!typingHidden) {
              showTyping(false);
              typingHidden = true;
            }
            fullText += parsed.content;
            if (!msgDiv) {
              msgDiv = addMessage('assistant', fullText);
            } else {
              msgDiv.querySelector('.message-bubble').textContent = fullText;
              document.getElementById('messagesContainer').scrollTop =
                document.getElementById('messagesContainer').scrollHeight;
            }
          }

          if (parsed.done) {
            if (parsed.affection_score !== undefined && parsed.affection_score !== null) {
              updateAffection(parsed.affection_score);
            }
            logResponse('POST', '/chatbot/chat/stream', { streamed: fullText.length + ' chars', affection_score: parsed.affection_score });
          }
        } catch { }
      }
    }

    // Process any remaining data in buffer
    if (buffer.trim().startsWith('data: ')) {
      try {
        const parsed = JSON.parse(buffer.trim().slice(6));
        if (parsed.content) {
          if (!typingHidden) {
            showTyping(false);
            typingHidden = true;
          }
          fullText += parsed.content;
          if (!msgDiv) msgDiv = addMessage('assistant', fullText);
          else msgDiv.querySelector('.message-bubble').textContent = fullText;
        }
        if (parsed.done && parsed.affection_score !== undefined && parsed.affection_score !== null) {
          updateAffection(parsed.affection_score);
        }
      } catch { }
    }

    // Hide typing indicator in case it's still visible but stream closed without returning content
    if (!typingHidden) {
      showTyping(false);
      typingHidden = true;
    }
  } catch (e) {
    toast(e.message, 'error');
    logError('POST', '/chatbot/chat/stream', e.message);
  }
}

async function loadMessages() {
  if (!sessionToken) return;
  try {
    const data = await api('GET', '/chatbot/messages', null, sessionToken);
    clearMessages();
    data.messages.forEach(m => addMessage(m.role, m.content));
    if (data.affection_score !== undefined) updateAffection(data.affection_score);
    toast('Messages loaded', 'info');
  } catch (e) { toast(e.message, 'error'); }
}

async function clearHistory() {
  if (!sessionToken) return;
  try {
    await api('DELETE', '/chatbot/messages', null, sessionToken);
    clearMessages();
    updateAffection(0);
    toast('Chat history cleared', 'info');
  } catch (e) { toast(e.message, 'error'); }
}

// ——— Affection Score ———
function updateAffection(score) {
  score = Math.max(-10, Math.min(10, score));
  const bar = document.getElementById('affectionBar');
  const label = document.getElementById('affectionLabel');
  const emoji = document.getElementById('affectionEmoji');

  // Map -10..10 to 0..100%
  const pct = ((score + 10) / 20) * 100;

  if (score < 0) {
    // red from left
    bar.style.left = pct + '%';
    bar.style.width = (50 - pct) + '%';
    bar.style.background = `linear-gradient(90deg, var(--danger), #fb7185)`;
  } else if (score > 0) {
    // pink from center
    bar.style.left = '50%';
    bar.style.width = (pct - 50) + '%';
    bar.style.background = `linear-gradient(90deg, var(--accent), #c084fc)`;
  } else {
    bar.style.left = '50%';
    bar.style.width = '0%';
  }

  label.textContent = (score > 0 ? '+' : '') + score;
  label.style.color = score < 0 ? 'var(--danger)' : score > 0 ? 'var(--accent)' : 'var(--text-muted)';

  // Pick emoji
  if (score <= -7) emoji.textContent = '😡';
  else if (score <= -4) emoji.textContent = '😤';
  else if (score <= -1) emoji.textContent = '😒';
  else if (score === 0) emoji.textContent = '😐';
  else if (score <= 3) emoji.textContent = '😊';
  else if (score <= 7) emoji.textContent = '😍';
  else emoji.textContent = '🥰';
}

// ——— Typing indicator ———
function showTyping(show) {
  document.getElementById('typingIndicator').className = 'typing-indicator' + (show ? ' visible' : '');
}

// ——— Utilities ———
function escapeHtml(str) {
  const el = document.createElement('span');
  el.textContent = str;
  return el.innerHTML;
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ——— Toast ———
function toast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3500);
}

// ——— Request Log ———
function logRequest(method, path, body) {
  appendLog(`→ ${method} ${path}` + (body ? '\n  ' + JSON.stringify(body).substring(0, 200) : ''), 'req');
}
function logResponse(method, path, data) {
  appendLog(`← ${method} ${path}\n  ${JSON.stringify(data).substring(0, 300)}`, 'res');
}
function logError(method, path, err) {
  appendLog(`✖ ${method} ${path}\n  ${typeof err === 'string' ? err : JSON.stringify(err).substring(0, 200)}`, 'err');
}

function appendLog(text, cls) {
  const log = document.getElementById('logContent');
  const entry = document.createElement('span');
  entry.className = 'log-entry ' + cls;
  entry.textContent = text + '\n\n';
  log.appendChild(entry);
  log.parentElement.scrollTop = log.parentElement.scrollHeight;
}

function updateCharCount() {
  const input = document.getElementById('messageInput');
  const counter = document.getElementById('charCount');
  const len = input.value.length;
  if (len > 0) {
    counter.textContent = `${len}/3000`;
    counter.style.color = len > 2800 ? 'var(--danger)' : len > 2400 ? 'var(--warning)' : 'var(--text-muted)';
  } else {
    counter.textContent = '';
  }
}

function toggleLog() {
  document.getElementById('logPanel').classList.toggle('open');
}