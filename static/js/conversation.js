// conversation.js — layout, history, edit, pagination, browser-close privacy,
//                   dark mode, conversation search

// ── Icons ──────────────────────────────────────────────────────────────────
const ICON_COPY  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_EDIT  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
const ICON_MOON  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
const ICON_SUN   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;

// ── Edit history — backed by sessionStorage ────────────────────────────────
function _ehGet(messageId) {
    try {
        const raw = sessionStorage.getItem('editHistory:' + messageId);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (parsed.length > 0 && typeof parsed[0] === 'string') {
            return parsed.map(s => ({ userText: s, botText: '' }));
        }
        return parsed;
    } catch { return null; }
}
function _ehSet(messageId, versions) {
    try { sessionStorage.setItem('editHistory:' + messageId, JSON.stringify(versions)); } catch {}
}
function _eiGet(messageId) {
    const v = sessionStorage.getItem('editCurrentIdx:' + messageId);
    return v !== null ? Number(v) : null;
}
function _eiSet(messageId, idx) {
    try { sessionStorage.setItem('editCurrentIdx:' + messageId, String(idx)); } catch {}
}
function _clearAllEditHistory() {
    const toRemove = [];
    for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && (k.startsWith('editHistory:') || k.startsWith('editCurrentIdx:'))) {
            toRemove.push(k);
        }
    }
    toRemove.forEach(k => sessionStorage.removeItem(k));
}

// ── DOMContentLoaded ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const chatInput         = document.getElementById('chatInput');
    const messagesContainer = document.getElementById('messagesContainer');
    const scrollTopBtn      = document.getElementById('scrollTopBtn');

    // ── Auto-expand textarea ────────────────────────────────────────────────
    chatInput.addEventListener('input', function () {
        this.style.height = '45px';
        const scrollHeight = this.scrollHeight;
        if (scrollHeight > 120) {
            this.style.height = '120px';
            this.classList.add('scrollable');
        } else {
            this.style.height = scrollHeight + 'px';
            this.classList.remove('scrollable');
        }
        adjustLayout();
    });

    // ── Scroll-to-top button ────────────────────────────────────────────────
    messagesContainer.addEventListener('scroll', function () {
        scrollTopBtn.classList.toggle('show', messagesContainer.scrollTop > 300);
    });

    scrollTopBtn.addEventListener('click', function () {
        messagesContainer.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // ── Initialize dark mode, search, page ─────────────────────────────────
    initDarkMode();
    initSearch();
    initializePage();
});

// ══════════════════════════════════════════════════════════════════════════════
// DARK MODE
// ══════════════════════════════════════════════════════════════════════════════
function initDarkMode() {
    const toggle = document.getElementById('darkModeToggle');
    const isDark = localStorage.getItem('charlieDarkMode') === 'true';

    // Apply saved preference immediately (before paint)
    if (isDark) {
        document.body.classList.add('dark');
        toggle.innerHTML = ICON_SUN;
        toggle.setAttribute('title', 'Switch to light mode');
    } else {
        toggle.innerHTML = ICON_MOON;
        toggle.setAttribute('title', 'Switch to dark mode');
    }

    toggle.addEventListener('click', () => {
        const nowDark = document.body.classList.toggle('dark');
        localStorage.setItem('charlieDarkMode', String(nowDark));
        toggle.innerHTML = nowDark ? ICON_SUN : ICON_MOON;
        toggle.setAttribute('title', nowDark ? 'Switch to light mode' : 'Switch to dark mode');
    });
}

// ══════════════════════════════════════════════════════════════════════════════
// CONVERSATION SEARCH
// ══════════════════════════════════════════════════════════════════════════════
let _searchMatches    = [];
let _searchCurrentIdx = -1;
const _savedBubbleHTML = new Map(); // bubble element → original innerHTML

