/* ── Chat state ── */
const chatArea = document.getElementById('chat-area');
const chatContainer = document.getElementById('chat-container');
const promptInput = document.getElementById('prompt');
const sendBtn = document.getElementById('send-btn');
const sessionId = crypto.randomUUID ? crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));

let animationActive = false;
let isProcessing = false;          // true when AI is generating

/* ── Queue state ── */
const queueBubble = document.getElementById('queue-bubble');
const queueList = document.getElementById('queueList');
const queueBadge = document.getElementById('queueBadge');
const pauseBtn = document.getElementById('pauseBtn');

let isPaused = false;
let editingIndex = null;
let taskQueue = [];

/* ── Syntax Highlighting (VS Code style via highlight.js) ── */
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (e) {
                // fall through to auto
            }
        }
        if (lang !== 'command') {
            try {
                return hljs.highlightAuto(code).value;
            } catch (e) {
                // no-op
            }
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
   Queue logic
   ═══════════════════════════════════════════════════════════════ */

function toggleQueueBubble() {
    queueBubble.classList.toggle('expanded');
}

function togglePauseQueue(event) {
    event.stopPropagation();
    isPaused = !isPaused;
    if (isPaused) {
        pauseBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg><span>Resume</span>`;
        queueBadge.classList.add('paused');
    } else {
        pauseBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg><span>Pause</span>`;
        queueBadge.classList.remove('paused');
        if (!isProcessing && taskQueue.length > 0) processNextQueueTask();
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
        executeTask(text);
    } else {
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
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: promptText, session_id: sessionId }),
        });
        if (!response.ok) throw new Error('Server returned ' + response.status);
        const data = await response.json();
        removeLoading();
        addMessage('assistant', data.answer, data.thinking, data.commands);
    } catch (error) {
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
}

function saveEdit(index, event) {
    if (event) event.stopPropagation();
    const editField = document.getElementById(`edit-field-${index}`);
    if (editField && editField.value.trim()) taskQueue[index] = editField.value.trim();
    editingIndex = null;
    renderQueue();
}

function handleEditKeyDown(event, index) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); saveEdit(index, event); }
    else if (event.key === 'Escape') { editingIndex = null; renderQueue(); }
}

