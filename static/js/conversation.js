// conversation.js — layout, history, edit, pagination, browser-close privacy

// ── Icons ──────────────────────────────────────────────────────────────────
const ICON_COPY  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_EDIT  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;

// ── Edit history — backed by sessionStorage so it survives F5 ─────────────
// sessionStorage is cleared automatically when the browser (all tabs) closes.
// Key format:  editHistory:{messageId}   → JSON array of version strings
//              editCurrentIdx:{messageId} → number

function _ehGet(messageId) {
    try {
        const raw = sessionStorage.getItem('editHistory:' + messageId);
        return raw ? JSON.parse(raw) : null;
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
    // Remove only our edit-history keys so other sessionStorage data is untouched
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
        if (messagesContainer.scrollTop > 300) {
            scrollTopBtn.classList.add('show');
        } else {
            scrollTopBtn.classList.remove('show');
        }
    });

    scrollTopBtn.addEventListener('click', function () {
        messagesContainer.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // ── Initialize page (privacy + history load) ────────────────────────────
    initializePage();
});

// ── Page initialization with browser-close privacy ────────────────────────
async function initializePage() {
    const SESSION_FLAG = 'charlieSessionActive';

    if (!sessionStorage.getItem(SESSION_FLAG)) {
        // New browser session (sessionStorage cleared on browser close).
        // Delete any conversation left from a previous session.
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
        // Also wipe any edit history that lingered
        _clearAllEditHistory();
    }

    // Mark this tab as active (survives F5 refresh, cleared on browser close)
    sessionStorage.setItem(SESSION_FLAG, 'true');

    await loadConversationHistory();
}

// ── Layout adjustment ──────────────────────────────────────────────────────
function adjustLayout() {
    const messagesContainer = document.getElementById('messagesContainer');
    const inputContainer    = document.querySelector('.input-container');
    const navbar            = document.querySelector('.navbar');

    messagesContainer.style.top    = navbar.offsetHeight + 'px';
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
                const msgDiv = addMessageToUI(
                    msg.content,
                    msg.role === 'user',
                    msg.id ? String(msg.id) : null
                );

                // Restore pagination if this user message was edited this session
                if (msg.role === 'user' && msg.id) {
                    const mid      = String(msg.id);
                    const versions = _ehGet(mid);
                    const idx      = _eiGet(mid);
                    if (versions && versions.length > 1 && idx !== null) {
                        // Show the version that was current when page was refreshed
                        const bubble = msgDiv.querySelector('.message-bubble');
                        if (bubble) bubble.innerHTML = versions[idx];
                        _renderPagination(msgDiv, mid);
                    }
                }
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
    const text = bubble.innerText || bubble.textContent;
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
    navigator.clipboard.writeText(text.trim()).then(doConfirm).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text.trim();
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        doConfirm();
    });
}

