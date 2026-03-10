// chat_handler.js — send, stream, stop, delete, share, print, regenerate after edit

// ── Stop icon (circle + filled square) ────────────────────────────────────
const ICON_STOP = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><rect x="8" y="8" width="8" height="8" rx="1" fill="currentColor" stroke="none"/></svg>`;

// Save original send button HTML so we can restore it after stopping
let _sendBtnOriginalHTML = '';
document.addEventListener('DOMContentLoaded', function () {
    const sendButton = document.getElementById('sendButton');
    if (sendButton) _sendBtnOriginalHTML = sendButton.innerHTML;
});

// ── Stop button helpers ────────────────────────────────────────────────────
function _activateStopButton(sendButton, onStop) {
    sendButton.innerHTML = ICON_STOP;
    sendButton.disabled  = false;
    sendButton.setAttribute('data-tip', 'Stop responding');
    sendButton.classList.add('stop-mode');
    sendButton.addEventListener('click', onStop, { once: true });
}

function _restoreSendButton(sendButton) {
    sendButton.innerHTML = _sendBtnOriginalHTML;
    sendButton.removeAttribute('data-tip');
    sendButton.classList.remove('stop-mode');
}

// ── Edit button lock helpers ───────────────────────────────────────────────
function _disableAllEditButtons() {
    document.querySelectorAll('#messagesContainer .edit-btn').forEach(btn => {
        btn.disabled = true;
    });
}

function _enableAllEditButtons() {
    document.querySelectorAll('#messagesContainer .edit-btn').forEach(btn => {
        btn.disabled = false;
    });
}

// ── Delete conversation ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const deleteButton = document.getElementById('deleteButton');

    deleteButton.addEventListener('click', async function () {
        const confirmed = confirm('Are you sure you want to delete the entire conversation? This cannot be undone.');
        if (!confirmed) return;

        try {
            const response = await fetch('/api/delete-conversation/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
            });

            const data = await response.json();

            if (data.status === 'success') {
                const messagesContainer = document.getElementById('messagesContainer');
                messagesContainer.innerHTML = `
                    <div class="empty-state" id="emptyState">
                        <div class="image-wrapper">
                            <img src="/static/images/no-messages-yet.png" alt="No messages yet" class="empty-state-image">
                        </div>
                        <p class="empty-state-text">No messages yet! Start chatting with Charlie to begin your conversation.</p>
                    </div>
                `;
                location.reload();
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('Failed to delete conversation. Please try again.');
        }
    });
});

// ── Send message (streaming) ───────────────────────────────────────────────
async function sendMessage(message) {
    if (!message.trim()) return;

    const chatInput    = document.getElementById('chatInput');
    const sendButton   = document.getElementById('sendButton');
    const deleteButton = document.getElementById('deleteButton');
    const shareButton  = document.getElementById('shareButton');

    const userMsgDiv = addMessageToUI(message, true);

    chatInput.disabled    = true;
    sendButton.disabled   = true;
    deleteButton.disabled = true;
    if (shareButton) shareButton.disabled = true;

    // Disable all edit buttons while Charlie is responding
    _disableAllEditButtons();

    showTypingIndicator();

    let botMsgDiv       = null;
    let botBubble       = null;
    let firstToken      = true;
    let streamCompleted = false;
    let partialText     = '';
    let aborted         = false;
    let reader          = null;
    const controller    = new AbortController();

    const onStop = () => {
        aborted = true;
        controller.abort();
        if (reader) reader.cancel().catch(() => {});
    };

    // Activate stop button immediately (even during typing indicator)
    _activateStopButton(sendButton, onStop);

    try {
        const response = await fetch('/api/chat-stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ message }),
            signal: controller.signal,
        });

        if (!response.ok || !response.body) {
            removeTypingIndicator();
            let errMsg = 'Something went wrong. Please try again.';
            try {
                const errData = await response.json();
                if (errData.error) errMsg = errData.error;
            } catch (_) {}
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
            await typeMessage(botBubble, errMsg);
            return;
        }

        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let parsed;
                try { parsed = JSON.parse(line.slice(6)); } catch (_) { continue; }

                if (parsed.error) {
                    if (firstToken) removeTypingIndicator();
                    if (!botMsgDiv) {
                        botMsgDiv = addMessageToUI('', false);
                        botBubble = botMsgDiv.querySelector('.message-bubble');
                    }
                    await typeMessage(botBubble, parsed.error);
                    return;
                }

                // ── FIX 1: Capture user_message_id as soon as server emits it  ──
                // The server now pre-saves the user message and emits its ID as the
                // FIRST SSE event (before any tokens). This ensures userMsgDiv always
                // has a messageId so the Edit button works — even if stream is aborted.
                if (parsed.user_message_id && userMsgDiv) {
                    userMsgDiv.dataset.messageId = String(parsed.user_message_id);
                }

                if (parsed.token) {
                    partialText += parsed.token;
                    if (firstToken) {
                        removeTypingIndicator();
                        botMsgDiv = addMessageToUI('', false);
                        botBubble = botMsgDiv.querySelector('.message-bubble');
                        initStreamBubble(botBubble);
                        firstToken = false;
                    }
                    appendStreamToken(botBubble, parsed.token);
                }

                if (parsed.done) {
                    if (botBubble) finalizeStreamedBubble(botBubble);
                    // user_message_id is now set early (above), no need to re-set here.
                    // bot_message_id still arrives with 'done'.
                    if (parsed.bot_message_id && botMsgDiv) {
                        botMsgDiv.dataset.messageId = String(parsed.bot_message_id);
                    }
                    streamCompleted = true;
                    break;
                }
            }
        }

        if (firstToken) {
            removeTypingIndicator();
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
            await typeMessage(botBubble, "I tried to respond but nothing came out. Could you ask again?");
        }

    } catch (err) {
        if (err.name === 'AbortError' || aborted) {
            if (!firstToken && botBubble && partialText.trim()) {
                // Charlie had started responding — finalize and save the partial text
                finalizeStreamedBubble(botBubble);
                try {
                    const saveRes = await fetch('/api/save-partial/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                        body: JSON.stringify({ partial_text: partialText.trim() }),
                    });
                    const saveData = await saveRes.json();
                    if (saveData.message_id && botMsgDiv) {
                        botMsgDiv.dataset.messageId = String(saveData.message_id);
                    }
                } catch (_) {}
                // ── FIX 2: Show Share — we have a saved user message + partial bot
                // response. streamCompleted is false on abort so the finally block
                // won't call checkAndShowShareButton; we must call it here explicitly.
                checkAndShowShareButton();
            } else if (!firstToken && botBubble) {
                // Tokens arrived but were all whitespace — remove the empty bubble
                botMsgDiv.remove();
            } else if (firstToken) {
                // Stopped during the "..." typing indicator before any token arrived.
                // User message is already saved in DB (pre-saved by server). The typing
                // indicator is still showing — remove it. No bot bubble exists yet.
                removeTypingIndicator();
                // Do NOT call checkAndShowShareButton — no bot response exists yet.
            }
            // No error message shown — user intentionally chose to stop.
        } else {
            console.error('Stream error:', err);
            removeTypingIndicator();
            if (!botMsgDiv) {
                botMsgDiv = addMessageToUI('', false);
                botBubble = botMsgDiv.querySelector('.message-bubble');
            }
            if (botBubble) botBubble.textContent = 'Sorry, I encountered an error. Please try again.';
        }
    } finally {
        _restoreSendButton(sendButton);
        chatInput.disabled    = false;
        sendButton.disabled   = false;
        deleteButton.disabled = false;
        if (shareButton) shareButton.disabled = false;
        // Re-enable all edit buttons now that Charlie is done
        _enableAllEditButtons();
        chatInput.focus();
        // Called here for the normal (non-aborted) completion path
        if (streamCompleted) checkAndShowShareButton();
    }
}

// ── Regenerate Charlie's response after a message edit ────────────────────
// userMsgId is passed so _fillLastBotText stores the response for pagination.
async function sendAfterEdit(userMsgId) {
    const chatInput    = document.getElementById('chatInput');
    const sendButton   = document.getElementById('sendButton');
    const deleteButton = document.getElementById('deleteButton');
    const shareButton  = document.getElementById('shareButton');

    chatInput.disabled    = true;
    sendButton.disabled   = true;
    deleteButton.disabled = true;
    if (shareButton) shareButton.disabled = true;

    // Disable all edit buttons while Charlie is responding
    _disableAllEditButtons();

    showTypingIndicator();

    let botMsgDiv       = null;
    let botBubble       = null;
    let firstToken      = true;
    let streamCompleted = false;
    let partialText     = '';
    let aborted         = false;
    let reader          = null;
    const controller    = new AbortController();

    const onStop = () => {
        aborted = true;
        controller.abort();
        if (reader) reader.cancel().catch(() => {});
    };

    // Activate stop button immediately (even during typing indicator)
    _activateStopButton(sendButton, onStop);

    try {
        const response = await fetch('/api/regenerate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({}),
            signal: controller.signal,
        });

        if (!response.ok || !response.body) {
            removeTypingIndicator();
            let errMsg = 'Something went wrong. Please try again.';
            try {
                const errData = await response.json();
                if (errData.error) errMsg = errData.error;
            } catch (_) {}
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
            await typeMessage(botBubble, errMsg);
            return;
        }

        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let parsed;
                try { parsed = JSON.parse(line.slice(6)); } catch (_) { continue; }

                if (parsed.error) {
                    if (firstToken) removeTypingIndicator();
                    if (!botMsgDiv) {
                        botMsgDiv = addMessageToUI('', false);
                        botBubble = botMsgDiv.querySelector('.message-bubble');
                    }
                    await typeMessage(botBubble, parsed.error);
                    return;
                }

                if (parsed.token) {
                    partialText += parsed.token;
                    if (firstToken) {
                        removeTypingIndicator();
                        botMsgDiv = addMessageToUI('', false);
                        botBubble = botMsgDiv.querySelector('.message-bubble');
                        initStreamBubble(botBubble);
                        firstToken = false;
                    }
                    appendStreamToken(botBubble, parsed.token);
                }

                if (parsed.done) {
                    if (botBubble) {
                        finalizeStreamedBubble(botBubble);
                        // Store final bot HTML for pagination
                        if (userMsgId && typeof _fillLastBotText === 'function') {
                            _fillLastBotText(userMsgId, botBubble.innerHTML);
                        }
                    }
                    if (parsed.bot_message_id && botMsgDiv) {
                        botMsgDiv.dataset.messageId = String(parsed.bot_message_id);
                    }
                    streamCompleted = true;
                    break;
                }
            }
        }

        if (firstToken) {
            removeTypingIndicator();
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
            await typeMessage(botBubble, "I tried to respond but nothing came out. Could you ask again?");
        }

    } catch (err) {
        if (err.name === 'AbortError' || aborted) {
            if (!firstToken && botBubble && partialText.trim()) {
                finalizeStreamedBubble(botBubble);
                try {
                    const saveRes = await fetch('/api/save-partial/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                        body: JSON.stringify({ partial_text: partialText.trim() }),
                    });
                    const saveData = await saveRes.json();
                    if (saveData.message_id && botMsgDiv) {
                        botMsgDiv.dataset.messageId = String(saveData.message_id);
                    }
                } catch (_) {}
                if (userMsgId && typeof _fillLastBotText === 'function') {
                    _fillLastBotText(userMsgId, botBubble.innerHTML);
                }
                // Show share — partial bot response exists for the edited user message
                checkAndShowShareButton();
            } else if (!firstToken && botBubble) {
                // Only whitespace tokens — remove the empty bubble
                botMsgDiv.remove();
                if (userMsgId && typeof _fillLastBotText === 'function') {
                    _fillLastBotText(userMsgId, '');
                }
            } else {
                // Stopped during typing indicator — no bot message produced
                if (firstToken) removeTypingIndicator();
                if (botMsgDiv) botMsgDiv.remove();
                if (userMsgId && typeof _fillLastBotText === 'function') {
                    _fillLastBotText(userMsgId, '');
                }
            }
        } else {
            console.error('Regenerate error:', err);
            removeTypingIndicator();
            if (!botMsgDiv) {
                botMsgDiv = addMessageToUI('', false);
                botBubble = botMsgDiv.querySelector('.message-bubble');
            }
            if (botBubble) botBubble.textContent = 'Sorry, I encountered an error. Please try again.';
        }
    } finally {
        _restoreSendButton(sendButton);
        chatInput.disabled    = false;
        sendButton.disabled   = false;
        deleteButton.disabled = false;
        if (shareButton) shareButton.disabled = false;
        // Re-enable all edit buttons now that Charlie is done
        _enableAllEditButtons();
        chatInput.focus();
        if (streamCompleted) checkAndShowShareButton();
    }
}

// ── Send button + Enter key ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const chatInput  = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');

    sendButton.addEventListener('click', () => {
        if (sendButton.classList.contains('stop-mode')) return;
        const message = chatInput.value.trim();
        if (message) {
            sendMessage(message);
            chatInput.value = '';
            chatInput.style.height = '45px';
            chatInput.classList.remove('scrollable');
            if (typeof adjustLayout === 'function') adjustLayout();
        }
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (sendButton.classList.contains('stop-mode')) return;
            const message = chatInput.value.trim();
            if (message) {
                sendMessage(message);
                chatInput.value = '';
                chatInput.style.height = '45px';
                chatInput.classList.remove('scrollable');
                if (typeof adjustLayout === 'function') adjustLayout();
            }
        }
    });
});

// ── Clipboard helper — works on both HTTPS and plain HTTP ─────────────────
// navigator.clipboard is only available in secure contexts (HTTPS / localhost).
// On plain HTTP (LAN access), it is undefined and will throw a silent TypeError.
// This helper tries the modern API first, then falls back to execCommand.
function _copyTextToClipboard(text, onSuccess, onFailure) {
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
            if (onSuccess) onSuccess();
        } catch (e) {
            console.error('Copy failed:', e);
            if (onFailure) onFailure(e);
        }
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(execFallback);
    } else {
        execFallback();
    }
}

// ── Share modal + print button ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('printButton').addEventListener('click', function () {
        window.print();
    });

    const overlay   = document.getElementById('shareModalOverlay');
    const closeBtn  = document.getElementById('shareModalClose');
    const linkInput = document.getElementById('shareLinkInput');
    const copyBtn   = document.getElementById('shareCopyBtn');

    if (!overlay) return;

    function openModal() {
        linkInput.value = window.location.href;
        overlay.classList.remove('hidden');
        setTimeout(() => linkInput.select(), 50);
    }

    function closeModal() {
        overlay.classList.add('hidden');
        copyBtn.textContent = 'Copy';
        copyBtn.classList.remove('copied');
    }

    document.getElementById('shareButton').addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

    copyBtn.addEventListener('click', function () {
        _copyTextToClipboard(linkInput.value, function () {
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.textContent = 'Copy';
                copyBtn.classList.remove('copied');
            }, 2000);
        });
    });

    document.getElementById('shareViaFacebook').addEventListener('click', function () {
        window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(linkInput.value), '_blank');
    });

    document.getElementById('shareViaWhatsApp').addEventListener('click', function () {
        const text = 'Check out my conversation with Charlie \u2014 Your Digital Buddy in Surigao! ' + linkInput.value;
        window.open('https://wa.me/?text=' + encodeURIComponent(text), '_blank');
    });

    document.getElementById('shareViaMessenger').addEventListener('click', function () {
        const url = 'https://www.facebook.com/dialog/send?link=' +
            encodeURIComponent(linkInput.value) +
            '&app_id=291494419107518&redirect_uri=' +
            encodeURIComponent(linkInput.value);
        window.open(url, '_blank');
    });

    document.getElementById('shareViaInstagram').addEventListener('click', function () {
        _copyTextToClipboard(
            linkInput.value,
            () => window.open('https://www.instagram.com/', '_blank'),
            () => window.open('https://www.instagram.com/', '_blank')
        );
    });
});