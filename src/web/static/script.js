/* ── Logger ── */
const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
let currentLogLevel = LOG_LEVELS.INFO;

const logger = {
  setLevel(level) {
    if (LOG_LEVELS[level] !== undefined) currentLogLevel = LOG_LEVELS[level];
  },
  _log(level, ...args) {
    if (LOG_LEVELS[level] < currentLogLevel) return;
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level}]`;
    switch (level) {
      case 'DEBUG': console.debug(prefix, ...args); break;
      case 'INFO':  console.info(prefix, ...args); break;
      case 'WARN':  console.warn(prefix, ...args); break;
      case 'ERROR': console.error(prefix, ...args); break;
    }
  },
  debug(...args) { this._log('DEBUG', ...args); },
  info(...args)  { this._log('INFO', ...args); },
  warn(...args)  { this._log('WARN', ...args); },
  error(...args) { this._log('ERROR', ...args); }
};
window.__logger = logger;

/* ── Chat state ── */
const chatArea = document.getElementById('chat-area');
const chatContainer = document.getElementById('chat-container');
const promptInput = document.getElementById('prompt');
const sendBtn = document.getElementById('send-btn');

let animationActive = false;
let autoAllowEnabled = false;
let activeCommandGroup = null;
let isProcessing = false;

/* ── Chat History State ── */
let currentChatId = null;
let chats = [];
let sidebarOpen = false;

/* ── Queue state ── */
const queueBubble = document.getElementById('queue-bubble');
const queueList = document.getElementById('queueList');
const queueBadge = document.getElementById('queueBadge');
const pauseBtn = document.getElementById('pauseBtn');

let isPaused = false;
let editingIndex = null;
let taskQueue = [];

/* ── Auto‑Allow command execution queue ── */
let commandExecutionQueue = [];
let isCommandExecuting = false;
// Number of /api/ai-feedback requests in flight. Their replies can
// spawn a NEW command group, so the queue must not drain while > 0
// (issue #7).
let pendingFeedback = 0;

/* ── Chat rendering limits ── */
// Most-recent messages rendered when a chat is opened. Older messages
// are hidden behind a "Show earlier" button to keep loadChat fast on
// long conversations. Tune this value if 10 feels too aggressive.
const MAX_RENDERED_MESSAGES = 10;

/* ── Syntax Highlighting ── */
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (e) {
                logger.debug('Highlight error for language', lang, e);
            }
        }
        if (lang !== 'command') {
            try {
                return hljs.highlightAuto(code).value;
            } catch (e) { /* no-op */ }
        }
        return code;
    }
});

/* ═══════════════════════════════════════════════════════════════
   Chat History
   ═══════════════════════════════════════════════════════════════ */

async function loadChatList() {
    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error('Failed to load chats');
        chats = await response.json();
        renderChatList();
        return chats;
    } catch (error) {
        logger.error('Error loading chat list', error);
        return [];
    }
}

function renderChatList() {
    const list = document.getElementById('chat-list');
    if (!list) return;

    if (chats.length === 0) {
        list.innerHTML = `<div class="empty-message">No chats yet.<br>Start a new conversation!</div>`;
        return;
    }

    list.innerHTML = chats.map(chat => `
        <div class="chat-item ${chat.id === currentChatId ? 'active' : ''}" data-chat-id="${chat.id}">
            <div class="chat-info" onclick="loadChat('${chat.id}')">
                <div class="chat-name" id="chat-name-${chat.id}">${escapeHtml(chat.name || 'Untitled')}</div>
                <div class="chat-preview">${escapeHtml(chat.last_message ? chat.last_message.substring(0, 60) : 'No messages')}</div>
            </div>
            <div class="chat-actions">
                <button class="dropdown-btn" onclick="toggleDropdown(event, '${chat.id}')" title="More actions">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                        <circle cx="12" cy="5" r="2"/>
                        <circle cx="12" cy="12" r="2"/>
                        <circle cx="12" cy="19" r="2"/>
                    </svg>
                </button>
                <div class="dropdown-menu" id="dropdown-${chat.id}">
                    <button onclick="renameChat('${chat.id}')">✏️ Rename</button>
                    <button onclick="togglePinChat('${chat.id}', event)">${chat.pinned ? '📌 Unpin' : '📌 Pin'}</button>
                    <button class="danger" onclick="deleteChat('${chat.id}', event)">🗑️ Delete</button>
                </div>
            </div>
        </div>
    `).join('');

    document.querySelectorAll('.chat-item').forEach(el => {
        el.addEventListener('dblclick', function(e) {
            if (e.target.closest('button') || e.target.closest('.dropdown-menu')) return;
            const chatId = this.dataset.chatId;
            enableChatNameEdit(chatId);
        });
    });
}

function toggleDropdown(event, chatId) {
    event.stopPropagation();
    const menu = document.getElementById(`dropdown-${chatId}`);
    if (!menu) return;
    document.querySelectorAll('.dropdown-menu.show').forEach(m => {
        if (m.id !== `dropdown-${chatId}`) m.classList.remove('show');
    });
    menu.classList.toggle('show');
    if (menu.classList.contains('show')) {
        const closeHandler = (e) => {
            if (!menu.contains(e.target) && !e.target.closest('.dropdown-btn')) {
                menu.classList.remove('show');
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 10);
    }
}

function renameChat(chatId) {
    const menu = document.getElementById(`dropdown-${chatId}`);
    if (menu) menu.classList.remove('show');
    enableChatNameEdit(chatId);
}

function enableChatNameEdit(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;
    const nameEl = document.getElementById(`chat-name-${chatId}`);
    if (!nameEl) return;

    const currentName = chat.name || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'chat-name-input';
    input.value = currentName;
    input.placeholder = 'Enter chat name...';
    
    nameEl.replaceWith(input);
    input.focus();
    input.select();

    const saveEdit = async () => {
        const newName = input.value.trim() || 'Untitled';
        try {
            const response = await fetch(`/api/chats/${chatId}/name`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            if (response.ok) {
                chat.name = newName;
                chat.is_custom_name = 1;
                renderChatList();
                logger.info('Chat name updated', { chatId, name: newName });
            }
        } catch (error) {
            logger.error('Failed to update chat name', error);
            renderChatList();
        }
    };

    input.addEventListener('blur', saveEdit);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        }
        if (e.key === 'Escape') {
            input.value = currentName;
            input.blur();
        }
    });
}

async function loadChat(chatId) {
    if (chatId === currentChatId) {
        toggleSidebar(false);
        return;
    }

    try {
        const response = await fetch(`/api/chats/${chatId}`);
        if (!response.ok) throw new Error('Failed to load chat');
        const data = await response.json();
        currentChatId = chatId;
        
        if (data.deepseek_url) {
            fetch('/api/browser/navigate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: data.deepseek_url })
            }).catch(err => logger.error('Navigation error', err));
        }
        
        chatArea.innerHTML = '';
        if (data.messages && data.messages.length > 0) {
            const total = data.messages.length;
            const hiddenCount = Math.max(0, total - MAX_RENDERED_MESSAGES);
            const visible = hiddenCount > 0 ? data.messages.slice(hiddenCount) : data.messages;

            if (hiddenCount > 0) {
                const hint = document.createElement('div');
                hint.className = 'message-row assistant';
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                const btn = document.createElement('button');
                btn.textContent = `Show ${hiddenCount} earlier message${hiddenCount === 1 ? '' : 's'}`;
                btn.style.cssText = 'background:transparent;border:1px dashed rgba(255,255,255,0.15);color:var(--text-muted);font-size:0.8rem;padding:6px 14px;border-radius:12px;cursor:pointer;font-family:inherit;';
                contentDiv.appendChild(btn);
                hint.appendChild(contentDiv);
                chatArea.appendChild(hint);
                btn.addEventListener('click', () => {
                    const beforeH = chatArea.scrollHeight;
                    const frag = document.createDocumentFragment();
                    data.messages.slice(0, hiddenCount).forEach(msg => {
                        let cmds = [];
                        if (msg.commands_json) { try { cmds = JSON.parse(msg.commands_json); } catch(e) {} }
                        addMessage(msg.role, msg.content, msg.thinking || '', cmds, true, frag, true);
                    });
                    chatArea.insertBefore(frag, hint);
                    hint.remove();
                    // Keep the same content in view after inserting above.
                    const delta = chatArea.scrollHeight - beforeH;
                    if (delta > 0) chatContainer.scrollTop += delta;
                });
                logger.debug('Rendered last %d of %d messages', visible.length, total);
            }

            visible.forEach(msg => {
                let commands = [];
                if (msg.commands_json) {
                    try { commands = JSON.parse(msg.commands_json); } catch(e) {}
                }
                addMessage(msg.role, msg.content, msg.thinking || '', commands, true);
            });
        } else {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'message-row assistant';
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.innerHTML = `<div class="bubble" style="color: var(--text-muted); text-align: center; padding: 30px 20px; opacity: 0.6;">No messages in this chat yet.<br>Start typing below!</div>`;
            emptyDiv.appendChild(contentDiv);
            chatArea.appendChild(emptyDiv);
        }
        
        scrollToBottom();
        renderChatList();
        toggleSidebar(false);
        logger.info('Loaded chat', { chatId, messages: data.messages?.length || 0, isCustom: data.is_custom_name });
    } catch (error) {
        logger.error('Error loading chat', error);
    }
}

async function loadContextChat() {
    // Start a fresh chat and send User/FOR_AI.md as the first message.
    // The server prepends src/prompts/system.txt on new sessions, so
    // this reproduces the manual "paste FOR_AI.md" flow in one click.
    const btn = document.getElementById('loadContextBtn');
    if (btn) { btn.disabled = true; }
    try {
        logger.info('Load Context: fetching FOR_AI.md');
        const resp = await fetch('/api/context/for-ai');
        if (!resp.ok) throw new Error('Server returned ' + resp.status);
        const data = await resp.json();
        if (!data.content || !data.content.trim()) {
            throw new Error('FOR_AI.md is empty');
        }

        // Reset to a fresh chat view.
        currentChatId = null;
        chatArea.innerHTML = '';
        const welcomeDiv = document.createElement('div');
        welcomeDiv.className = 'message-row assistant';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = '<div class="bubble" style="color: var(--text-muted); text-align: center; padding: 30px 20px; opacity: 0.6;">Loading context (FOR_AI.md)...</div>';
        welcomeDiv.appendChild(contentDiv);
        chatArea.appendChild(welcomeDiv);

        // Navigate DeepSeek to a fresh chat, then send the context file.
        await fetch('/api/browser/navigate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: 'https://chat.deepseek.com/' })
        });
        renderChatList();
        toggleSidebar(false);
        logger.info('Load Context: sending FOR_AI.md', { bytes: data.content.length });
        executeTask(data.content);
    } catch (error) {
        logger.error('Load Context failed', error);
        removeLoading();
        const errDiv = document.createElement('div');
        errDiv.className = 'message-row assistant';
        const errContent = document.createElement('div');
        errContent.className = 'message-content';
        errContent.innerHTML = '<div class="bubble" style="color: var(--accent-red); border: 1px solid var(--accent-red); padding: 10px 14px; border-radius: 12px;">Load Context failed: ' + error.message + '</div>';
        errDiv.appendChild(errContent);
        chatArea.appendChild(errDiv);
        scrollToBottom();
    } finally {
        if (btn) { btn.disabled = false; }
    }
}

async function newChat() {
    // Prevent spamming: if already in a new chat, do nothing
    if (currentChatId === null) {
        const welcomeBubble = chatArea.querySelector('.bubble');
        if (welcomeBubble && welcomeBubble.textContent.includes('New conversation')) {
            logger.debug('Already in a new chat, ignoring new chat click');
            return;
        }
    }

    currentChatId = null;
    chatArea.innerHTML = '';
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'message-row assistant';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `<div class="bubble" style="color: var(--text-muted); text-align: center; padding: 30px 20px; opacity: 0.6;">✨ New conversation<br>Type a message to start</div>`;
    welcomeDiv.appendChild(contentDiv);
    chatArea.appendChild(welcomeDiv);
    
    fetch('/api/browser/navigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: 'https://chat.deepseek.com/' })
    }).catch(err => logger.error('Navigation error', err));
    
    renderChatList();
    toggleSidebar(false);
    logger.info('New chat started');
}

async function togglePinChat(chatId, event) {
    if (event) event.stopPropagation();
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;
    const newPinned = !chat.pinned;
    try {
        const response = await fetch(`/api/chats/${chatId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned: newPinned })
        });
        if (response.ok) {
            chat.pinned = newPinned;
            renderChatList();
            logger.info('Chat pin toggled', { chatId, pinned: newPinned });
        }
    } catch (error) {
        logger.error('Failed to toggle pin', error);
    }
}

