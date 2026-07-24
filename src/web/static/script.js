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
            <div class="thinking-block-content">${escapeHtml(thinking)}</div>
        `;
        contentDiv.appendChild(details);
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (role === 'assistant') {
        bubble.innerHTML = marked.parse(content);
    } else {
        bubble.textContent = content;
    }

    contentDiv.appendChild(bubble);

    // Command cards (Gemini's integration)
    if (commands && commands.length > 0) {
        contentDiv.appendChild(createCommandSection(commands));
    }

    row.appendChild(contentDiv);
    chatArea.appendChild(row);
    scrollToBottom();
}

/**
 * Toggles expand/collapse state for collapsible command cards.
 */
function toggleCommandCard(headerElem) {
    const card = headerElem.closest('.command-card');
    if (card) {
        card.classList.toggle('expanded');
    }
}

/**
 * Creates the DOM container for inline assistant commands.
 * @param {Array<{code: string}>} commands 
 * @returns {HTMLElement}
 */
function createCommandSection(commands) {
    const cmdSection = document.createElement('div');
    cmdSection.className = 'command-section';

    commands.forEach((cmd) => {
        const commandCode = cmd.code || '';
        const isLong = commandCode.length > 80;

        const card = document.createElement('div');
        card.className = `command-card ${isLong ? 'collapsible' : 'expanded'}`;

        // Header for collapsible commands
        if (isLong) {
            const header = document.createElement('div');
            header.className = 'command-header';
            header.onclick = () => toggleCommandCard(header);
            header.innerHTML = `
                <span class="command-header-title">Command</span>
                <svg class="command-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
            `;
            card.appendChild(header);
        }

        // Card Body
        const body = document.createElement('div');
        body.className = 'command-body';

        const pre = document.createElement('pre');
        pre.className = 'command-code';
        const codeElem = document.createElement('code');
        codeElem.textContent = commandCode;
        pre.appendChild(codeElem);

        const runBtn = document.createElement('button');
        runBtn.className = 'command-run-btn';
        runBtn.textContent = 'Run';

        const outputArea = document.createElement('div');
        outputArea.className = 'command-output-area';

        runBtn.onclick = () => runCommand(commandCode, runBtn, outputArea);

        body.appendChild(pre);
        body.appendChild(runBtn);
        body.appendChild(outputArea);
        card.appendChild(body);

        cmdSection.appendChild(card);
    });

    return cmdSection;
}

/**
 * Handles executing the command via API call and displaying output/errors.
 */
async function runCommand(commandText, buttonElem, outputContainer) {
    buttonElem.disabled = true;
    buttonElem.textContent = 'Running…';
    outputContainer.innerHTML = '';

    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: commandText }),
        });

        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }

        const data = await response.json();

        const outputBlock = document.createElement('div');
        outputBlock.className = 'command-output-block';

        if (data.stdout) {
            const stdoutPre = document.createElement('pre');
            stdoutPre.className = 'stdout';
            stdoutPre.textContent = data.stdout;
            outputBlock.appendChild(stdoutPre);
        }

        if (data.stderr) {
            const stderrPre = document.createElement('pre');
            stderrPre.className = 'stderr';
            stderrPre.textContent = data.stderr;
            outputBlock.appendChild(stderrPre);
        }

        const exitCodeSpan = document.createElement('span');
        exitCodeSpan.className = 'exit-code';
        exitCodeSpan.textContent = `Exit code: ${data.exit_code ?? 0}`;
        outputBlock.appendChild(exitCodeSpan);

        outputContainer.appendChild(outputBlock);
    } catch (error) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'command-output-error';
        errorDiv.textContent = `Error: ${error.message}`;
        outputContainer.appendChild(errorDiv);
    } finally {
        buttonElem.disabled = false;
        buttonElem.textContent = 'Run';
        scrollToBottom();
    }
}

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