function _escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Walk text nodes inside an element and wrap term matches with <mark>
// Returns true if at least one match was found
function _highlightTextNodes(element, term) {
    const walker    = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let node;
    while ((node = walker.nextNode())) textNodes.push(node);

    const regex  = new RegExp(_escapeRegex(term), 'gi');
    let   found  = false;

    textNodes.forEach(textNode => {
        if (!regex.test(textNode.textContent)) return;
        regex.lastIndex = 0; // reset after test()
        found = true;
        const wrapper = document.createElement('span');
        wrapper.innerHTML = textNode.textContent.replace(
            regex,
            match => `<mark class="search-highlight">${match}</mark>`
        );
        textNode.parentNode.replaceChild(wrapper, textNode);
    });

    return found;
}

function _clearSearchHighlights() {
    // Restore every bubble we touched
    _savedBubbleHTML.forEach((html, bubble) => {
        bubble.innerHTML = html;
    });
    _savedBubbleHTML.clear();

    // Un-dim all messages
    document.querySelectorAll('#messagesContainer .message.search-dim').forEach(m => {
        m.classList.remove('search-dim');
    });

    _searchMatches    = [];
    _searchCurrentIdx = -1;
}

function _performSearch(term) {
    _clearSearchHighlights();

    const counter  = document.getElementById('searchCounter');
    const prevBtn  = document.getElementById('searchPrev');
    const nextBtn  = document.getElementById('searchNext');

    if (!term.trim()) {
        counter.textContent = '';
        counter.classList.remove('no-results');
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
    }

    const messages = document.querySelectorAll('#messagesContainer .message');

    messages.forEach(msgDiv => {
        const bubble = msgDiv.querySelector('.message-bubble');
        if (!bubble) return;

        // Don't search inside an active edit textarea
        if (bubble.classList.contains('editing')) return;

        _savedBubbleHTML.set(bubble, bubble.innerHTML);
        const found = _highlightTextNodes(bubble, term);

        if (found) {
            msgDiv.classList.remove('search-dim');
        } else {
            msgDiv.classList.add('search-dim');
        }
    });

    // Collect all highlight marks
    _searchMatches = Array.from(
        document.querySelectorAll('#messagesContainer mark.search-highlight')
    );

    if (_searchMatches.length > 0) {
        _searchCurrentIdx = 0;
        _activateMatch(0);
        prevBtn.disabled = false;
        nextBtn.disabled = false;
    } else {
        _searchCurrentIdx = -1;
        counter.textContent = 'No results';
        counter.classList.add('no-results');
        prevBtn.disabled = true;
        nextBtn.disabled = true;
    }
}

function _activateMatch(idx) {
    const counter = document.getElementById('searchCounter');
    _searchMatches.forEach(m => m.classList.remove('active'));
    if (idx < 0 || idx >= _searchMatches.length) return;

    const match = _searchMatches[idx];
    match.classList.add('active');
    match.scrollIntoView({ behavior: 'smooth', block: 'center' });

    counter.textContent = `${idx + 1} of ${_searchMatches.length}`;
    counter.classList.remove('no-results');
}

function openSearch() {
    const container = document.getElementById('searchBarContainer');
    const input     = document.getElementById('searchInput');
    container.classList.add('visible');
    adjustLayout();
    // Small delay so the transition plays before focusing
    setTimeout(() => input.focus(), 50);
}

function closeSearch() {
    const container = document.getElementById('searchBarContainer');
    const input     = document.getElementById('searchInput');
    container.classList.remove('visible');
    input.value = '';
    _clearSearchHighlights();
    const counter = document.getElementById('searchCounter');
    if (counter) { counter.textContent = ''; counter.classList.remove('no-results'); }
    const prevBtn = document.getElementById('searchPrev');
    const nextBtn = document.getElementById('searchNext');
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    adjustLayout();
}