async function deleteChat(chatId, event) {
    if (event) event.stopPropagation();
    if (!confirm('Delete this chat?')) return;
    try {
        const response = await fetch(`/api/chats/${chatId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            chats = chats.filter(c => c.id !== chatId);
            if (currentChatId === chatId) {
                currentChatId = null;
                chatArea.innerHTML = '';
                const welcomeDiv = document.createElement('div');
                welcomeDiv.className = 'message-row assistant';
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.innerHTML = `<div class="bubble" style="color: var(--text-muted); text-align: center; padding: 30px 20px; opacity: 0.6;">✨ New conversation<br>Type a message to start</div>`;
                welcomeDiv.appendChild(contentDiv);
                chatArea.appendChild(welcomeDiv);
            }
            renderChatList();
            logger.info('Chat deleted', { chatId });
        }
    } catch (error) {
        logger.error('Failed to delete chat', error);
    }
}

function toggleSidebar(forceState) {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 768;
    
    if (typeof forceState === 'boolean') {
        if (isMobile) {
            sidebarOpen = forceState;
            sidebar.classList.toggle('sidebar-open', forceState);
            sidebar.classList.toggle('sidebar-closed', !forceState);
            let overlay = document.querySelector('.sidebar-overlay');
            if (forceState && !overlay) {
                overlay = document.createElement('div');
                overlay.className = 'sidebar-overlay active';
                overlay.onclick = () => toggleSidebar(false);
                document.getElementById('main-layout').appendChild(overlay);
            } else if (overlay) {
                overlay.classList.toggle('active', forceState);
            }
        }
        localStorage.setItem('sidebarOpen', String(sidebarOpen));
        return;
    }

    sidebarOpen = !sidebarOpen;
    localStorage.setItem('sidebarOpen', String(sidebarOpen));
    
    if (isMobile) {
        sidebar.classList.toggle('sidebar-open', sidebarOpen);
        sidebar.classList.toggle('sidebar-closed', !sidebarOpen);
        let overlay = document.querySelector('.sidebar-overlay');
        if (sidebarOpen && !overlay) {
            overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay active';
            overlay.onclick = () => toggleSidebar(false);
            document.getElementById('main-layout').appendChild(overlay);
        } else if (overlay) {
            overlay.classList.toggle('active', sidebarOpen);
        }
    } else {
        sidebar.classList.toggle('sidebar-closed', !sidebarOpen);
    }
}

async function restoreLastChat() {
    try {
        const res = await fetch('/api/current-chat');
        if (!res.ok) return;
        const data = await res.json();
        if (data.chat_id && data.chat_id !== currentChatId) {
            logger.info('Auto-opening last chat', data.chat_id);
            await loadChat(data.chat_id);
        }
    } catch (e) {
        logger.error('restoreLastChat failed', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('sidebarOpen');
    if (saved !== null) {
        sidebarOpen = saved === 'true';
    } else if (window.innerWidth > 768) {
        sidebarOpen = true;
    }
    const sidebar = document.getElementById('sidebar');
    if (sidebarOpen) {
        sidebar.classList.remove('sidebar-closed');
        if (window.innerWidth <= 768) sidebar.classList.add('sidebar-open');
    } else {
        sidebar.classList.add('sidebar-closed');
        if (window.innerWidth <= 768) sidebar.classList.remove('sidebar-open');
    }
    loadChatList().then(restoreLastChat);
    loadSupportedExtensions();
    connectEventSocket();
});

/* ═══════════════════════════════════════════════════════════════
   Input helpers
   ═══════════════════════════════════════════════════════════════ */
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    if (typeof updateSendBtnState === 'function') updateSendBtnState();
    else sendBtn.disabled = !textarea.value.trim();
}
function autoResizeEdit(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}
function handleKeyDown(event) {
    if (event.key !== 'Enter') return;
    // On touch devices (phone/tablet) Enter inserts a newline; send is
    // the Send button.  There is no Shift key, so the desktop
    // Enter=send / Shift+Enter=newline split cannot apply.
    if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) {
        return;
    }
    if (event.shiftKey) return;   // desktop: Shift+Enter = newline
    event.preventDefault();
    // Empty input + Enter toggles Auto-Allow instead of sending.
    if (!getEffectivePrompt().trim()) {
        toggleAutoAllow();
    } else {
        handleSend();
    }
}
function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

/* ═══════════════════════════════════════════════════════════════
   Queue logic
   ═══════════════════════════════════════════════════════════════ */
function toggleQueueBubble() {
    queueBubble.classList.toggle('expanded');
    logger.debug('Queue bubble toggled');
}
function togglePauseQueue(event) {
    event.stopPropagation();
    isPaused = !isPaused;
    if (isPaused) {
        pauseBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg><span>Resume</span>`;
        queueBadge.classList.add('paused');
        logger.info('Queue paused');
    } else {
        pauseBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg><span>Pause</span>`;
        queueBadge.classList.remove('paused');
        if (!isProcessing && taskQueue.length > 0) {
            logger.info('Queue resumed, processing next task');
            processNextQueueTask();
        }
    }
    renderQueue();
}

function handleSend() {
    const text = getEffectivePrompt().trim();
    if (!text) return;
    promptInput.value = '';
    promptInput.style.height = 'auto';
    clearPasteChip();
    sendBtn.disabled = true;
    // If dictation is on, drop its committed baseline too, otherwise
    // the next partial/final re-renders the just-sent text back in.
    // Also reset the STT buffer so audio from before the send does not
    // finalize into the now-empty box.
    _dictCommitted = '';
    if (_dictWS && _dictWS.readyState === WebSocket.OPEN) {
        _dictAwaitingReset = true;
        try { _dictWS.send('reset'); } catch (e) { _dictAwaitingReset = false; }
    }

    if (shouldQueueMessage()) {
        logger.info('Queuing prompt (app busy)', { prompt: text.substring(0, 50) });
        taskQueue.push(text);
        renderQueue();
    } else {
        logger.info('Sending prompt directly', { prompt: text.substring(0, 50) });
        executeTask(text);
    }
}

function executeTask(promptText) {
    isProcessing = true;
    addMessage('user', promptText);
    showLoading();

    uploadFilesAndSend(promptText)
        .then(() => {
            // Keep isProcessing = true if command cards are still pending.
            // The WebSocket close handler for the last command in the group
            // is responsible for clearing it and draining the queue.
            const hasPendingCommands = activeCommandGroup && !activeCommandGroup.resolved;
            if (!hasPendingCommands) {
                isProcessing = false;
                sendBtn.disabled = !promptInput.value.trim();
                processNextQueueTask();
            } else {
                logger.debug('executeTask done, but command group still pending — keeping busy');
            }
        })
        .catch((err) => {
            logger.error('executeTask failed', err);
            isProcessing = false;
            sendBtn.disabled = !promptInput.value.trim();
            processNextQueueTask();
        });
}

async function uploadFilesAndSend(promptText) {
    if (attachedFiles.length > 0) {
        logger.info(`Uploading ${attachedFiles.length} file(s)...`);
        for (let i = 0; i < attachedFiles.length; i++) {
            const file = attachedFiles[i];
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData,
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.error || 'Upload failed');
                }
                const data = await resp.json();
                logger.info(`Uploaded ${file.name}`, data);
            } catch (e) {
                logger.error('File upload error:', e);
                alert(`Failed to upload ${file.name}: ${e.message}`);
                isProcessing = false;
                sendBtn.disabled = !promptInput.value.trim();
                throw e;
            }
        }
        attachedFiles = [];
        showAttachedFiles();
    }

    await sendToAI(promptText);
}

// ── Updated sendToAI ──
async function sendToAI(promptText) {
    const chatId = currentChatId || null;
    try {
        logger.debug('Sending to AI', { chatId, prompt: promptText.substring(0, 50) });
        const response = await postWithRetry('/api/chat',
            { prompt: promptText, session_id: chatId });
        if (!response.ok) throw new Error('Server returned ' + response.status);
        const data = await response.json();
        logger.info('AI response received', { commands: data.commands?.length || 0 });
        removeLoading();
        addMessage('assistant', data.answer, data.thinking, data.commands, false);
        if (data.session_id) {
            currentChatId = data.session_id;
        }
        await loadChatList();
        // Title sync is handled server-side by the DOM observer.
        // See src/browser/observer.py and _on_dom_event in server.py.
    } catch (error) {
        logger.error('AI request failed', error);
        removeLoading();
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message-row assistant';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = `<div class="bubble" style="color: var(--accent-red); border: 1px solid var(--accent-red); padding: 10px 14px; border-radius: 12px;">Error: ${error.message}</div>`;
        errorDiv.appendChild(contentDiv);
        chatArea.appendChild(errorDiv);
        scrollToBottom();
    }
}

/* ── Command-work gate (issue #7) ──────────────────────────────
   Queue-bypass bug: with Auto-Allow ON, a message queued while a
   command group ran would fire the moment the last command's feedback
   resolved -- even though the AI's reply to that feedback had just
   spawned a NEW command group. The user message then raced the
   auto-executed commands, producing interleaved command/feedback
   loops. Fix: while Auto-Allow is ON and any command work is pending
   (an unresolved group, a queued command, or a command executing), a
   message must QUEUE rather than send. Auto-Allow OFF keeps the
   direct path -- manual approval already paces the flow. */
function hasPendingCommandWork() {
    return !!(activeCommandGroup && !activeCommandGroup.resolved)
        || commandExecutionQueue.length > 0
        || isCommandExecuting
        || pendingFeedback > 0;
}

function shouldQueueMessage() {
    if (isPaused) return true;
    // Queue while command work is pending ONLY under Auto-Allow. The
    // queue's job there is to wait out auto-executed commands so a
    // queued message does not race the next command group (issue #7).
    // With Auto-Allow OFF the user paces approvals manually and must
    // be able to send a new message while a command waits -- that
    // goes direct. (2026-10-02: previously the bare isProcessing check
    // caught the pending-approval case too, so messages queued with no
    // visible reason and no timer to release them.)
    if (autoAllowEnabled && hasPendingCommandWork()) return true;
    // Still queue while an AI request is in flight and nothing is
    // waiting on manual approval.
    if (isProcessing && !hasPendingCommandWork()) return true;
    return false;
}

/* ── Background-job idle flush ──────────────────────────────────
   A finished queue* job appends its block to the server's pending
   buffer. Normally the block rides the NEXT message. But if the app
   goes idle -- no user message, no command running, nothing queued --
   nobody sends that next message, and the block would sit forever.
   When the server broadcasts queue-job-done, the UI decides for
   itself whether it is idle and, if so, fires a turn to flush.
   Idle is a frontend truth: the PTY command state lives here. */
let _queueFlushPending = false;
let _queueFlushInFlight = false;

function isAppIdleForFlush() {
    if (isProcessing) return false;
    if (isPaused) return false;
    if (taskQueue.length > 0) return false;
    if (autoAllowEnabled && hasPendingCommandWork()) return false;
    return true;
}

async function maybeFlushQueueInjections() {
    if (!_queueFlushPending) return;
    if (_queueFlushInFlight) return;
    if (!isAppIdleForFlush()) return;
    _queueFlushPending = false;
    _queueFlushInFlight = true;
    try {
        isProcessing = true;
        logger.info('Flushing pending background-job output (idle)');
        const resp = await fetch('/api/queue-flush', { method: 'POST' });
        if (resp && resp.ok) {
            const data = await resp.json();
            if (data.flushed && data.answer) {
                addMessage('assistant', data.answer, data.thinking || '',
                           data.commands || [], false);
            } else if (!data.flushed) {
                logger.debug('queue flush: server had nothing pending');
            }
        }
    } catch (e) {
        logger.warn('queue flush failed', e);
        _queueFlushPending = true;   // retry on the next idle signal
    } finally {
        _queueFlushInFlight = false;
        // Mirror executeTask: if the AI's reply to the job output
        // spawned a command group, stay busy until it resolves.
        const hasPendingCommands = activeCommandGroup && !activeCommandGroup.resolved;
        if (!hasPendingCommands) {
            isProcessing = false;
            sendBtn.disabled = !promptInput.value.trim();
            processNextQueueTask();
        } else {
            logger.debug('queue flush done, command group pending — keeping busy');
        }
    }
}

function processNextQueueTask() {
    _processNextQueueTaskInner();
    maybeFlushQueueInjections();
}

function _processNextQueueTaskInner() {
    // Do not drain the queue if the app is still busy. This guards against
    // any handler that mistakenly calls us mid-flight.
    if (isProcessing) {
        logger.debug('processNextQueueTask called while busy — skipping');
        return;
    }
    if (isPaused) return;
    // Do not drain into a fresh prompt while Auto-Allow still has
    // command work pending -- the AI's feedback reply may have spawned
    // a new command group that must finish first (issue #7).
    if (autoAllowEnabled && hasPendingCommandWork()) {
        logger.debug('processNextQueueTask deferred - command work pending');
        return;
    }
    if (taskQueue.length === 0) return;

    const nextPrompt = taskQueue.shift();
    logger.debug('Processing next queue task', { prompt: nextPrompt.substring(0, 30) });
    renderQueue();
    executeTask(nextPrompt);
}


/* ── Queue editing ── */
function enableEdit(index, event) {
    if (event) event.stopPropagation();
    editingIndex = index;
    renderQueue();
    setTimeout(() => {
        const editField = document.getElementById(`edit-field-${index}`);
        if (editField) { editField.focus(); autoResizeEdit(editField); editField.select(); }
    }, 50);
    logger.debug('Editing queue item', { index });
}
function saveEdit(index, event) {
    if (event) event.stopPropagation();
    const editField = document.getElementById(`edit-field-${index}`);
    if (editField && editField.value.trim()) taskQueue[index] = editField.value.trim();
    editingIndex = null;
    renderQueue();
    logger.debug('Queue item saved', { index });
}
function handleEditKeyDown(event, index) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); saveEdit(index, event);
    } else if (event.key === 'Escape') { editingIndex = null; renderQueue();
    }
}
function removeTask(index, event) {
    if (event) event.stopPropagation();
    taskQueue.splice(index, 1);
    if (editingIndex === index) editingIndex = null;
    renderQueue();
    logger.debug('Queue item removed', { index });
}
/* ── Drag-and-drop ── */
let activeDrag = null;
function startPointerDrag(event) {
    if (event.target.closest('button') || event.target.closest('textarea') || editingIndex !== null) return;
    const itemEl = event.currentTarget;
    const initialIndex = parseInt(itemEl.dataset.index, 10);
    if (isNaN(initialIndex)) return;
    const rect = itemEl.getBoundingClientRect();
    const itemHeight = rect.height;
    const startY = event.clientY;
    const items = Array.from(queueList.querySelectorAll('.queue-message'));
    activeDrag = { itemEl, initialIndex, currentTargetIndex: initialIndex, startY, itemHeight, items, isDragging: false, pointerId: event.pointerId };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
    logger.debug('Drag started', { initialIndex });
}
function onPointerMove(event) {
    if (!activeDrag) return;
    const { itemEl, initialIndex, startY, itemHeight, items } = activeDrag;
    const deltaY = event.clientY - startY;
    if (!activeDrag.isDragging) {
        if (Math.abs(deltaY) > 5) {
            activeDrag.isDragging = true;
            itemEl.classList.add('dragging');
            try { itemEl.setPointerCapture(activeDrag.pointerId); } catch (e) {}
        } else return;
    }
    event.preventDefault();
    itemEl.style.transform = `translateY(${deltaY}px)`;
    const indexShift = Math.round(deltaY / itemHeight);
    let newIndex = Math.max(0, Math.min(items.length - 1, initialIndex + indexShift));
    if (newIndex !== activeDrag.currentTargetIndex) {
        activeDrag.currentTargetIndex = newIndex;
        items.forEach((el, i) => {
            if (i === initialIndex) return;
            if (initialIndex < newIndex && i > initialIndex && i <= newIndex) el.style.transform = `translateY(-${itemHeight + 2}px)`;
            else if (initialIndex > newIndex && i < initialIndex && i >= newIndex) el.style.transform = `translateY(${itemHeight + 2}px)`;
            else el.style.transform = 'translateY(0px)';
        });
    }
}
function onPointerUp(event) {
    if (!activeDrag) return;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerUp);
    const { itemEl, initialIndex, currentTargetIndex, items, isDragging } = activeDrag;
    if (isDragging) {
        try { itemEl.releasePointerCapture(event.pointerId);
        } catch (e) {}
        itemEl.classList.remove('dragging');
        if (initialIndex !== currentTargetIndex) {
            logger.debug('Queue item reordered', { from: initialIndex, to: currentTargetIndex });
            const movedItem = taskQueue.splice(initialIndex, 1)[0];
            taskQueue.splice(currentTargetIndex, 0, movedItem);
            const targetNode = items[currentTargetIndex];
            queueList.insertBefore(itemEl, currentTargetIndex > initialIndex ? targetNode.nextSibling : targetNode);
            Array.from(queueList.querySelectorAll('.queue-message')).forEach((el, idx) => {
                el.style.transform = ''; el.dataset.index = idx;
                const numSpan = el.querySelector('.queue-number');
                if (numSpan) numSpan.textContent = `#${idx + 1}`;
            });
        } else items.forEach(el => el.style.transform = '');
    }
    activeDrag = null;
}
function renderQueue() {
    if (taskQueue.length === 0) { queueBubble.style.display = 'none'; return;
    }
    queueBubble.style.display = 'flex';
    queueBadge.textContent = `${taskQueue.length} ${isPaused ? 'PAUSED' : 'QUEUED'}`;
    queueList.innerHTML = taskQueue.map((prompt, index) => {
        const isEditing = editingIndex === index;
        return `<div class="queue-message" data-index="${index}" onpointerdown="startPointerDrag(event)">
            <div class="queue-message-left">
                <span class="drag-handle" title="Drag to reorder"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="5" r="1.5"></circle><circle cx="15" cy="5" r="1.5"></circle><circle cx="9" cy="12" r="1.5"></circle><circle cx="15" cy="12" r="1.5"></circle><circle cx="9" cy="19" r="1.5"></circle><circle cx="15" cy="19" r="1.5"></circle></svg></span>
                <span class="queue-number">#${index + 1}</span>
                ${isEditing ? `<textarea id="edit-field-${index}" class="edit-input" rows="1" oninput="autoResizeEdit(this)" onkeydown="handleEditKeyDown(event, ${index})" onpointerdown="event.stopPropagation()" onclick="event.stopPropagation()" ondblclick="event.stopPropagation()">${escapeHtml(prompt)}</textarea>` : `<span class="queue-prompt" ondblclick="enableEdit(${index}, event)" title="Double click to edit">${escapeHtml(prompt)}</span>`}
            </div>
            <div class="queue-actions">
                ${isEditing ?
                `<button class="task-action-btn save" title="Save" onclick="saveEdit(${index}, event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></button>` : `<button class="task-action-btn" title="Edit Task" onclick="enableEdit(${index}, event)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button>`}
                <button class="task-action-btn delete" title="Cancel Task" onclick="removeTask(${index}, event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
            </div>
        </div>`;
    }).join('');
}

