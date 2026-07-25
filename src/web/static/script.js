const chatArea = document.getElementById('chat-area');
const chatContainer = document.getElementById('chat-container');
const promptInput = document.getElementById('prompt');
const sendBtn = document.getElementById('send-btn');

let animationActive = false;
let isProcessing = false;

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    sendBtn.disabled = !textarea.value.trim() || isProcessing;
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!isProcessing) {
            sendMessage();
        }
    }
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function stripCommandBlocks(markdown) {
    return markdown.replace(/```command[\s\S]*?```/g, '');
}

function addMessage(role, content, thinking = '', commands = []) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (thinking && role === 'assistant') {
        const details = document.createElement('details');
        details.className = 'thinking-block';
        details.innerHTML = `
            <summary>
                <span>Thinking</span>
                <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
            </summary>
        `;
        const thinkingContent = document.createElement('div');
        thinkingContent.className = 'thinking-block-content';
        thinkingContent.textContent = thinking;  // plain text — no markdown parsing
        details.appendChild(thinkingContent);
        contentDiv.appendChild(details);
    }

    let displayContent = content;
    if (commands && commands.length > 0) {
        displayContent = stripCommandBlocks(content);
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (role === 'assistant') {
        bubble.innerHTML = marked.parse(displayContent);
    } else {
        bubble.textContent = displayContent;
    }
    contentDiv.appendChild(bubble);

    if (commands && commands.length > 0) {
        contentDiv.appendChild(createCommandSection(commands));
    }

    row.appendChild(contentDiv);
    chatArea.appendChild(row);
    scrollToBottom();
}

/* ── Command Card ── */

function toggleCommandCard(headerElem) {
    const card = headerElem.closest('.command-card');
    card.classList.toggle('expanded');
}

function updateHeaderTitleSmooth(titleElem, newText, isCommand) {
    titleElem.classList.add('fading');
    setTimeout(() => {
        titleElem.textContent = newText;
        if (isCommand) {
            titleElem.classList.add('is-command');
        } else {
            titleElem.classList.remove('is-command');
        }
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

        // Header
        const header = document.createElement('div');
        header.className = 'command-header';
        header.onclick = () => toggleCommandCard(header);
        header.innerHTML = `
            <div class="command-header-left">
                <div class="status-dot-wrapper">
                    <span class="status-dot" style="background-color: var(--color-pending);"></span>
                    <span class="pulse-ring"></span>
                </div>
                <span class="command-header-title" style="color: var(--color-pending);">PENDING APPROVAL</span>
            </div>
            <svg class="command-arrow" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
        `;

        // Body wrapper
        const bodyWrapper = document.createElement('div');
        bodyWrapper.className = 'command-body-wrapper';

        const body = document.createElement('div');
        body.className = 'command-body';

        // Code
        const pre = document.createElement('pre');
        pre.className = 'command-code';
        pre.innerHTML = `<code class="code-text">${escapeHtml(commandCode)}</code><span class="cursor"></span>`;

        // Buttons
        const btnRow = document.createElement('div');
        btnRow.className = 'command-btn-row';
        btnRow.innerHTML = `
            <button class="command-btn decline-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
                Decline
            </button>
            <button class="command-btn allow-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                Allow
            </button>
        `;

        const declineBtn = btnRow.querySelector('.decline-btn');
        const allowBtn = btnRow.querySelector('.allow-btn');

        // Output area
        const outputArea = document.createElement('div');
        outputArea.className = 'command-output-area';
        outputArea.innerHTML = '<div class="progress-bar"></div>';

        declineBtn.onclick = (e) => {
            e.stopPropagation();
            handleDecline(card);
        };

        allowBtn.onclick = (e) => {
            e.stopPropagation();
            handleAllow(card);
        };

        body.appendChild(pre);
        body.appendChild(btnRow);
        body.appendChild(outputArea);
        bodyWrapper.appendChild(body);

        card.appendChild(header);
        card.appendChild(bodyWrapper);
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

    statusDot.style.backgroundColor = activeColor;
    titleElem.style.color = activeColor;

    card.classList.remove('expanded');
    updateHeaderTitleSmooth(titleElem, `$ ${commandStr}`, true);
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

    // UI: start execution
    if (cursor) cursor.classList.add('hidden');
    if (btnRow) btnRow.remove();
    if (pulseRing) pulseRing.remove();

    progressBar.classList.add('active');
    titleElem.style.color = 'var(--text-sub)';
    updateHeaderTitleSmooth(titleElem, 'EXECUTING…', false);

    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: commandStr }),
        });

        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }

        const data = await response.json();
        progressBar.classList.remove('active');

        // Determine state from exit code
        let activeColor, stateText;
        if (data.exit_code === 0) {
            activeColor = 'var(--color-success)';
            stateText = 'COMMAND EXECUTED';
        } else {
            activeColor = 'var(--color-error)';
            stateText = 'COMMAND FAILED';
        }

        card.dataset.activeColor = activeColor;
        card.dataset.stateText = stateText;

        statusDot.style.backgroundColor = activeColor;
        titleElem.style.color = activeColor;

        // Pure terminal output — no exit code badges
        let outputHTML = '<div class="command-output-block">';
        if (data.stdout) {
            outputHTML += `<pre style="color: ${activeColor};">${escapeHtml(data.stdout)}</pre>`;
        }
        if (data.stderr) {
            outputHTML += `<pre style="color: var(--color-error);">${escapeHtml(data.stderr)}</pre>`;
        }
        if (!data.stdout && !data.stderr) {
            outputHTML += `<pre style="color: var(--text-muted);">(no output)</pre>`;
        }
        outputHTML += '</div>';

        outputArea.innerHTML += outputHTML;

    } catch (error) {
        progressBar.classList.remove('active');

        const activeColor = 'var(--color-error)';
        const stateText = 'CONNECTION ERROR';

        card.dataset.activeColor = activeColor;
        card.dataset.stateText = stateText;

        statusDot.style.backgroundColor = activeColor;
        titleElem.style.color = activeColor;

        outputArea.innerHTML += `
            <div class="command-output-block">
                <pre style="color: ${activeColor};">Error: ${escapeHtml(error.message)}</pre>
            </div>
        `;
    }

    // Collapse and show command in header
    card.classList.remove('expanded');
    updateHeaderTitleSmooth(titleElem, `$ ${commandStr}`, true);
}

