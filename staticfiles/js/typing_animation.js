// Typing animation, streaming helpers, and formatting utilities.

// ── URL / email → clickable links ────────────────────────────────────────────
function linkifyText(text) {
    const surigaoRe = /(surigaocity\.gov\.ph)/gi;
    const urlRe     = /(\b(https?:\/\/|www\.)[^\s<]+)/gi;
    const emailRe   = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/gi;

    const link = (href, label) =>
        `<a href="${href}" target="_blank" rel="noopener noreferrer"
            style="color:#1976d2;text-decoration:underline;font-weight:500;">${label}</a>`;

    text = text.replace(surigaoRe, (u) => link(`https://${u}`, u));
    text = text.replace(urlRe,     (u) => {
        if (u.includes('surigaocity.gov.ph')) return u;
        return link(u.startsWith('www.') ? 'https://' + u : u, u);
    });
    text = text.replace(emailRe, (e) =>
        `<a href="mailto:${e}" style="color:#1976d2;text-decoration:underline;">${e}</a>`
    );
    return text;
}

// ── Mirror of Python's _clean_response() in views.py ─────────────────────────
function normalizeText(raw) {
    const BULLET = '\u2022';
    const lines  = raw.split('\n');

    const pass1 = lines.map(line => {
        const sub = line.match(/^(\s+)([*+\-\u2022])\s+(.+)$/);
        if (sub) return `    ${BULLET} ${sub[3]}`;
        line = line.replace(/^\*(?!\*)\s+/, `${BULLET} `);
        line = line.replace(/^\+\s+/,       `${BULLET} `);
        line = line.replace(/^-(?!-)\s+/,   `${BULLET} `);
        return line;
    });

    const isBullet = s => /^\s*\u2022\s/.test(s) || /^\s*\d+\.\s/.test(s);
    const pass2 = [];
    let i = 0;
    while (i < pass1.length) {
        pass2.push(pass1[i]);
        if (i + 2 < pass1.length &&
            isBullet(pass1[i]) &&
            pass1[i + 1].trim() === '' &&
            isBullet(pass1[i + 2])) {
            i += 2;
        } else {
            i++;
        }
    }
    return pass2.join('\n');
}

// ── Full markdown → HTML ──────────────────────────────────────────────────────
function formatText(raw) {
    let t = normalizeText(raw);
    t = t.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
    if (/\*\*[^*]+$/.test(t)) t = t.replace(/\*\*([^*]+)$/, '<strong>$1</strong>');
    return linkifyText(t);
}

// ── Debounced scroll ──────────────────────────────────────────────────────────
let _scrollPending = false;
function scrollToBottom() {
    if (_scrollPending) return;
    _scrollPending = true;
    requestAnimationFrame(() => {
        document.getElementById('messagesContainer')
            ?.scrollTo({ top: 999999, behavior: 'smooth' });
        _scrollPending = false;
    });
}

// ── Streaming state ───────────────────────────────────────────────────────────
const _streamState = new WeakMap();

function initStreamBubble(bubbleEl) {
    bubbleEl.innerHTML = '';

    const textSpan = document.createElement('span');
    textSpan.className = 'typing-text';

    const dotsSpan = document.createElement('span');
    dotsSpan.className = 'typing-dots-inline';
    dotsSpan.innerHTML =
        '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

    bubbleEl.appendChild(textSpan);
    bubbleEl.appendChild(dotsSpan);

    _streamState.set(bubbleEl, { raw: '', textSpan, dotsSpan });
}

function appendStreamToken(bubbleEl, token) {
    const state = _streamState.get(bubbleEl);
    if (!state) return;
    state.raw += token;
    state.textSpan.innerHTML = formatText(state.raw);
    scrollToBottom();
}

function finalizeStreamedBubble(bubbleEl) {
    const state = _streamState.get(bubbleEl);
    if (!state) return;
    state.dotsSpan.remove();
    bubbleEl.innerHTML = formatText(state.raw);
    _streamState.delete(bubbleEl);
    scrollToBottom();
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function showTypingIndicator() {
    const container = document.getElementById('messagesContainer');
    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.id = 'typingIndicator';
    div.innerHTML = `
        <div class="message-avatar">
            <img src="/static/images/favicon.ico" alt="Charlie"
                 style="width:100%;height:100%;border-radius:50%;object-fit:cover;">
        </div>
        <div class="typing-dots-container">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function removeTypingIndicator() {
    document.getElementById('typingIndicator')?.remove();
}

// ── Typewriter effect for history messages ────────────────────────────────────
function typeMessage(element, text, speed = 10) {
    return new Promise(resolve => {
        element.innerHTML = '';

        const textSpan = document.createElement('span');
        textSpan.className = 'typing-text';

        const dotsSpan = document.createElement('span');
        dotsSpan.className = 'typing-dots-inline';
        dotsSpan.innerHTML =
            '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

        element.appendChild(textSpan);
        element.appendChild(dotsSpan);

        let idx = 0;
        let buf = '';

        function typeNext() {
            if (idx >= text.length) {
                dotsSpan.remove();
                element.innerHTML = formatText(buf);
                scrollToBottom();
                return resolve();
            }

            if (text[idx] === '*' && text[idx + 1] === '*') {
                buf += '**';
                idx += 2;
                textSpan.innerHTML = formatText(buf);
                scrollToBottom();
                return typeNext();
            }

            buf += text[idx++];
            textSpan.innerHTML = formatText(buf);
            scrollToBottom();
            setTimeout(typeNext, speed);
        }

        typeNext();
    });
}