/* ═══════════════════════════════════════════════════════════════
   Chat messages
   ═══════════════════════════════════════════════════════════════ */
function addMessage(role, content, thinking = '', commands = [], historical = false, parent = null, noScroll = false) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (thinking && role === 'assistant') {
        const details = document.createElement('details');
        details.className = 'thinking-block';
        details.innerHTML = `<summary><span>Thinking</span><svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg></summary>`;
        const thinkingContent = document.createElement('div');
        thinkingContent.className = 'thinking-block-content';
        thinkingContent.textContent = thinking;
        details.appendChild(thinkingContent);
        contentDiv.appendChild(details);
    }
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (role === 'assistant') {
        bubble.innerHTML = marked.parse(content);
        bubble.querySelectorAll('pre code[class*="language-"]').forEach((codeEl) => {
            if (codeEl.closest('.command-section')) return;
            hljs.highlightElement(codeEl);
            const pre = codeEl.closest('pre');
            if (pre) pre.style.color = '';
        });
        if (commands && commands.length > 0) {
            // CRITICAL (2026-10-02 regression): split into shell commands
            // and other skills. The approval group's total MUST count
            // ONLY shell commands -- non-command skills never increment
            // group.completed, so counting them would leave the group
            // unresolved and the Auto-Allow queue stuck forever.
            const split = (typeof splitSkills === 'function')
                ? splitSkills(commands)
                : { commandSkills: commands, otherSkills: [] };
            const commandSkills = split.commandSkills;
            const otherSkills = split.otherSkills;
            logger.debug('Adding command cards', {
                total: commands.length,
                commands: commandSkills.length,
                otherSkills: otherSkills.length,
                historical
            });

            // Strip raw skill-tag blocks (<command>/<attach>/<kaggle>)
            // from the bubble FIRST, before the commandSkills gate.
            // A turn whose only skill is <attach> or <kaggle> never
            // enters the block below, so leaving this inside it made
            // the raw <attach> fence render as a duplicate text block
            // above its skill card (2026-10-02 bug).
            bubble.querySelectorAll('pre').forEach((preEl) => {
                const codeEl = preEl.querySelector('code');
                if (!codeEl) return;
                const codeText = codeEl.textContent.trim();
                if (/^<(queue[a-zA-Z_][\w-]*|command|attach|kaggle)>[\s\S]*<\/\1>$/.test(codeText)) {
                    preEl.remove();
                }
            });

            let group = null;
            if (commandSkills.length > 0) {
                group = {
                    total: commandSkills.length,
                    completed: 0,
                    outputs: [],
                    resolved: false,
                    onComplete: null,
                    attachPaths: [],
                    chat_id: currentChatId,
                    historical: historical
                };
                if (!historical) {
                    activeCommandGroup = group;
                }
                const remainingCommands = [...commandSkills];
                const preBlocks = bubble.querySelectorAll('pre');
                preBlocks.forEach((preEl) => {
                    const codeEl = preEl.querySelector('code');
                    if (!codeEl) return;
                    const codeText = codeEl.textContent.trim();
                    // Tag blocks (<command>/<attach>/<kaggle>) are already
                    // turned into cards from the commands array. Remove the
                    // raw block so it does not ALSO render as plain text.
                    if (/^<(queue[a-zA-Z_][\w-]*|command|attach|kaggle)>[\s\S]*<\/\1>$/.test(codeText)) {
                        preEl.remove();
                        return;
                    }
                    const matchIndex = remainingCommands.findIndex(cmd => (cmd.code || '').trim() === codeText);
                    if (matchIndex !== -1) {
                        const cmd = remainingCommands[matchIndex];
                        const cmdSection = createCommandSection([cmd], group);
                        preEl.parentNode.replaceChild(cmdSection, preEl);
                        remainingCommands.splice(matchIndex, 1);
                    }
                });
                if (remainingCommands.length > 0) {
                    const fallbackSection = createCommandSection(remainingCommands, group);
                    bubble.appendChild(fallbackSection);
                    logger.debug('Added fallback command cards', { count: remainingCommands.length });
                }
            }

            if (otherSkills.length > 0) {
                const skillSection = createSkillSection(otherSkills, historical, group);
                bubble.appendChild(skillSection);
                logger.debug('Added skill cards', { count: otherSkills.length });
            }
        }
    } else {
        bubble.textContent = content;
    }
    contentDiv.appendChild(bubble);
    row.appendChild(contentDiv);
    (parent || chatArea).appendChild(row);
    if (!noScroll) scrollToBottom();
}