/* ── Loading / Portal ── */

function showLoading() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.id = 'loading-indicator';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `
        <div class="portal-oval">
            <div class="inner-content">
                <div id="portal-track" class="track"></div>
            </div>
        </div>
    `;

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

    function createItem(state) {
        const div = document.createElement('div');
        div.className = 'item';
        div.innerHTML = `
            <div class="icon ${state.spin ? 'spin' : ''}">${state.icon}</div>
            <div class="label"></div>
        `;
        return div;
    }

    let currentItem = createItem(states[index]);
    track.appendChild(currentItem);

    while (animationActive && document.getElementById('portal-track')) {
        const labelEl = currentItem.querySelector('.label');
        const text = states[index].label + "...";

        for (let char of text) {
            if (!animationActive) break;
            labelEl.textContent += char;
            await new Promise(r => setTimeout(r, 40));
        }

        await new Promise(r => setTimeout(r, 800));
        if (!animationActive) break;

        index = (index + 1) % states.length;
        let nextItem = createItem(states[index]);
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

async function sendMessage() {
    if (isProcessing) return;

    const prompt = promptInput.value.trim();
    if (!prompt) return;

    isProcessing = true;
    addMessage('user', prompt);

    promptInput.value = '';
    promptInput.style.height = 'auto';
    sendBtn.disabled = true;

    showLoading();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt }),
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
        contentDiv.innerHTML = `
            <div class="bubble" style="color: var(--accent-red); border: 1px solid var(--accent-red); padding: 10px 14px; border-radius: 12px;">
                Error: ${error.message}
            </div>
        `;
        errorDiv.appendChild(contentDiv);
        chatArea.appendChild(errorDiv);
        scrollToBottom();
    } finally {
        isProcessing = false;
        sendBtn.disabled = !promptInput.value.trim();
        promptInput.focus();
    }
}

promptInput.focus();