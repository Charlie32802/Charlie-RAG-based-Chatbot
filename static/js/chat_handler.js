// chat_handler.js — send, stream, delete, share, print, regenerate after edit

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

    // Add user message to UI and keep a reference so we can set its ID later
    const userMsgDiv = addMessageToUI(message, true);

    // Disable controls
    chatInput.disabled    = true;
    sendButton.disabled   = true;
    deleteButton.disabled = true;
    if (shareButton) shareButton.disabled = true;

    showTypingIndicator();

    let botMsgDiv       = null;
    let botBubble       = null;
    let firstToken      = true;
    let streamCompleted = false;

    try {
        const response = await fetch('/api/chat-stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ message }),
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

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer    = '';

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

                    // Attach message IDs so the Edit button can reference them
                    if (parsed.user_message_id && userMsgDiv) {
                        userMsgDiv.dataset.messageId = String(parsed.user_message_id);
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

    } catch (error) {
        console.error('Stream error:', error);
        removeTypingIndicator();
        if (!botMsgDiv) {
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
        }
        if (botBubble) botBubble.textContent = 'Sorry, I encountered an error. Please try again.';
    } finally {
        chatInput.disabled    = false;
        sendButton.disabled   = false;
        deleteButton.disabled = false;
        if (shareButton) shareButton.disabled = false;
        chatInput.focus();

        if (streamCompleted) checkAndShowShareButton();
    }
}

// ── Regenerate Charlie's response after a message edit ────────────────────
// Called from conversation.js saveEdit() after the edit is saved to DB.
async function sendAfterEdit() {
    const chatInput    = document.getElementById('chatInput');
    const sendButton   = document.getElementById('sendButton');
    const deleteButton = document.getElementById('deleteButton');
    const shareButton  = document.getElementById('shareButton');

    chatInput.disabled    = true;
    sendButton.disabled   = true;
    deleteButton.disabled = true;
    if (shareButton) shareButton.disabled = true;

    showTypingIndicator();

    let botMsgDiv       = null;
    let botBubble       = null;
    let firstToken      = true;
    let streamCompleted = false;

    try {
        const response = await fetch('/api/regenerate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({}),
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

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer    = '';

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

    } catch (error) {
        console.error('Regenerate error:', error);
        removeTypingIndicator();
        if (!botMsgDiv) {
            botMsgDiv = addMessageToUI('', false);
            botBubble = botMsgDiv.querySelector('.message-bubble');
        }
        if (botBubble) botBubble.textContent = 'Sorry, I encountered an error. Please try again.';
    } finally {
        chatInput.disabled    = false;
        sendButton.disabled   = false;
        deleteButton.disabled = false;
        if (shareButton) shareButton.disabled = false;
        chatInput.focus();

        if (streamCompleted) checkAndShowShareButton();
    }
}

// ── Send button + Enter key ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const chatInput  = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');

    sendButton.addEventListener('click', () => {
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
        navigator.clipboard.writeText(linkInput.value).then(() => {
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

    document.getElementById('shareViaX').addEventListener('click', function () {
        const text = 'Check out my conversation with Charlie \u2014 Your Digital Buddy in Surigao!';
        window.open(
            'https://twitter.com/intent/tweet?url=' + encodeURIComponent(linkInput.value) +
            '&text=' + encodeURIComponent(text),
            '_blank'
        );
    });

    document.getElementById('shareViaMessenger').addEventListener('click', function () {
        const url = 'https://www.facebook.com/dialog/send?link=' +
            encodeURIComponent(linkInput.value) +
            '&app_id=291494419107518&redirect_uri=' +
            encodeURIComponent(linkInput.value);
        window.open(url, '_blank');
    });

    document.getElementById('shareViaInstagram').addEventListener('click', function () {
        navigator.clipboard.writeText(linkInput.value)
            .catch(() => {})
            .finally(() => window.open('https://www.instagram.com/', '_blank'));
    });
});