/* ═══════════════════════════════════════════════════════════════
   Command cards & Auto‑Allow queue
   ═══════════════════════════════════════════════════════════════ */

function updateCardStatus(card, statusText, color) {
    const title = card.querySelector('.command-header-title');
    const dot = card.querySelector('.status-dot');
    if (title) {
        title.textContent = statusText;
        title.style.color = color;
    }
    if (dot) dot.style.backgroundColor = color;
}

function processCommandQueue() {
    if (isCommandExecuting || commandExecutionQueue.length === 0) return;
    isCommandExecuting = true;
    const card = commandExecutionQueue.shift();
    updateCardStatus(card, 'EXECUTING…', 'var(--text-sub)');
    handleAllow(card, () => {
        isCommandExecuting = false;
        if (commandExecutionQueue.length > 0) {
            processCommandQueue();
        }
    });
}

function toggleCommandCard(headerElem) {
    const card = headerElem.closest('.command-card');
    card.classList.toggle('expanded');
    updateCommandCardTitle(card);
    if (card.classList.contains('expanded')) {
        card.querySelectorAll('.command-body pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }
    logger.debug('Command card toggled', { expanded: card.classList.contains('expanded') });
}

function updateCommandCardTitle(card) {
    const titleElem = card.querySelector('.command-header-title');
    const isExpanded = card.classList.contains('expanded');
    const statusText = card.dataset.statusText || 'PENDING APPROVAL';
    const statusColor = card.dataset.statusColor || 'var(--color-pending)';
    const commandText = card.dataset.commandText || '';
    if (isExpanded) {
        titleElem.style.color = statusColor;
        updateHeaderTitleSmooth(titleElem, statusText, false);
    } else {
        if (commandText) {
            titleElem.style.color = 'var(--text-sub)';
            updateHeaderTitleSmooth(titleElem, `$ ${commandText}`, true);
        } else {
            titleElem.style.color = statusColor;
            updateHeaderTitleSmooth(titleElem, statusText, false);
        }
    }
}

function updateHeaderTitleSmooth(titleElem, newText, isCommand) {
    titleElem.classList.add('fading');
    setTimeout(() => {
        titleElem.textContent = newText;
        if (isCommand) titleElem.classList.add('is-command');
        else titleElem.classList.remove('is-command');
        titleElem.classList.remove('fading');
    }, 180);
}

function getCommandSafetyTag(safety) {
    switch (safety) {
        case 'deny': return { text: 'UNSAFE', class: 'cmd-tag-unsafe' };
        case 'warn': return { text: 'UNSURE', class: 'cmd-tag-unsure' };
        case 'allow':
        default: return { text: 'SAFE', class: 'cmd-tag-safe' };
    }
}

function toggleAutoAllow() {
    autoAllowEnabled = !autoAllowEnabled;
    const btn = document.getElementById('autoAllowBtn');
    const offIcon = document.getElementById('auto-allow-off');
    const onIcon = document.getElementById('auto-allow-on');
    if (btn) {
        btn.classList.toggle('active', autoAllowEnabled);
        if (offIcon) offIcon.style.display = autoAllowEnabled ? 'none' : 'block';
        if (onIcon) onIcon.style.display = autoAllowEnabled ? 'block' : 'none';
        btn.title = autoAllowEnabled ? 'Disable Auto-Allow' : 'Enable Auto-Allow';
    }
    logger.info('Auto-Allow toggled', { enabled: autoAllowEnabled });
}

/* ── Microphone dictation via the local Parakeet STT service ──
   Streams 16 kHz float32 PCM to ws://<host>:6012/ws/stt and writes
   the transcript into the prompt.  Partial results show live; final
   results commit on the service's silence endpoint. */
let _dictWS = null;
let _dictCtx = null;
let _dictStream = null;
let _dictNode = null;
let _dictSrc = null;
let _dictListening = false;
let _dictCommitted = '';   // text locked in by past finals (+ pre-existing input)
let _dictAwaitingReset = false;  // drop in-flight frames until reset-ack

const STT_PORT = 6012;

function _dictRender(live) {
    const base = _dictCommitted.replace(/\s+$/, '');
    promptInput.value = base + (live ? (base ? ' ' : '') + live : '');
    autoResize(promptInput);
}

function _dictCleanup() {
    try { if (_dictNode) _dictNode.disconnect(); } catch (e) {}
    try { if (_dictSrc) _dictSrc.disconnect(); } catch (e) {}
    try { if (_dictStream) _dictStream.getTracks().forEach(t => t.stop()); } catch (e) {}
    try { if (_dictCtx) _dictCtx.close(); } catch (e) {}
    if (_dictWS) { try { _dictWS.close(); } catch (e) {} }
    _dictNode = _dictSrc = _dictStream = _dictCtx = _dictWS = null;
}

function toggleDictation() {
    const btn = document.getElementById('mic-btn');
    if (_dictListening) {
        _dictListening = false;
        if (btn) btn.classList.remove('listening');
        _dictCleanup();
        logger.info('Dictation stopped');
        return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        logger.warn('Microphone API unavailable');
        return;
    }
    navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
    }).then(async (stream) => {
        _dictStream = stream;
        _dictCommitted = promptInput.value.replace(/\s+$/, '');

        const Ctx = window.AudioContext || window.webkitAudioContext;
        _dictCtx = new Ctx();
        // A context created outside a direct gesture can start suspended;
        // resume it or the ScriptProcessor never fires.
        try { await _dictCtx.resume(); } catch (e) {}
        const sr = _dictCtx.sampleRate;
        // Same-origin path; AutoNect proxies /ws/stt to the local STT
        // service.  Works over HTTPS and from the phone (no separate port,
        // no mixed content).
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${window.location.host}/ws/stt?sr=${sr}`);
        _dictWS = ws;
        ws.binaryType = 'arraybuffer';
        ws.onopen = () => {
            _dictSrc = _dictCtx.createMediaStreamSource(stream);
            _dictNode = _dictCtx.createScriptProcessor(2048, 1, 1);
            let _sentFrames = 0;
            _dictNode.onaudioprocess = (e) => {
                if (!_dictListening || ws.readyState !== WebSocket.OPEN) return;
                const f = e.inputBuffer.getChannelData(0);
                ws.send(new Float32Array(f).buffer);
                if ((++_sentFrames % 20) === 1) {
                    let peak = 0;
                    for (let i = 0; i < f.length; i += 16) peak = Math.max(peak, Math.abs(f[i]));
                    logger.info('dict frame', { frames: _sentFrames, peak: peak.toFixed(4), sr });
                }
            };
            const sink = _dictCtx.createGain();
            sink.gain.value = 0;                 // silent: no mic feedback
            _dictSrc.connect(_dictNode);
            _dictNode.connect(sink);
            sink.connect(_dictCtx.destination);
            _dictListening = true;
            if (btn) btn.classList.add('listening');
            logger.info('Dictation started');
        };

        ws.onmessage = (ev) => {
            let m;
            try { m = JSON.parse(ev.data); } catch (e) { return; }
            if (m.type === 'reset-ack') {
                // Everything before this was stale; safe to render again.
                _dictAwaitingReset = false;
            } else if (_dictAwaitingReset) {
                // Drop in-flight partial/final frames from before the
                // reset -- they would re-render the just-sent text.
            } else if (m.type === 'partial') {
                _dictRender(m.text || '');
            } else if (m.type === 'final') {
                if (m.text) {
                    _dictCommitted = (_dictCommitted ? _dictCommitted + ' ' : '') + m.text;
                }
                _dictRender('');
            } else if (m.type === 'error') {
                logger.warn('STT error', { message: m.message });
            }
        };
        ws.onerror = () => logger.warn('STT websocket error');
        ws.onclose = () => {
            _dictListening = false;
            if (btn) btn.classList.remove('listening');
        };
    }).catch((err) => {
        logger.warn('Microphone permission failed', { err: String(err) });
    });
}

/* ── Skill cards (attach, kaggle, ...) ────────────────────────────
   Non-command skills run server-side before the answer reaches the UI.
   cmd.result holds the handler's return value. These cards are
   informational -- they never enter the approval group, so they cannot
   affect the Auto-Allow queue. */
function createSkillSection(skillCmds, historical, group = null) {
    const section = document.createElement('div');
    section.className = 'skill-section';
    skillCmds.forEach((cmd) => {
        const skill = (cmd && cmd.skill) || 'skill';
        const result = (cmd && cmd.result) || {};
        const card = document.createElement('div');
        card.className = 'skill-card';
        card.dataset.skill = skill;

        const header = document.createElement('div');
        header.className = 'skill-header';
        header.innerHTML =
            '<span class="skill-badge">' + escapeHtml(skill) + '</span>' +
            '<span class="skill-title">' + escapeHtml(skillTitle(skill)) + '</span>';
        card.appendChild(header);

        const body = document.createElement('div');
        body.className = 'skill-body';

        if (skill === 'queue') {
            const res = (cmd && cmd.result) || {};
            const ok = document.createElement('div');
            ok.className = 'skill-ok';
            if (res.error) {
                ok.textContent = 'launch failed: ' + res.error;
            } else {
                ok.textContent = 'running in background (job ' +
                    (res.job_id || '?') + ', pid ' + (res.pid || '?') + ')';
            }
            body.appendChild(ok);
            const pre = document.createElement('pre');
            pre.className = 'skill-code';
            const code = document.createElement('code');
            code.textContent = (cmd && cmd.code) || '';
            pre.appendChild(code);
            body.appendChild(pre);
            const note = document.createElement('div');
            note.className = 'skill-result';
            note.textContent = 'Output will ride the next message.';
            body.appendChild(note);
        } else if (skill === 'attach') {
            // The server sends result.paths (raw strings, resolved at
            // feedback time). Older handlers sent result.files (objects).
            // Normalise both to {path, bytes, mime} for display + paths[].
            const rawPaths = result.paths || null;
            const files = rawPaths
                ? rawPaths.map(p => ({ path: p, bytes: null, mime: null }))
                : (result.files || []);
            const errors = result.errors || [];
            if (files.length > 0) {
                const ok = document.createElement('div');
                ok.className = 'skill-ok';
                ok.textContent = files.length + ' file' + (files.length === 1 ? '' : 's') +
                    ' attached to the AI';
                body.appendChild(ok);
                files.forEach(f => {
                    const row = document.createElement('div');
                    row.className = 'skill-file';
                    const meta = (f.bytes != null)
                        ? '  (' + humanBytes(f.bytes) + ', ' + (f.mime || '?') + ')'
                        : '';
                    row.textContent = f.path + meta;
                    body.appendChild(row);
                });
                // Live only. If a command group is active in this turn,
                // stash the paths on the group so they ride the SAME
                // feedback POST as the command output (resolved after the
                // commands ran). Otherwise fire standalone.
                if (!historical) {
                    const paths = files.map(f => f.path);
                    if (group) {
                        group.attachPaths = (group.attachPaths || []).concat(paths);
                    } else {
                        setTimeout(() => sendAttachFeedback(paths, currentChatId), 50);
                    }
                }
            }
            errors.forEach(e => {
                const row = document.createElement('div');
                row.className = 'skill-err';
                row.textContent = e.path + ' \u2014 ' + e.reason;
                body.appendChild(row);
            });
        } else {
            const pre = document.createElement('pre');
            pre.className = 'skill-code';
            const code = document.createElement('code');
            code.textContent = (cmd && cmd.code) || '';
            pre.appendChild(code);
            body.appendChild(pre);
            const res = document.createElement('div');
            res.className = 'skill-result';
            res.textContent = JSON.stringify(result);
            body.appendChild(res);
        }

        card.appendChild(body);
        section.appendChild(card);
    });
    return section;
}

function skillTitle(skill) {
    switch (skill) {
        case 'attach': return 'Files sent to AI';
        case 'kaggle': return 'Kaggle';
        case 'queue': return 'Background job';
        default: return skill;
    }
}

function humanBytes(n) {
    if (!n && n !== 0) return '?';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

function createCommandSection(commands, group = null) {
    const cmdSection = document.createElement('div');
    cmdSection.className = 'command-section';
    
    commands.forEach((cmd) => {
        const commandCode = cmd.code || '';
        const card = document.createElement('div');
        // Historical cards render collapsed on first paint. Rendering
        // them expanded then collapsing caused a full layout + syntax
        // highlight pass on every code block — the main cause of slow
        // loadChat on long chats. Live cards start expanded so the user
        // sees the command they are about to approve.
        const isHistorical = !!(group && group.historical);
        card.className = isHistorical ? 'command-card' : 'command-card expanded';
        card.dataset.command = commandCode;
        card.dataset.commandText = commandCode;
        card.dataset.statusText = 'PENDING APPROVAL';
        card.dataset.statusColor = 'var(--color-pending)';
        card._group = group;

        const header = document.createElement('div');
        header.className = 'command-header';
        header.onclick = () => toggleCommandCard(header);
        header.innerHTML = `<div class="command-header-left"><div class="status-dot-wrapper"><span class="status-dot" style="background-color: var(--color-pending);"></span><span class="pulse-ring"></span></div><span class="command-header-title" style="color: var(--color-pending);">PENDING APPROVAL</span></div><svg class="command-arrow" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
        
        const bodyWrapper = document.createElement('div');
        bodyWrapper.className = 'command-body-wrapper';
        const body = document.createElement('div');
        body.className = 'command-body';

        const safety = cmd.safety || 'allow';
        const tag = getCommandSafetyTag(safety);
        const tagHtml = `<span class="cmd-tag ${tag.class}">${tag.text}</span>`;

        const pre = document.createElement('pre');
        pre.className = 'command-code';
        pre.innerHTML = `
            <div class="command-code-content">
                <code class="code-text">${escapeHtml(commandCode)}</code>
                <span class="cursor"></span>
            </div>
            ${tagHtml}`;
            
        const btnRow = document.createElement('div');
        btnRow.className = 'command-btn-row';
        btnRow.innerHTML = `
            <button class="command-btn decline-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>Decline
            </button>
            <button class="command-btn allow-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>Allow
            </button>
            <button class="command-btn terminal-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="4 17 10 11 4 5"></polyline>
                    <line x1="12" y1="19" x2="20" y2="19"></line>
                </svg>Open Terminal
            </button>`;
            
        const declineBtn = btnRow.querySelector('.decline-btn');
        const allowBtn = btnRow.querySelector('.allow-btn');
        const terminalBtn = btnRow.querySelector('.terminal-btn');
        const outputArea = document.createElement('div');
        outputArea.className = 'command-output-area';
        outputArea.innerHTML = '<div class="progress-bar"></div>';
        
        declineBtn.onclick = (e) => { e.stopPropagation(); handleDecline(card); };
        allowBtn.onclick = (e) => {
            e.stopPropagation();
            if (autoAllowEnabled) {
                updateCardStatus(card, 'QUEUED', 'var(--color-warning)');
                commandExecutionQueue.push(card);
                if (!isCommandExecuting) processCommandQueue();
            } else {
                handleAllow(card);
            }
        };
        terminalBtn.onclick = (e) => { e.stopPropagation(); openNativeTerminal(commandCode); };

        if (autoAllowEnabled && !group.historical) {
            if (safety === 'deny') {
                setTimeout(() => handleDecline(card), 100);
                logger.debug('Auto-deny triggered for unsafe command', { command: commandCode.substring(0, 30) });
            } else if (safety === 'warn') {
                let countdown = 5;
                const timerEl = document.createElement('span');
                timerEl.className = 'auto-allow-countdown';
                timerEl.textContent = `Auto-Allowing in ${countdown}s...`;
                body.appendChild(timerEl);
                const timer = setInterval(() => {
                    countdown--;
                    timerEl.textContent = `Auto-Allowing in ${countdown}s...`;
                    if (countdown <= 0) {
                        clearInterval(timer);
                        if (timerEl.parentNode) timerEl.remove();
                        updateCardStatus(card, 'QUEUED', 'var(--color-warning)');
                        commandExecutionQueue.push(card);
                        if (!isCommandExecuting) processCommandQueue();
                    }
                }, 1000);
                card._autoAllowTimer = timer;
                card._autoAllowTimerEl = timerEl;
            } else if (safety === 'allow') {
                setTimeout(() => {
                    updateCardStatus(card, 'QUEUED', 'var(--color-warning)');
                    commandExecutionQueue.push(card);
                    if (!isCommandExecuting) processCommandQueue();
                }, 100);
                logger.debug('Auto-allow triggered for safe command', { command: commandCode.substring(0, 30) });
            }
        }

        body.appendChild(pre);
        body.appendChild(btnRow);
        body.appendChild(outputArea);
        bodyWrapper.appendChild(body);
        card.appendChild(header);
        card.appendChild(bodyWrapper);
        cmdSection.appendChild(card);
        void card.offsetHeight;
        if (isHistorical) {
            // Start collapsed — set the header title to show "$ <command>"
            // directly, skipping the smooth transition.
            const titleEl = card.querySelector('.command-header-title');
            if (titleEl) {
                titleEl.textContent = `$ ${commandCode}`;
                titleEl.classList.add('is-command');
                titleEl.style.color = 'var(--text-sub)';
            }
        }
    });
    return cmdSection;
}