function initSearch() {
    const toggleBtn = document.getElementById('searchToggleBtn');
    const closeBtn  = document.getElementById('searchClose');
    const prevBtn   = document.getElementById('searchPrev');
    const nextBtn   = document.getElementById('searchNext');
    const input     = document.getElementById('searchInput');

    toggleBtn.addEventListener('click', () => {
        const container = document.getElementById('searchBarContainer');
        if (container.classList.contains('visible')) {
            closeSearch();
        } else {
            openSearch();
        }
    });

    closeBtn.addEventListener('click', closeSearch);

    input.addEventListener('input', () => _performSearch(input.value));

    prevBtn.addEventListener('click', () => {
        if (_searchMatches.length === 0) return;
        _searchCurrentIdx = (_searchCurrentIdx - 1 + _searchMatches.length) % _searchMatches.length;
        _activateMatch(_searchCurrentIdx);
    });

    nextBtn.addEventListener('click', () => {
        if (_searchMatches.length === 0) return;
        _searchCurrentIdx = (_searchCurrentIdx + 1) % _searchMatches.length;
        _activateMatch(_searchCurrentIdx);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (_searchMatches.length === 0) return;
            if (e.shiftKey) {
                _searchCurrentIdx = (_searchCurrentIdx - 1 + _searchMatches.length) % _searchMatches.length;
            } else {
                _searchCurrentIdx = (_searchCurrentIdx + 1) % _searchMatches.length;
            }
            _activateMatch(_searchCurrentIdx);
        }
        if (e.key === 'Escape') closeSearch();
    });

    // Intercept Ctrl+F / Cmd+F
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            // Only intercept if not typing in the chat input
            if (document.activeElement === document.getElementById('chatInput')) return;
            e.preventDefault();
            openSearch();
        }
    });
}

// ── Page initialization with browser-close privacy ────────────────────────
async function initializePage() {
    const SESSION_FLAG = 'charlieSessionActive';

    if (!sessionStorage.getItem(SESSION_FLAG)) {
        try {
            await fetch('/api/delete-conversation/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
            });
        } catch (e) {
            console.warn('Could not clear previous session:', e);
        }
        _clearAllEditHistory();
    }

    sessionStorage.setItem(SESSION_FLAG, 'true');
    await loadConversationHistory();
}

// ── Layout adjustment ──────────────────────────────────────────────────────
function adjustLayout() {
    const messagesContainer = document.getElementById('messagesContainer');
    const inputContainer    = document.querySelector('.input-container');
    const navbar            = document.querySelector('.navbar');
    const searchBar         = document.getElementById('searchBarContainer');

    const navHeight    = navbar.offsetHeight;
    const searchHeight = (searchBar && searchBar.classList.contains('visible'))
        ? searchBar.offsetHeight
        : 0;

    messagesContainer.style.top    = (navHeight + searchHeight) + 'px';
    messagesContainer.style.bottom = inputContainer.offsetHeight + 'px';
}

// ── Show share button once a full exchange exists ──────────────────────────
function checkAndShowShareButton() {
    const shareButton = document.getElementById('shareButton');
    if (!shareButton) return;
    const messages = document.querySelectorAll('#messagesContainer .message');
    const hasUser  = [...messages].some(m => m.classList.contains('user'));
    const hasBot   = [...messages].some(m => m.classList.contains('bot'));
    if (hasUser && hasBot) shareButton.classList.add('visible');
}

// ── Load conversation history from DB ─────────────────────────────────────
async function loadConversationHistory() {
    try {
        const response = await fetch('/api/load-history/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
        });

        const data = await response.json();

        if (data.status === 'success' && data.messages && data.messages.length > 0) {
            const emptyState = document.getElementById('emptyState');
            if (emptyState) emptyState.classList.add('hidden');

            for (const msg of data.messages) {
                addMessageToUI(
                    msg.content,
                    msg.role === 'user',
                    msg.id ? String(msg.id) : null
                );
            }

            // Second pass: restore pagination + correct version display
            const container = document.getElementById('messagesContainer');
            for (const msg of data.messages) {
                if (msg.role !== 'user' || !msg.id) continue;
                const mid      = String(msg.id);
                const versions = _ehGet(mid);
                const idx      = _eiGet(mid);
                if (!versions || versions.length <= 1 || idx === null) continue;

                const userDiv = [...container.querySelectorAll('.message.user')]
                    .find(d => d.dataset.messageId === mid);
                if (!userDiv) continue;

                const ver        = versions[idx];
                const userBubble = userDiv.querySelector('.message-bubble');
                if (userBubble) userBubble.innerHTML = ver.userText;

                const botDiv = _getNextBotDiv(userDiv);
                if (botDiv && ver.botText) {
                    botDiv.querySelector('.message-bubble').innerHTML = ver.botText;
                }
                _renderPagination(userDiv, mid);
            }

            scrollToBottom();
            checkAndShowShareButton();
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// ── Copy message text ──────────────────────────────────────────────────────
function copyMessageText(bubble, btn) {
    const text = (bubble.innerText || bubble.textContent).trim();

    const doConfirm = () => {
        btn.innerHTML = ICON_CHECK;
        btn.setAttribute('data-tip', 'Copied!');
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = ICON_COPY;
            btn.setAttribute('data-tip', 'Copy message');
            btn.classList.remove('copied');
        }, 3000);
    };

    const execFallback = () => {
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity  = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            doConfirm();
        } catch (e) {
            console.error('Copy failed:', e);
        }
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(doConfirm).catch(execFallback);
    } else {
        execFallback();
    }
}