// ── Add message to UI ──────────────────────────────────────────────────────
// Returns the message div (not the bubble).
// Pass messageId when the ID is known upfront (history load).
// For new messages sent live, the ID is set later via dataset after save.
function addMessageToUI(content, isUser = false, messageId = null) {
    const messagesContainer = document.getElementById('messagesContainer');
    const emptyState        = document.getElementById('emptyState');

    if (emptyState && !emptyState.classList.contains('hidden')) {
        emptyState.classList.add('hidden');
    }

    const messageDiv       = document.createElement('div');
    messageDiv.className   = `message ${isUser ? 'user' : 'bot'}`;
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

    let displayContent = content;
    if (!isUser) {
        displayContent = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        displayContent = linkifyText(displayContent);
    }

    // Actions: copy for all, edit only for user
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

    // Wire up copy button
    const copyBtn = messageDiv.querySelector('.copy-btn');
    const bubble  = messageDiv.querySelector('.message-bubble');
    copyBtn.addEventListener('click', () => copyMessageText(bubble, copyBtn));

    // Wire up edit button (user only) — reads messageId from dataset at click time
    if (isUser) {
        const editBtn = messageDiv.querySelector('.edit-btn');
        editBtn.addEventListener('click', () => {
            const mid = messageDiv.dataset.messageId;
            if (!mid) return; // message not yet saved, ignore
            startEditing(messageDiv, bubble, mid);
        });
    }

    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

// ── Edit: start ────────────────────────────────────────────────────────────
function startEditing(messageDiv, bubble, messageId) {
    // Prevent double-editing
    if (bubble.classList.contains('editing')) return;

    const originalText = (bubble.innerText || bubble.textContent).trim();
    bubble.dataset.originalContent = bubble.innerHTML;
    bubble.dataset.originalText    = originalText;

    // Disable copy + edit buttons while editing
    const copyBtn = messageDiv.querySelector('.copy-btn');
    const editBtn = messageDiv.querySelector('.edit-btn');
    if (copyBtn) copyBtn.disabled = true;
    if (editBtn) editBtn.disabled = true;

    // Lock width only so the bubble doesn't expand/shrink horizontally
    bubble.style.width = bubble.offsetWidth + 'px';

    // Replace bubble content with a textarea
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

    // Insert save/cancel row between bubble and meta
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

    // Enable save only when content actually changed
    textarea.addEventListener('input', () => {
        const current = textarea.value.trim();
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
    const maxHeight = 22 * 6; // ~6 lines
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.height      = maxHeight + 'px';
        textarea.style.overflowY   = 'auto';
    } else {
        textarea.style.height      = textarea.scrollHeight + 'px';
        textarea.style.overflowY   = 'hidden';
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

    // Re-enable copy + edit buttons
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

        // Restore bubble with new text (plain for user messages)
        bubble.innerHTML = newText;
        bubble.classList.remove('editing');
        bubble.style.width = '';
        delete bubble.dataset.originalContent;
        delete bubble.dataset.originalText;
        editActions.remove();

        // Re-enable copy + edit buttons
        const copyBtn = messageDiv.querySelector('.copy-btn');
        const editBtn = messageDiv.querySelector('.edit-btn');
        if (copyBtn) copyBtn.disabled = false;
        if (editBtn) editBtn.disabled = false;

        // Track edit history and show pagination
        _addToEditHistory(messageDiv, messageId, originalText, newText);

        // Remove all messages after this one in the DOM
        removeMessagesAfter(messageDiv);

        // Hide share button (conversation has changed)
        const shareButton = document.getElementById('shareButton');
        if (shareButton) shareButton.classList.remove('visible');

        // Re-trigger Charlie's response via the regenerate endpoint
        if (typeof sendAfterEdit === 'function') {
            await sendAfterEdit();
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
function _addToEditHistory(messageDiv, messageId, oldText, newText) {
    let versions = _ehGet(messageId);
    if (!versions) versions = [oldText];
    versions.push(newText);
    _ehSet(messageId, versions);
    _eiSet(messageId, versions.length - 1);
    _renderPagination(messageDiv, messageId);
}

function _renderPagination(messageDiv, messageId) {
    const versions  = _ehGet(messageId);
    const currentIdx = _eiGet(messageId);
    if (!versions || currentIdx === null) return;
    const total   = versions.length;
    const current = currentIdx + 1;

    // Remove any existing pagination row for this message
    const existing = messageDiv.querySelector('.edit-pagination');
    if (existing) existing.remove();

    const pagination        = document.createElement('div');
    pagination.className    = 'edit-pagination';
    pagination.dataset.msgId = messageId;
    pagination.innerHTML    = `
        <button class="page-prev" ${currentIdx === 0 ? 'disabled' : ''}>&#8249;</button>
        <span class="page-indicator">${current}/${total}</span>
        <button class="page-next" ${currentIdx === total - 1 ? 'disabled' : ''}>&#8250;</button>
    `;

    // Append after meta row
    const messageContent = messageDiv.querySelector('.message-content');
    messageContent.appendChild(pagination);

    const prevBtn = pagination.querySelector('.page-prev');
    const nextBtn = pagination.querySelector('.page-next');
    const bubble  = messageDiv.querySelector('.message-bubble');

    prevBtn.addEventListener('click', () => {
        const newIdx = _eiGet(messageId) - 1;
        if (newIdx < 0) return;
        _eiSet(messageId, newIdx);
        bubble.innerHTML = versions[newIdx];
        _renderPagination(messageDiv, messageId);
    });

    nextBtn.addEventListener('click', () => {
        const newIdx = _eiGet(messageId) + 1;
        if (newIdx >= total) return;
        _eiSet(messageId, newIdx);
        bubble.innerHTML = versions[newIdx];
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