async function openNativeTerminal(command) {
    logger.info('Opening native terminal', { command: command.substring(0, 50) });
    try {
        const response = await fetch('/api/open-terminal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: command }),
        });
        if (!response.ok) {
            throw new Error('Server returned ' + response.status);
        }
        const data = await response.json();
        logger.info('Terminal opened successfully', data);
    } catch (error) {
        logger.error('Failed to open native terminal', error);
        alert('Failed to open terminal: ' + error.message);
    }
}

/* ── Durable feedback delivery across a server restart ──────────
   When a command restarts AutoNect (scripts/restart.sh), the
   /ws/execute socket dies and the server goes down. The feedback POST
   carrying that command's output would then fail and the output would
   be LOST, stalling the AI loop until a human reconnects. Retry the
   POST with exponential backoff until the new server answers, so a
   self-restart survives end to end. */
async function postWithRetry(url, body, maxWaitMs = 180000) {
    // Retry on BOTH a thrown fetch error (server down) AND a 5xx
    // response. After a restart the server boots before the DeepSeek
    // browser reconnects, and answers 500 ("Provider not initialized")
    // until it is ready -- a 5xx that clears on its own. Retrying it is
    // what lets a self-restart's output reach the AI with no human step.
    const start = Date.now();
    let delay = 500;
    let attempt = 0;
    while (true) {
        attempt++;
        let resp = null;
        let err = null;
        try {
            resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        } catch (e) {
            err = e;
        }
        if (resp && resp.status < 500) {
            return resp;   // success or a real 4xx: hand it back
        }
        const elapsed = Date.now() - start;
        const why = err ? ('network error: ' + err) : ('HTTP ' + resp.status);
        if (elapsed >= maxWaitMs) {
            logger.error('POST ' + url + ' gave up after ' + elapsed + 'ms (' + why + ')');
            if (err) throw err;
            return resp;   // last 5xx: return so the caller logs it
        }
        logger.warn('POST ' + url + ' retryable (' + why + '); attempt ' + attempt + ' in ' + delay + 'ms');
        await new Promise(r => setTimeout(r, delay));
        delay = Math.min(delay * 2, 5000);
    }
}