function removeTask(index, event) {
    if (event) event.stopPropagation();
    taskQueue.splice(index, 1);
    if (editingIndex === index) editingIndex = null;
    renderQueue();
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
        try { itemEl.releasePointerCapture(event.pointerId); } catch (e) {}
        itemEl.classList.remove('dragging');
        if (initialIndex !== currentTargetIndex) {
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
    if (taskQueue.length === 0) { queueBubble.style.display = 'none'; return; }
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
                ${isEditing ? `<button class="task-action-btn save" title="Save" onclick="saveEdit(${index}, event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></button>` : `<button class="task-action-btn" title="Edit Task" onclick="enableEdit(${index}, event)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button>`}
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

        // Apply Highlight.js to any code blocks that were injected as raw HTML
        bubble.querySelectorAll('pre code[class*="language-"]').forEach((codeEl) => {
            // Don't touch command blocks (they become command cards)
            if (codeEl.closest('.command-section')) return;
            hljs.highlightElement(codeEl);
            // Remove the hardcoded text colour from the parent <pre> so the theme's colours work
            const pre = codeEl.closest('pre');
            if (pre) pre.style.color = '';
        });

        // INLINE COMMAND CARDS: Replace matching <pre> blocks dynamically
        if (commands && commands.length > 0) {
            let remainingCommands = [...commands];
            const preBlocks = bubble.querySelectorAll('pre');

            preBlocks.forEach((preEl) => {
                const codeEl = preEl.querySelector('code');
                if (!codeEl) return;

                const codeText = codeEl.textContent.trim();
                const isCommandClass = codeEl.className.includes('command') || codeEl.className.includes('language-command');

                // Match by EXACT text to bypass markdown class stripping issues
                const matchIndex = remainingCommands.findIndex(cmd => cmd.code.trim() === codeText);

                if (matchIndex !== -1) {
                    const cmd = remainingCommands[matchIndex];
                    const cmdSection = createCommandSection([cmd]);
                    preEl.parentNode.replaceChild(cmdSection, preEl);
                    remainingCommands.splice(matchIndex, 1);
                } else if (isCommandClass && remainingCommands.length > 0) {
                    const cmd = remainingCommands[0];
                    const cmdSection = createCommandSection([cmd]);
                    preEl.parentNode.replaceChild(cmdSection, preEl);
                    remainingCommands.shift();
                }
            });

            // Fallback for any commands that weren't found inline (so they don't vanish)
            if (remainingCommands.length > 0) {
                const fallbackSection = createCommandSection(remainingCommands);
                bubble.appendChild(fallbackSection);
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
   Command cards
   ═══════════════════════════════════════════════════════════════ */

function toggleCommandCard(headerElem) {
    const card = headerElem.closest('.command-card');
    card.classList.toggle('expanded');
    updateCommandCardTitle(card);
}

function updateCommandCardTitle(card) {
    const titleElem = card.querySelector('.command-header-title');
    const isExpanded = card.classList.contains('expanded');
    const statusText = card.dataset.statusText || 'PENDING APPROVAL';
    const statusColor = card.dataset.statusColor || 'var(--color-pending)';
    const commandText = card.dataset.commandText || '';

    if (isExpanded) {
        // Show status text when expanded
        titleElem.style.color = statusColor;
        updateHeaderTitleSmooth(titleElem, statusText, false);
    } else {
        // Show command text when collapsed
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

function createCommandSection(commands) {
    const cmdSection = document.createElement('div');
    cmdSection.className = 'command-section';
    commands.forEach((cmd) => {
        const commandCode = cmd.code || '';
        const card = document.createElement('div');
        card.className = 'command-card expanded';
        card.dataset.command = commandCode;

        // Set initial status data for title toggle
        card.dataset.commandText = commandCode;
        card.dataset.statusText = 'PENDING APPROVAL';
        card.dataset.statusColor = 'var(--color-pending)';

        const header = document.createElement('div');
        header.className = 'command-header';
        header.onclick = () => toggleCommandCard(header);
        header.innerHTML = `<div class="command-header-left"><div class="status-dot-wrapper"><span class="status-dot" style="background-color: var(--color-pending);"></span><span class="pulse-ring"></span></div><span class="command-header-title" style="color: var(--color-pending);">PENDING APPROVAL</span></div><svg class="command-arrow" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`;

        const bodyWrapper = document.createElement('div');
        bodyWrapper.className = 'command-body-wrapper';
        const body = document.createElement('div');
        body.className = 'command-body';
        const pre = document.createElement('pre');
        pre.className = 'command-code';
        pre.innerHTML = `<code class="code-text">${escapeHtml(commandCode)}</code><span class="cursor"></span>`;
        const btnRow = document.createElement('div');
        btnRow.className = 'command-btn-row';
        btnRow.innerHTML = `<button class="command-btn decline-btn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>Decline</button><button class="command-btn allow-btn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>Allow</button>`;
        const declineBtn = btnRow.querySelector('.decline-btn');
        const allowBtn = btnRow.querySelector('.allow-btn');
        const outputArea = document.createElement('div');
        outputArea.className = 'command-output-area';
        outputArea.innerHTML = '<div class="progress-bar"></div>';
        declineBtn.onclick = (e) => { e.stopPropagation(); handleDecline(card); };
        allowBtn.onclick = (e) => { e.stopPropagation(); handleAllow(card); };
        body.appendChild(pre); body.appendChild(btnRow); body.appendChild(outputArea);
        bodyWrapper.appendChild(body);
        card.appendChild(header); card.appendChild(bodyWrapper);
        cmdSection.appendChild(card);
    });
    return cmdSection;
}

function handleDecline(card) {
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
}

async function handleAllow(card) {
    const btnRow = card.querySelector('.command-btn-row');
    const outputArea = card.querySelector('.command-output-area');
    const cursor = card.querySelector('.cursor');
    const progressBar = outputArea.querySelector('.progress-bar');
    const titleElem = card.querySelector('.command-header-title');
    const statusDot = card.querySelector('.status-dot');
    const pulseRing = card.querySelector('.pulse-ring');
    const commandStr = card.dataset.command || '';
    isProcessing = true; sendBtn.disabled = true;
    if (cursor) cursor.classList.add('hidden');
    if (btnRow) btnRow.remove();
    if (pulseRing) pulseRing.remove();
    progressBar.classList.add('active');
    titleElem.style.color = 'var(--text-sub)';
    updateHeaderTitleSmooth(titleElem, 'EXECUTING…', false);
    try {
        const execResponse = await fetch('/api/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: commandStr }) });
        if (!execResponse.ok) throw new Error(`Server returned HTTP ${execResponse.status}`);
        const data = await execResponse.json();
        progressBar.classList.remove('active');
        let activeColor, stateText;
        if (data.exit_code === 0) { activeColor = 'var(--color-success)'; stateText = 'COMMAND EXECUTED'; }
        else { activeColor = 'var(--color-error)'; stateText = 'COMMAND FAILED'; }
        card.dataset.activeColor = activeColor; card.dataset.stateText = stateText;
        card.dataset.statusText = stateText;
        card.dataset.statusColor = activeColor;
        statusDot.style.backgroundColor = activeColor; titleElem.style.color = activeColor;
        let outputHTML = '<div class="command-output-block">';
        if (data.stdout) outputHTML += `<pre style="color: ${activeColor};">${escapeHtml(data.stdout)}</pre>`;
        if (data.stderr) outputHTML += `<pre style="color: var(--color-error);">${escapeHtml(data.stderr)}</pre>`;
        if (!data.stdout && !data.stderr) outputHTML += `<pre style="color: var(--text-muted);">(no output)</pre>`;
        outputHTML += '</div>';
        outputArea.innerHTML += outputHTML;
        card.classList.remove('expanded');
        updateCommandCardTitle(card);
        try {
            const fbResponse = await fetch('/api/ai-feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: commandStr, stdout: data.stdout, stderr: data.stderr, exit_code: data.exit_code }) });
            if (fbResponse.ok) {
                const fbData = await fbResponse.json();
                if (fbData.answer) addMessage('assistant', fbData.answer, fbData.thinking, fbData.commands || []);
            }
        } catch (fbError) { console.error('AI feedback failed:', fbError); }
    } catch (error) {
        progressBar.classList.remove('active');
        const errorColor = 'var(--color-error)';
        const errorText = 'COMMAND FAILED';
        card.dataset.statusText = errorText;
        card.dataset.statusColor = errorColor;
        statusDot.style.backgroundColor = errorColor; titleElem.style.color = errorColor;
        outputArea.innerHTML += `<div class="command-output-block"><pre style="color: var(--color-error);">Error: ${escapeHtml(error.message)}</pre></div>`;
        card.classList.remove('expanded');
        updateCommandCardTitle(card);
    } finally {
        isProcessing = false;
        sendBtn.disabled = !promptInput.value.trim();
        processNextQueueTask();
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
        { icon: '🔍', label: 'Searching', spin: false },
        { icon: '✏️', label: 'Writing', spin: false },
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
        track.offsetHeight;   // force reflow
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

promptInput.focus();