// ── Add message to UI ──────────────────────────────────────────────────────
function addMessageToUI(content, isUser = false, messageId = null) {
    const messagesContainer = document.getElementById('messagesContainer');
    const emptyState        = document.getElementById('emptyState');

    if (emptyState && !emptyState.classList.contains('hidden')) {
        emptyState.classList.add('hidden');
    }

    const messageDiv     = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
    if (messageId) messageDiv.dataset.messageId = messageId;

    const avatarHtml = isUser
        ? `<div class="message-avatar">
               <img src="/static/images/user-profile.png" alt="User"
                    style="width:100%;height:100%;border-radius:50%;object-fit:cover;">
           </div>`
        : `<div class="message-avatar">
               <img src="/static/images/favicon.ico" alt="Charlie"
                    style="width:100%;height:100%;border-radius:50%;object-fit:cover;">
           </div>`;

    // ── FIX: Bot messages must go through the full formatText pipeline       ──
    // (normalizeText → bold → linkify) so bullet formatting is identical      ──
    // whether the message arrives via live streaming or history load from DB.  ──
    // Previously only **bold** was applied here, leaving raw "* " bullets      ──
    // untouched whenever content was loaded from the database.                 ──
    let displayContent = content;
    if (!isUser) {
        displayContent = formatText(content);
    }

    const actionsHtml = isUser
        ? `<div class="message-actions">
               <button class="message-action-btn copy-btn" data-tip="Copy message">${ICON_COPY}</button>
               <button class="message-action-btn edit-btn" data-tip="Edit message">${ICON_EDIT}</button>
           </div>`
        : `<div class="message-actions">
               <button class="message-action-btn copy-btn" data-tip="Copy message">${ICON_COPY}</button>
           </div>`;

    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            <div class="message-bubble">${displayContent}</div>
            <div class="message-meta">
                <div class="message-time">${getCurrentTime()}</div>
                ${actionsHtml}
            </div>
        </div>
    `;

    const copyBtn = messageDiv.querySelector('.copy-btn');
    const bubble  = messageDiv.querySelector('.message-bubble');
    copyBtn.addEventListener('click', () => copyMessageText(bubble, copyBtn));

    if (isUser) {
        const editBtn = messageDiv.querySelector('.edit-btn');
        editBtn.addEventListener('click', () => {
            const mid = messageDiv.dataset.messageId;
            if (!mid) return;
            startEditing(messageDiv, bubble, mid);
        });
    }

    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

// ── Edit: start ────────────────────────────────────────────────────────────
function startEditing(messageDiv, bubble, messageId) {
    if (bubble.classList.contains('editing')) return;

    const originalText = (bubble.innerText || bubble.textContent).trim();
    bubble.dataset.originalContent = bubble.innerHTML;
    bubble.dataset.originalText    = originalText;

    const copyBtn = messageDiv.querySelector('.copy-btn');
    const editBtn = messageDiv.querySelector('.edit-btn');
    if (copyBtn) copyBtn.disabled = true;
    if (editBtn) editBtn.disabled = true;

    bubble.style.width = bubble.offsetWidth + 'px';

    const textarea     = document.createElement('textarea');
    textarea.className = 'edit-textarea';
    textarea.value     = originalText;

    bubble.innerHTML = '';
    bubble.appendChild(textarea);
    bubble.classList.add('editing');

    autoResizeEditTextarea(textarea);
    textarea.addEventListener('input', () => autoResizeEditTextarea(textarea));
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    const messageContent = messageDiv.querySelector('.message-content');
    const metaRow        = messageDiv.querySelector('.message-meta');
    const editActions    = document.createElement('div');
    editActions.className = 'edit-actions';
    editActions.innerHTML = `
        <button class="edit-save-btn" disabled>Save</button>
        <button class="edit-cancel-btn">Cancel</button>
    `;
    messageContent.insertBefore(editActions, metaRow);

    const saveBtn   = editActions.querySelector('.edit-save-btn');
    const cancelBtn = editActions.querySelector('.edit-cancel-btn');

    textarea.addEventListener('input', () => {
        const current    = textarea.value.trim();
        saveBtn.disabled = current === originalText || current === '';
    });

    cancelBtn.addEventListener('click', () => {
        cancelEdit(messageDiv, bubble, editActions);
    });

    saveBtn.addEventListener('click', async () => {
        const newText = textarea.value.trim();
        if (saveBtn.disabled) return;
        await saveEdit(messageDiv, bubble, editActions, messageId, originalText, newText);
    });
}

// ── Edit: auto-resize textarea ─────────────────────────────────────────────
function autoResizeEditTextarea(textarea) {
    textarea.style.height = 'auto';
    const maxHeight = 22 * 6;
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.height    = maxHeight + 'px';
        textarea.style.overflowY = 'auto';
    } else {
        textarea.style.height    = textarea.scrollHeight + 'px';
        textarea.style.overflowY = 'hidden';
    }
}

// ── Edit: cancel ───────────────────────────────────────────────────────────
function cancelEdit(messageDiv, bubble, editActions) {
    bubble.innerHTML = bubble.dataset.originalContent || '';
    bubble.classList.remove('editing');
    bubble.style.width = '';
    delete bubble.dataset.originalContent;
    delete bubble.dataset.originalText;
    editActions.remove();

    const copyBtn = messageDiv.querySelector('.copy-btn');
    const editBtn = messageDiv.querySelector('.edit-btn');
    if (copyBtn) copyBtn.disabled = false;
    if (editBtn) editBtn.disabled = false;
}

// ── Edit: save ─────────────────────────────────────────────────────────────
async function saveEdit(messageDiv, bubble, editActions, messageId, originalText, newText) {
    const saveBtn = editActions.querySelector('.edit-save-btn');
    saveBtn.disabled    = true;
    saveBtn.textContent = 'Saving…';

    try {
        const res  = await fetch('/api/edit-message/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ message_id: Number(messageId), new_content: newText }),
        });
        const data = await res.json();

        if (data.status !== 'success') throw new Error(data.error || 'Save failed');

        bubble.innerHTML = newText;
        bubble.classList.remove('editing');
        bubble.style.width = '';
        delete bubble.dataset.originalContent;
        delete bubble.dataset.originalText;
        editActions.remove();

        const copyBtn = messageDiv.querySelector('.copy-btn');
        const editBtn = messageDiv.querySelector('.edit-btn');
        if (copyBtn) copyBtn.disabled = false;
        if (editBtn) editBtn.disabled = false;

        const oldBotDiv  = _getNextBotDiv(messageDiv);
        const oldBotHTML = oldBotDiv ? oldBotDiv.querySelector('.message-bubble').innerHTML : '';
        _addToEditHistory(messageDiv, messageId, originalText, newText, oldBotHTML);

        removeMessagesAfter(messageDiv);

        const shareButton = document.getElementById('shareButton');
        if (shareButton) shareButton.classList.remove('visible');

        if (typeof sendAfterEdit === 'function') {
            await sendAfterEdit(messageId);
        }

    } catch (err) {
        console.error('Edit save error:', err);
        saveBtn.disabled    = false;
        saveBtn.textContent = 'Save';
        alert('Failed to save. Please try again.');
    }
}

// ── Remove all messages after a given message div ─────────────────────────
function removeMessagesAfter(messageDiv) {
    const container   = document.getElementById('messagesContainer');
    const allMessages = Array.from(container.querySelectorAll('.message'));
    const idx         = allMessages.indexOf(messageDiv);
    if (idx === -1) return;
    for (let i = idx + 1; i < allMessages.length; i++) {
        allMessages[i].remove();
    }
}

// ── Edit history + pagination ──────────────────────────────────────────────
function _addToEditHistory(messageDiv, messageId, oldText, newText, oldBotHTML = '') {
    let versions = _ehGet(messageId);
    if (!versions) {
        versions = [{ userText: oldText, botText: oldBotHTML }];
    }
    versions.push({ userText: newText, botText: null });
    _ehSet(messageId, versions);
    _eiSet(messageId, versions.length - 1);
    _renderPagination(messageDiv, messageId);
}

function _fillLastBotText(messageId, botHTML) {
    const versions = _ehGet(messageId);
    if (!versions || versions.length === 0) return;
    versions[versions.length - 1].botText = botHTML || '';
    _ehSet(messageId, versions);
}

function _getNextBotDiv(userMsgDiv) {
    const container = document.getElementById('messagesContainer');
    const all       = Array.from(container.querySelectorAll('.message'));
    const idx       = all.indexOf(userMsgDiv);
    if (idx === -1 || idx + 1 >= all.length) return null;
    const next = all[idx + 1];
    return next.classList.contains('bot') ? next : null;
}

function _renderPagination(messageDiv, messageId) {
    const versions   = _ehGet(messageId);
    const currentIdx = _eiGet(messageId);
    if (!versions || currentIdx === null) return;
    const total   = versions.length;
    const current = currentIdx + 1;

    const existing = messageDiv.querySelector('.edit-pagination');
    if (existing) existing.remove();

    const pagination         = document.createElement('div');
    pagination.className     = 'edit-pagination';
    pagination.dataset.msgId = messageId;
    pagination.innerHTML     = `
        <button class="page-prev" ${currentIdx === 0 ? 'disabled' : ''}>&#8249;</button>
        <span class="page-indicator">${current}/${total}</span>
        <button class="page-next" ${currentIdx === total - 1 ? 'disabled' : ''}>&#8250;</button>
    `;

    const messageContent = messageDiv.querySelector('.message-content');
    messageContent.appendChild(pagination);

    const prevBtn    = pagination.querySelector('.page-prev');
    const nextBtn    = pagination.querySelector('.page-next');
    const userBubble = messageDiv.querySelector('.message-bubble');

    function applyVersion(idx) {
        const ver = _ehGet(messageId)[idx];
        if (!ver) return;
        userBubble.innerHTML = ver.userText;
        const botDiv = _getNextBotDiv(messageDiv);
        if (botDiv) {
            botDiv.querySelector('.message-bubble').innerHTML = ver.botText || '';
        }
    }

    prevBtn.addEventListener('click', () => {
        const newIdx = _eiGet(messageId) - 1;
        if (newIdx < 0) return;
        _eiSet(messageId, newIdx);
        applyVersion(newIdx);
        _renderPagination(messageDiv, messageId);
    });

    nextBtn.addEventListener('click', () => {
        const newIdx = _eiGet(messageId) + 1;
        if (newIdx >= total) return;
        _eiSet(messageId, newIdx);
        applyVersion(newIdx);
        _renderPagination(messageDiv, messageId);
    });
}

// ── Helpers ────────────────────────────────────────────────────────────────
function getCurrentTime() {
    const now     = new Date();
    let hours     = now.getHours();
    let minutes   = now.getMinutes();
    const ampm    = hours >= 12 ? 'PM' : 'AM';
    hours         = hours % 12 || 12;
    minutes       = minutes < 10 ? '0' + minutes : minutes;
    return `${hours}:${minutes} ${ampm}`;
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        for (const cookie of document.cookie.split(';')) {
            const c = cookie.trim();
            if (c.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(c.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}