// Kept as a thin alias for the feedback call sites.
function postFeedbackWithRetry(body, maxWaitMs) {
    return postWithRetry('/api/ai-feedback', body, maxWaitMs);
}

/* ── Event-driven server → UI channel ───────────────────────────
   The server pushes events over /ws/events (e.g. a restart report).
   No polling: the socket is opened once and reconnected on close
   (which is what happens when the server restarts). A pushed
   restart-report is forwarded to the AI. */
let _eventWS = null;
let _eventReconnectDelay = 500;

function connectEventSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/events`);
    _eventWS = ws;
    ws.onopen = () => {
        _eventReconnectDelay = 500;
        logger.info('Event socket connected');
    };
    ws.onmessage = (ev) => {
        let m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.type === 'restart-report' && m.content) {
            forwardRestartReport(m.content);
        } else if (m.type === 'queue-job-done') {
            _queueFlushPending = true;
            logger.info('Background job finished; will flush when idle', m);
            maybeFlushQueueInjections();
        }
    };
    ws.onclose = () => {
        logger.info('Event socket closed; reconnecting in ' + _eventReconnectDelay + 'ms');
        setTimeout(connectEventSocket, _eventReconnectDelay);
        _eventReconnectDelay = Math.min(_eventReconnectDelay * 2, 5000);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

async function forwardRestartReport(content) {
    try {
        await fetch('/api/restart-report/ack', { method: 'POST' });
        logger.info('Forwarding restart report to AI (event)', { bytes: content.length });
        isProcessing = true;
        const resp = await postFeedbackWithRetry({
            command: 'restart report (scripts/restart.sh)',
            stdout: content, stderr: '', exit_code: 0,
            chat_id: currentChatId,
        });
        if (resp && resp.ok) {
            const fb = await resp.json();
            if (fb.answer) addMessage('assistant', fb.answer, fb.thinking, fb.commands || [], false);
        }
    } catch (e) {
        logger.warn('restart report forward failed', e);
    } finally {
        isProcessing = false;
        sendBtn.disabled = !promptInput.value.trim();
        processNextQueueTask();
    }
}

async function sendBatchFeedback(outputs, chatId = null, outputId = null, files = null) {
    return (async () => {
    pendingFeedback++;
    try {
        logger.debug('Sending batch feedback', { count: outputs.length, chatId, files: files ? files.length : 0 });
        // DO NOT send output_id here. The batch already carries every
        // command's stdout in `outputs`. If output_id is also sent,
        // server.py's ai_feedback() pops its cache (the LAST card's
        // output only) into stdout_content, and the `is_multi` gate
        // becomes False -- so the server sends ONE command's output
        // and silently drops the rest. Regression seen 2026-10-02.
        const fbResponse = await postFeedbackWithRetry({
            commands: outputs, chat_id: chatId,
            files: files || [],
        });
        if (fbResponse.ok) {
            const fbData = await fbResponse.json();
            if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || [], false);
            logger.info('Batch feedback processed', { commands: fbData.commands?.length || 0 });
        } else {
            logger.warn('Batch feedback server error', { status: fbResponse.status });
        }
    } catch (fbError) {
        logger.error('Batch feedback failed', fbError);
    } finally {
        pendingFeedback = Math.max(0, pendingFeedback - 1);
    }
    })();
}

async function sendAttachFeedback(files, chatId = null) {
    // <attach> rides the SAME feedback channel as command output: the
    // card renders, then the files go to the AI and its reply lands as
    // a normal next message. No server-side loop, no swallowed message.
    return (async () => {
    pendingFeedback++;
    try {
        logger.debug('Sending attach feedback', { count: files.length, chatId });
        const fbResponse = await postFeedbackWithRetry({
            files: files, chat_id: chatId,
        });
        if (fbResponse.ok) {
            const fbData = await fbResponse.json();
            if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || [], false);
            logger.info('Attach feedback processed', { commands: fbData.commands?.length || 0 });
        } else {
            logger.warn('Attach feedback server error', { status: fbResponse.status });
        }
    } catch (fbError) {
        logger.error('Attach feedback failed', fbError);
    } finally {
        pendingFeedback = Math.max(0, pendingFeedback - 1);
    }
    })();
}

function handleDecline(card) {
    let feedbackPromise = Promise.resolve();
    if (card._autoAllowTimer) {
        clearInterval(card._autoAllowTimer);
        if (card._autoAllowTimerEl) card._autoAllowTimerEl.remove();
    }
    const btnRow = card.querySelector('.command-btn-row');
    const cursor = card.querySelector('.cursor');
    const titleElem = card.querySelector('.command-header-title');
    const statusDot = card.querySelector('.status-dot');
    const pulseRing = card.querySelector('.pulse-ring');
    const commandStr = card.dataset.command || '';
    if (cursor) cursor.classList.add('hidden');
    if (btnRow) btnRow.remove();
    if (pulseRing) pulseRing.remove();

    const activeColor = 'var(--color-denied)';
    const stateText = 'COMMAND DENIED';
    card.dataset.activeColor = activeColor;
    card.dataset.stateText = stateText;
    card.dataset.statusText = stateText;
    card.dataset.statusColor = activeColor;
    statusDot.style.backgroundColor = activeColor;
    titleElem.style.color = activeColor;
    card.classList.remove('expanded');
    updateCommandCardTitle(card);
    logger.warn('Command declined', { command: commandStr.substring(0, 30) });

    // ── Group bookkeeping ──
    let batchDone = false;
    if (card._group) {
        const group = card._group;
        group.outputs.push({ command: commandStr, stdout: '', stderr: 'Declined by user', exit_code: -1 });
        group.completed++;
        if (group.completed === group.total && !group.resolved) {
            group.resolved = true;
            // Only clear if it still names THIS group (Auto-Allow OFF
            // can now send a new message while a command waits; if its
            // reply spawns a second group, activeCommandGroup points at
            // that one and nulling here would release the queue early).
            if (activeCommandGroup === group) activeCommandGroup = null;
            // Await the feedback: its reply may spawn a new command group,
            // and draining the queue before it lands is the issue #7 race.
            feedbackPromise = sendBatchFeedback(group.outputs, group.chat_id, null, group.attachPaths);
            batchDone = true;
        }
    } else {
        batchDone = true;
    }

    // If this decline completed the whole batch, release the busy state
    // only AFTER the feedback reply has landed (or been attempted).
    if (batchDone) {
        feedbackPromise.finally(() => {
            isProcessing = false;
            sendBtn.disabled = !promptInput.value.trim();
            processNextQueueTask();
        });
    }
}

async function handleAllow(card, onComplete = null) {
    if (card._autoAllowTimer) {
        clearInterval(card._autoAllowTimer);
        if (card._autoAllowTimerEl) card._autoAllowTimerEl.remove();
    }
    const btnRow = card.querySelector('.command-btn-row');
    const outputArea = card.querySelector('.command-output-area');
    const cursor = card.querySelector('.cursor');
    const pulseRing = card.querySelector('.pulse-ring');
    const titleElem = card.querySelector('.command-header-title');
    const statusDot = card.querySelector('.status-dot');
    const commandStr = card.dataset.command || '';

    isProcessing = true; sendBtn.disabled = true;
    if (cursor) cursor.classList.add('hidden');
    if (btnRow) btnRow.remove();
    if (pulseRing) pulseRing.remove();

    outputArea.innerHTML = '';
    const terminalContainer = document.createElement('div');
    terminalContainer.className = 'terminal-container active';
    outputArea.appendChild(terminalContainer);

    titleElem.style.color = 'var(--text-sub)';
    updateHeaderTitleSmooth(titleElem, 'EXECUTING…', false);

    const term = new Terminal({
        cursorBlink: true,
        cursorStyle: 'bar',
        fontFamily: 'var(--font-mono)',
        fontSize: 13,
        lineHeight: 1.2,
        rows: 1,
        cols: 80,
        scrollback: 1000,
        theme: {
            background: '#121316',
            foreground: '#ececec',
            cursor: '#ffffff',
            cursorAccent: '#121316',
            selection: 'rgba(255,255,255,0.3)',
            black: '#1a1b1e',
            red: '#f87171',
            green: '#4ade80',
            yellow: '#fbbf24',
            blue: '#60a5fa',
            magenta: '#c084fc',
            cyan: '#22d3ee',
            white: '#e2e8f0',
            brightBlack: '#475569',
            brightRed: '#fca5a5',
            brightGreen: '#86efac',
            brightYellow: '#fde047',
            brightBlue: '#93c5fd',
            brightMagenta: '#d8b4fe',
            brightCyan: '#67e8f9',
            brightWhite: '#f8fafc',
        },
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon.WebLinksAddon());
    term.open(terminalContainer);
    const dims = fitAddon.proposeDimensions();
    term.resize(dims ? dims.cols : 80, 1);

    const maxRows = 20;
    term.onLineFeed(() => {
        const buffer = term.buffer.active;
        const contentRows = buffer.baseY + buffer.cursorY + 1;
        const currentRows = term.rows;
        if (contentRows > currentRows && currentRows < maxRows) {
            term.resize(term.cols, contentRows);
        }
    });

    card._term = term;
    card._fitAddon = fitAddon;
    card._terminalContainer = terminalContainer;
    card._isExecuting = true;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/execute`;
    const ws = new WebSocket(wsUrl);
    card._ws = ws;
    logger.debug('WebSocket connecting', { url: wsUrl });

    ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'exec', command: commandStr }));
        logger.info('WebSocket opened, command sent', { command: commandStr.substring(0, 30) });
    };

    let collectedOutput = '';
    let exitCode = -1;
    let outputId = null;

    ws.onmessage = async (event) => {
        if (event.data instanceof Blob) {
            const reader = new FileReader();
            reader.onload = () => {
                const bytes = new Uint8Array(reader.result);
                term.write(bytes, () => {
                    collectedOutput += new TextDecoder().decode(bytes);
                    const buffer = term.buffer.active;
                    const actualLines = buffer.baseY + buffer.cursorY + 1;
                    const targetRows = Math.min(22, Math.max(1, actualLines));
                    const currentCols = fitAddon.proposeDimensions()?.cols || term.cols || 80;
                    if (term.rows !== targetRows || term.cols !== currentCols) {
                        term.resize(currentCols, targetRows);
                    }
                });
            };
            reader.readAsArrayBuffer(event.data);
        } else {
            const msg = JSON.parse(event.data);
            if (msg.type === 'exit') {
                exitCode = msg.code;
                if (msg.output) collectedOutput = msg.output;
                outputId = msg.output_id || null;
                ws.close();
                logger.info('Command exited', { exitCode, outputLength: collectedOutput.length, outputId });
            } else if (msg.type === 'error') {
                term.writeln('\r\n\x1b[31m' + msg.message + '\x1b[0m');
                logger.error('WebSocket error message', msg);
                ws.close();
            } else if (msg.type === 'warning') {
                term.writeln('\r\n\x1b[33m⚠ ' + msg.message + '\x1b[0m');
                logger.warn('WebSocket warning', msg);
            } else if (msg.type === 'ask') {
                ws.send(JSON.stringify({ action: 'allow_once', path: msg.path || '' }));
                logger.debug('Auto-approved permission request');
            }
        }
    };

    ws.onclose = (event) => {
        card._isExecuting = false;
        term.options.disableStdin = true;
        term.options.cursorBlink = false;
        term.write('\x1b[?25l');

        terminalContainer.classList.remove('active');
        terminalContainer.classList.add('readonly');

        const buffer = term.buffer.active;
        const actualLines = buffer.baseY + buffer.cursorY + 1;
        const targetRows = Math.min(22, Math.max(1, actualLines));
        const currentCols = fitAddon.proposeDimensions()?.cols || term.cols || 80;
        term.resize(currentCols, targetRows);

        delete card._ws;

        // ── Resolve exit code: prefer in-band message, fall back to close frame ──
        let resolvedExitCode = exitCode;
        if (resolvedExitCode === -1 && event && typeof event.reason === 'string' && event.reason) {
            const m = event.reason.match(/^(exit|signal):(-?\d+|unknown)$/);
            if (m) {
                if (!(m[1] === 'exit' && m[2] === 'unknown')) {
                    const n = parseInt(m[2], 10);
                    resolvedExitCode = (m[1] === 'signal') ? -n : n;
                    logger.info('Recovered exit code from close frame', {
                        reason: event.reason, resolvedExitCode
                    });
                }
            }
        }
        if (resolvedExitCode === -1 && event && event.code === 1000) {
            resolvedExitCode = 0;
        }

        let activeColor, stateText;
        if (resolvedExitCode === 0) {
            activeColor = 'var(--color-success)';
            stateText = 'COMMAND EXECUTED';
        } else {
            activeColor = 'var(--color-error)';
            stateText = 'COMMAND FAILED';
        }

        card.dataset.activeColor = activeColor;
        card.dataset.stateText = stateText;
        card.dataset.statusText = stateText;
        card.dataset.statusColor = activeColor;
        statusDot.style.backgroundColor = activeColor;
        titleElem.style.color = activeColor;
        card.classList.remove('expanded');
        updateCommandCardTitle(card);

        const sendSingleFeedback = async (cmd, out, code) => {
            return (async () => {
            pendingFeedback++;
            try {
                logger.debug('Sending single feedback', {
                    command: cmd.substring(0, 30),
                    exitCode: code,
                    chatId: currentChatId,
                    outputId
                });
                const fbResponse = await postFeedbackWithRetry({
                    command: cmd,
                    stdout: out,
                    stderr: '',
                    exit_code: code,
                    chat_id: currentChatId,
                    output_id: outputId
                });
                if (fbResponse.ok) {
                    const fbData = await fbResponse.json();
                    if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || [], false);
                    logger.info('Single feedback processed');
                } else {
                    logger.warn('Single feedback server error', { status: fbResponse.status });
                }
            } catch (fbError) {
                logger.error('Single feedback failed', fbError);
            } finally {
                pendingFeedback = Math.max(0, pendingFeedback - 1);
            }
            })();
        };

        // ── Only release the busy state when the entire batch is done ──
        // Previously isProcessing was cleared here unconditionally, which
        // meant that in a multi-command group the queue would drain after
        // the first command finished — before the remaining commands had
        // even started. That is the "queue bypass" reported in issue #7.
        let batchDone = false;
        let feedbackPromise = Promise.resolve();
        if (card._group) {
            const group = card._group;
            group.outputs.push({
                command: commandStr,
                stdout: collectedOutput,
                stderr: '',
                exit_code: resolvedExitCode
            });
            group.completed++;
            if (group.completed === group.total && !group.resolved) {
                group.resolved = true;
                // Only clear if it still names THIS group -- see handleDecline.
                if (activeCommandGroup === group) activeCommandGroup = null;
                // outputId intentionally omitted -- see sendBatchFeedback.
                feedbackPromise = sendBatchFeedback(group.outputs, group.chat_id, null, group.attachPaths);
                batchDone = true;
            }
        } else {
            feedbackPromise = sendSingleFeedback(commandStr, collectedOutput, resolvedExitCode);
            batchDone = true;
        }

        if (batchDone) {
            // Hold isProcessing until the AI has actually responded to the
            // command output. Releasing it immediately after the command
            // exits opened a window where a queued message could fire
            // before the AI's reply landed in the chat.
            feedbackPromise.finally(() => {
                isProcessing = false;
                sendBtn.disabled = !promptInput.value.trim();
                processNextQueueTask();
            });
        }

        if (onComplete) onComplete();
        logger.debug('WebSocket closed, command card finalized', { batchDone });
    };

    ws.onerror = (err) => {
        logger.error('WebSocket error', err);
        term.write('\r\n\x1b[31mConnection error\x1b[0m\r\n');
        ws.close();
    };

    term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "stdin", data: data }));
        }
    });

    term.onResize(({ cols, rows }) => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'resize', cols, rows }));
        }
    });

    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                if (card.classList.contains('expanded') && card._term && !card._isExecuting) {
                    setTimeout(() => {
                        const dims = card._fitAddon.proposeDimensions();
                        if (dims) card._term.resize(dims.cols, card._term.rows);
                    }, 50);
                }
            }
        });
    });
    observer.observe(card, { attributes: true, attributeFilter: ['class'] });
    card._observer = observer;
}

