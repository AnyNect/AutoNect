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
const sessionId = crypto.randomUUID ?
  crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));

logger.info('Chat session started', { sessionId });

let animationActive = false;
let autoAllowEnabled = false;
let activeCommandGroup = null;
let isProcessing = false;

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
   Input helpers
   ═══════════════════════════════════════════════════════════════ */
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    sendBtn.disabled = !textarea.value.trim();
}
function autoResizeEdit(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSend();
    }
}
function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

/* ═══════════════════════════════════════════════════════════════
   Queue logic (task queue)
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
    const text = promptInput.value.trim();
    if (!text) return;
    promptInput.value = '';
    promptInput.style.height = 'auto';
    sendBtn.disabled = true;
    if (!isProcessing && !isPaused) {
        logger.info('Sending prompt directly', { prompt: text.substring(0, 50) });
        executeTask(text);
    } else {
        logger.info('Queuing prompt', { prompt: text.substring(0, 50) });
        taskQueue.push(text);
        renderQueue();
    }
}
function executeTask(promptText) {
    isProcessing = true;
    addMessage('user', promptText);
    showLoading();
    sendToAI(promptText).then(() => {
        isProcessing = false;
        processNextQueueTask();
    });
}
async function sendToAI(promptText) {
    try {
        logger.debug('Sending to AI', { sessionId, prompt: promptText.substring(0, 50) });
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: promptText, session_id: sessionId }),
        });
        if (!response.ok) throw new Error('Server returned ' + response.status);
        const data = await response.json();
        logger.info('AI response received', { commands: data.commands?.length || 0 });
        removeLoading();
        addMessage('assistant', data.answer, data.thinking, data.commands);
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
function processNextQueueTask() {
    if (!isPaused && taskQueue.length > 0) {
        const nextPrompt = taskQueue.shift();
        logger.debug('Processing next queue task', { prompt: nextPrompt.substring(0, 30) });
        renderQueue();
        executeTask(nextPrompt);
    }
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
function addMessage(role, content, thinking = '', commands = []) {
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
            logger.debug('Adding command cards', { count: commands.length });
            const group = {
                total: commands.length,
                completed: 0,
                outputs: [],
                resolved: false,
                onComplete: null
            };
            activeCommandGroup = group;
            let remainingCommands = [...commands];
            const preBlocks = bubble.querySelectorAll('pre');
            preBlocks.forEach((preEl) => {
                const codeEl = preEl.querySelector('code');
                if (!codeEl) return;
                const codeText = codeEl.textContent.trim();
                const isCommandClass = codeEl.className.includes('command') || codeEl.className.includes('language-command');
                const matchIndex = remainingCommands.findIndex(cmd => cmd.code.trim() === codeText);
                if (matchIndex !== -1) {
                    const cmd = remainingCommands[matchIndex];
                    const cmdSection = createCommandSection([cmd], group);
                    preEl.parentNode.replaceChild(cmdSection, preEl);
                    remainingCommands.splice(matchIndex, 1);
                } else if (isCommandClass && remainingCommands.length > 0) {
                    const cmd = remainingCommands[0];
                    const cmdSection = createCommandSection([cmd], group);
                    preEl.parentNode.replaceChild(cmdSection, preEl);
                    remainingCommands.shift();
                }
            });
            if (remainingCommands.length > 0) {
                const fallbackSection = createCommandSection(remainingCommands, group);
                bubble.appendChild(fallbackSection);
                logger.debug('Added fallback command cards', { count: remainingCommands.length });
            }
        }
    } else {
        bubble.textContent = content;
    }
    contentDiv.appendChild(bubble);
    row.appendChild(contentDiv);
    chatArea.appendChild(row);
    scrollToBottom();
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

function createCommandSection(commands, group = null) {
    const cmdSection = document.createElement('div');
    cmdSection.className = 'command-section';
    
    commands.forEach((cmd) => {
        const commandCode = cmd.code || '';
        const card = document.createElement('div');
        card.className = 'command-card expanded';
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
        
        // ── Button handlers ──
        declineBtn.onclick = (e) => { e.stopPropagation(); handleDecline(card); };
        
        allowBtn.onclick = (e) => {
            e.stopPropagation();
            if (autoAllowEnabled) {
                // Enqueue the command
                updateCardStatus(card, 'QUEUED', 'var(--color-warning)');
                commandExecutionQueue.push(card);
                if (!isCommandExecuting) processCommandQueue();
            } else {
                handleAllow(card);
            }
        };
        
        terminalBtn.onclick = (e) => { e.stopPropagation(); openNativeTerminal(commandCode); };

        // ── Auto‑Allow logic ──
        if (autoAllowEnabled) {
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
                        // Enqueue instead of directly executing
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

async function sendBatchFeedback(outputs) {
    try {
        logger.debug('Sending batch feedback', { count: outputs.length });
        const fbResponse = await fetch('/api/ai-feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ commands: outputs }),
        });
        if (fbResponse.ok) {
            const fbData = await fbResponse.json();
            if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || []);
            logger.info('Batch feedback processed', { commands: fbData.commands?.length || 0 });
        } else {
            logger.warn('Batch feedback server error', { status: fbResponse.status });
        }
    } catch (fbError) {
        logger.error('Batch feedback failed', fbError);
    }
}

function handleDecline(card) {
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
    
    if (card._group) {
        const group = card._group;
        group.outputs.push({ command: commandStr, stdout: '', stderr: 'Declined by user', exit_code: -1 });
        group.completed++;
        if (group.completed === group.total && !group.resolved) {
            group.resolved = true;
            activeCommandGroup = null;
            sendBatchFeedback(group.outputs);
        }
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
                ws.close();
                logger.info('Command exited', { exitCode, outputLength: collectedOutput.length });
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
    
    ws.onclose = () => {
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

        let activeColor, stateText;
        if (exitCode === 0) {
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
            try {
                logger.debug('Sending single feedback', { command: cmd.substring(0, 30), exitCode: code });
                const fbResponse = await fetch('/api/ai-feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: cmd, stdout: out, stderr: '', exit_code: code }),
                });
                if (fbResponse.ok) {
                    const fbData = await fbResponse.json();
                    if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || []);
                    logger.info('Single feedback processed');
                } else {
                    logger.warn('Single feedback server error', { status: fbResponse.status });
                }
            } catch (fbError) {
                logger.error('Single feedback failed', fbError);
            }
        };

        if (card._group) {
            const group = card._group;
            group.outputs.push({ command: commandStr, stdout: collectedOutput, stderr: '', exit_code: exitCode });
            group.completed++;
            if (group.completed === group.total && !group.resolved) {
                group.resolved = true;
                activeCommandGroup = null;
                sendBatchFeedback(group.outputs);
            }
        } else {
            sendSingleFeedback(commandStr, collectedOutput, exitCode);
        }

        isProcessing = false;
        sendBtn.disabled = !promptInput.value.trim();
        processNextQueueTask();

        // Call the completion callback if provided (for Auto‑Allow queue)
        if (onComplete) onComplete();
        logger.debug('WebSocket closed, command card finalized');
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

promptInput.focus();
logger.info('Chat UI initialized');