/* ═══════════════════════════════════════════════════════════════
   File upload UI helpers
   ═══════════════════════════════════════════════════════════════ */

// Authoritative extension list comes from GET /api/supported-extensions
// (backed by src/web/static/supported-extensions.json). Nothing is
// hardcoded here: if the fetch has not completed yet, nothing is
// accepted. That matches the server, which also validates by this list.
let SUPPORTED_EXTENSIONS = new Set();

async function loadSupportedExtensions() {
  try {
    const resp = await fetch('/api/supported-extensions');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    const list = Array.isArray(data.extensions) ? data.extensions : [];
    SUPPORTED_EXTENSIONS = new Set(
      list.map(e => String(e).replace(/^\./, '').toLowerCase())
    );
    logger.info('Loaded ' + SUPPORTED_EXTENSIONS.size + ' supported extensions');
  } catch (e) {
    logger.warn('Could not load supported extensions; uploads disabled:', e.message);
  }
}

function isFileSupported(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  return SUPPORTED_EXTENSIONS.has(ext);
}

let attachedFiles = [];

function showAttachedFiles() {
    const container = document.getElementById('attached-files');
    if (!container) return;
    if (attachedFiles.length === 0) {
        container.innerHTML = '';
        container.style.display = 'none';
        return;
    }
    container.style.display = 'flex';
    container.innerHTML = attachedFiles.map((file, index) => {
        const ext = (file.name.split('.').pop() || '?').slice(0, 4).toUpperCase();
        return `<span class="attach-pill attach-pill--file">
            <span class="attach-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span>
            <span class="attach-meta">
                <span class="attach-label">${escapeHtml(file.name)}</span>
                <span class="attach-sub">${ext} &middot; ${(file.size / 1024).toFixed(1)} KB</span>
            </span>
            <span class="attach-remove" data-index="${index}" title="Remove">&times;</span>
        </span>`;
    }).join('');

    container.querySelectorAll('.attach-remove').forEach(el => {
        el.addEventListener('click', function() {
            const idx = parseInt(this.dataset.index, 10);
            if (!isNaN(idx)) {
                attachedFiles.splice(idx, 1);
                showAttachedFiles();
                const fileInput = document.getElementById('file-input');
                if (fileInput) fileInput.value = '';
            }
        });
    });
}

/* ── Paste chips (multi: each paste becomes its own chip) ── */
const PASTE_CHIP_THRESHOLD = 2000;
let pasteChips = [];  // [{id, text, charCount, expanded, anchor}]
let pasteChipNextId = 1;

function getEffectivePrompt() {
    const box = promptInput.value;
    if (pasteChips.length === 0) return box;

    // Chips still hidden (not spliced into the box).
    const collapsed = pasteChips.filter(c => !c.expanded);
    if (collapsed.length === 0) return box;

    // Interleave by the anchor captured at paste time. Anchor is a position
    // in the box when the paste happened; clamp to current box length in
    // case the user edited afterwards.
    const byAnchor = [...collapsed].sort((a, b) => a.anchor - b.anchor);

    const parts = [];
    let cursor = 0;
    for (const c of byAnchor) {
        const a = Math.max(cursor, Math.min(c.anchor, box.length));
        const seg = box.slice(cursor, a);
        if (seg) parts.push(seg);
        parts.push(c.text);
        cursor = a;
    }
    if (cursor < box.length) {
        const seg = box.slice(cursor);
        if (seg) parts.push(seg);
    }
    return parts.join('\n\n');
}

function updateSendBtnState() {
    sendBtn.disabled = !getEffectivePrompt().trim();
}

function renderPasteChips() {
    const row = document.getElementById('paste-chip-row');
    if (!row) return;
    if (pasteChips.length === 0) {
        row.innerHTML = '';
        row.style.display = 'none';
        return;
    }
    row.style.display = 'flex';
    row.innerHTML = pasteChips.map(c => {
        const label = c.expanded ? 'Hide' : 'Show';
        return '<span class="attach-pill attach-pill--paste">' +
            '<span class="attach-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></span>' +
            '<span class="attach-meta">' +
                '<span class="attach-label">Pasted text</span>' +
                '<span class="attach-sub">' + c.charCount.toLocaleString() + ' chars</span>' +
            '</span>' +
            '<span class="attach-action" data-chip-id="' + c.id + '">' + label + '</span>' +
            '<span class="attach-remove" data-chip-id="' + c.id + '">&times;</span></span>';
    }).join('');
    row.querySelectorAll('.attach-action').forEach(el => {
        el.onclick = function() { toggleChip(parseInt(this.dataset.chipId, 10)); };
    });
    row.querySelectorAll('.attach-remove').forEach(el => {
        el.onclick = function() { removeChip(parseInt(this.dataset.chipId, 10)); };
    });
}

function toggleChip(id) {
    const ta = document.getElementById('prompt');
    if (!ta) return;
    const chip = pasteChips.find(c => c.id === id);
    if (!chip) return;
    if (chip.expanded) {
        // Hide: cut its text out at the exact position it went in.
        if (typeof chip.insertedAt === 'number') {
            const s = chip.insertedAt;
            const e = s + chip.text.length;
            if (s >= 0 && e <= ta.value.length && ta.value.slice(s, e) === chip.text) {
                ta.value = ta.value.slice(0, s) + ta.value.slice(e);
            } else {
                // Position drifted (should not happen, input clears chips)
                const idx = ta.value.indexOf(chip.text);
                if (idx !== -1) ta.value = ta.value.slice(0, idx) + ta.value.slice(idx + chip.text.length);
            }
        }
        chip.expanded = false;
        chip.insertedAt = null;
    } else {
        // Show: splice its text at the anchor captured at paste time (clamped)
        let pos = (typeof chip.anchor === 'number') ? chip.anchor : ta.value.length;
        if (pos > ta.value.length) pos = ta.value.length;
        if (pos < 0) pos = 0;
        ta.value = ta.value.slice(0, pos) + chip.text + ta.value.slice(pos);
        chip.expanded = true;
        chip.insertedAt = pos;
        ta.focus();
        try { ta.setSelectionRange(pos + chip.text.length, pos + chip.text.length); } catch (e) {}
        if (typeof autoResize === 'function') autoResize(ta);
    }
    updateSendBtnState();
    renderPasteChips();
}

function removeChip(id) {
    const ta = document.getElementById('prompt');
    const chip = pasteChips.find(c => c.id === id);
    if (!chip) return;
    if (chip.expanded && ta && typeof chip.insertedAt === 'number') {
        const s = chip.insertedAt;
        const e = s + chip.text.length;
        if (s >= 0 && e <= ta.value.length && ta.value.slice(s, e) === chip.text) {
            ta.value = ta.value.slice(0, s) + ta.value.slice(e);
        }
    }
    pasteChips = pasteChips.filter(c => c.id !== id);
    updateSendBtnState();
    renderPasteChips();
}

function clearPasteChips() {
    const ta = document.getElementById('prompt');
    if (ta) {
        // Remove expanded chips from highest position to lowest so earlier
        // offsets stay valid.
        const expanded = pasteChips
            .filter(c => c.expanded && typeof c.insertedAt === 'number')
            .sort((a, b) => b.insertedAt - a.insertedAt);
        for (const c of expanded) {
            const s = c.insertedAt;
            const e = s + c.text.length;
            if (s >= 0 && e <= ta.value.length && ta.value.slice(s, e) === c.text) {
                ta.value = ta.value.slice(0, s) + ta.value.slice(e);
            }
        }
        ta.style.maxHeight = '';
        ta.style.overflowY = '';
    }
    pasteChips = [];
    updateSendBtnState();
    renderPasteChips();
}
// Backward-compat alias for handleSend
function clearPasteChip() { clearPasteChips(); }

if (promptInput) {
    promptInput.addEventListener('input', function() {
        // Edits invalidate stored positions. Drop any chip whose text was
        // spliced into the box (it is now literal content); keep the rest.
        const hadExpanded = pasteChips.some(c => c.expanded);
        if (hadExpanded) {
            pasteChips = pasteChips.filter(c => !c.expanded);
            renderPasteChips();
            updateSendBtnState();
        }
    });

    promptInput.addEventListener('paste', function(e) {
        const cd = e.clipboardData;
        if (!cd) return;
        const pasted = cd.getData('text/plain') || '';
        if (pasted.length < PASTE_CHIP_THRESHOLD) return;
        e.preventDefault();
        const pos = promptInput.selectionStart != null
            ? promptInput.selectionStart
            : promptInput.value.length;
        pasteChips.push({
            id: pasteChipNextId++,
            text: pasted,
            charCount: pasted.length,
            expanded: false,
            insertedAt: null,
            anchor: pos
        });
        updateSendBtnState();
        renderPasteChips();
    });
}

const fileInput = document.getElementById('file-input');
if (fileInput) {
    fileInput.addEventListener('change', function(e) {
        if (this.files.length === 0) return;
        for (let file of this.files) {
            if (!isFileSupported(file)) {
                alert(`File "${file.name}" is not supported. Supported formats: PDF, DOC, XLSX, PPT, images, text, and code.`);
                continue;
            }
            const exists = attachedFiles.some(f => f.name === file.name && f.size === file.size);
            if (!exists) {
                attachedFiles.push(file);
            }
        }
        showAttachedFiles();
        this.value = '';
    });

    const label = document.getElementById('file-upload-btn');
    if (label) {
        let dragCounter = 0;
        label.addEventListener('dragenter', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dragCounter++;
            if (dragCounter === 1) this.classList.add('drag-over');
        });
        label.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
        });
        label.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dragCounter--;
            if (dragCounter === 0) this.classList.remove('drag-over');
        });
        label.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('drag-over');
            dragCounter = 0;
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                for (let file of files) {
                    if (!isFileSupported(file)) {
                        alert(`File "${file.name}" is not supported. Supported formats: PDF, DOC, XLSX, PPT, images, text, and code.`);
                        continue;
                    }
                    const exists = attachedFiles.some(f => f.name === file.name && f.size === file.size);
                    if (!exists) {
                        attachedFiles.push(file);
                    }
                }
                showAttachedFiles();
                if (fileInput) fileInput.value = '';
            }
        });
        label.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (fileInput) fileInput.click();
            }
        });
    }
}

/* ═══════════════════════════════════════════════════════════════
   Loading portal
   ═══════════════════════════════════════════════════════════════ */
function showLoading() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.id = 'loading-indicator';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `<div class="portal-oval"><div class="inner-content"><div id="portal-track" class="track"></div></div></div>`;
    row.appendChild(contentDiv);
    chatArea.appendChild(row);
    scrollToBottom();
    animationActive = true;
    runPortalAnimation();
}
async function runPortalAnimation() {
    const states = [
        { icon: '🧠', label: 'Thinking', spin: false },
        { icon: '⏳', label: 'Processing', spin: true },
    ];
    let index = 0;
    const track = document.getElementById('portal-track');
    if (!track) return;
    function createItem(state, fullText = false) {
        const div = document.createElement('div');
        div.className = 'item';
        const labelText = fullText ? state.label + "..." : "";
        div.innerHTML = `<div class="icon ${state.spin ? 'spin' : ''}">${state.icon}</div><div class="label">${labelText}</div>`;
        return div;
    }
    let currentItem = createItem(states[index]);
    track.appendChild(currentItem);
    while (animationActive && document.getElementById('portal-track')) {
        const labelEl = currentItem.querySelector('.label');
        if (!labelEl.textContent) {
            const text = states[index].label + "...";
            for (let char of text) {
                if (!animationActive) break;
                labelEl.textContent += char;
                await new Promise(r => setTimeout(r, 40));
            }
        }
        await new Promise(r => setTimeout(r, 800));
        if (!animationActive) break;
        index = (index + 1) % states.length;
        let nextItem = createItem(states[index], true);
        track.appendChild(nextItem);
        track.style.transform = 'translateY(-30px)';
        await new Promise(r => setTimeout(r, 500));
        if (!animationActive) break;
        track.removeChild(currentItem);
        track.style.transition = 'none';
        track.style.transform = 'translateY(0)';
        track.offsetHeight;
        track.style.transition = 'transform 0.5s cubic-bezier(0.2, 0, 0, 1)';
        currentItem = nextItem;
    }
}
function removeLoading() {
    animationActive = false;
    const loading = document.getElementById('loading-indicator');
    if (loading) loading.remove();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* ── Auto-Allow Button Initialization ── */
const autoAllowBtn = document.getElementById('autoAllowBtn');
if (autoAllowBtn) {
    autoAllowBtn.addEventListener('click', toggleAutoAllow);
    const offIcon = document.getElementById('auto-allow-off');
    const onIcon = document.getElementById('auto-allow-on');
    if (offIcon) offIcon.style.display = 'block';
    if (onIcon) onIcon.style.display = 'none';
}

const micBtn = document.getElementById('mic-btn');
if (micBtn) {
    micBtn.addEventListener('click', toggleDictation);
}

promptInput.focus();
logger.info('Chat UI initialized');