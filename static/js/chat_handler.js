// Chat handler for sending and receiving messages

// Delete conversation
document.addEventListener('DOMContentLoaded', function() {
    const deleteButton = document.getElementById('deleteButton');

    deleteButton.addEventListener('click', async function() {
        const confirmed = confirm('Are you sure you want to delete the entire conversation? This cannot be undone.');

        if (confirmed) {
            try {
                const response = await fetch('/api/delete-conversation/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });

                const data = await response.json();

                if (data.status === 'success') {
                    const messagesContainer = document.getElementById('messagesContainer');
                    messagesContainer.innerHTML = `
                        <div class="empty-state" id="emptyState">
                            <img src="/static/images/no-messages-yet.png" alt="No messages yet" class="empty-state-image">
                            <p class="empty-state-text">No messages yet! Start chatting with Charlie to begin your conversation.</p>
                        </div>
                    `;
                    location.reload();
                }
            } catch (error) {
                console.error('Error deleting conversation:', error);
                alert('Failed to delete conversation. Please try again.');
            }
        }
    });
});

// Send message using streaming API
async function sendMessage(message) {
    if (!message.trim()) return;

    const chatInput    = document.getElementById('chatInput');
    const sendButton   = document.getElementById('sendButton');
    const deleteButton = document.getElementById('deleteButton');
    const shareButton  = document.getElementById('shareButton');

    // Add user message to UI
    addMessageToUI(message, true);

    // Disable controls while Charlie is responding
    chatInput.disabled    = true;
    sendButton.disabled   = true;
    deleteButton.disabled = true;
    if (shareButton) shareButton.disabled = true;

    // Show the animated typing indicator while waiting for first token
    showTypingIndicator();

    let botBubble  = null;
    let firstToken = true;
    let streamCompleted = false;  // true only when server sends { done: true }

    try {
        const response = await fetch('/api/chat-stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ message })
        });

        // Non-streaming error (429, 400, 500…)
        if (!response.ok || !response.body) {
            removeTypingIndicator();
            let errMsg = 'Something went wrong. Please try again.';
            try {
                const errData = await response.json();
                if (errData.error) errMsg = errData.error;
            } catch (_) {}
            botBubble = addMessageToUI('', false);
            await typeMessage(botBubble, errMsg);
            return;
        }

        const reader  = response.body.getReader();
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

                // Error mid-stream
                if (parsed.error) {
                    if (firstToken) removeTypingIndicator();
                    if (!botBubble) botBubble = addMessageToUI('', false);
                    await typeMessage(botBubble, parsed.error);
                    return;
                }

                // Token arrived — swap indicator for real bubble
                if (parsed.token) {
                    if (firstToken) {
                        removeTypingIndicator();
                        botBubble = addMessageToUI('', false);
                        initStreamBubble(botBubble);
                        firstToken = false;
                    }
                    appendStreamToken(botBubble, parsed.token);
                }

                // Stream finished — server confirmed save
                if (parsed.done) {
                    if (botBubble) finalizeStreamedBubble(botBubble);
                    streamCompleted = true;
                    break;
                }
            }
        }

        // Edge case: stream closed with no tokens
        if (firstToken) {
            removeTypingIndicator();
            botBubble = addMessageToUI('', false);
            await typeMessage(botBubble, "I tried to respond but nothing came out. Could you ask again?");
        }

    } catch (error) {
        console.error('Stream error:', error);
        removeTypingIndicator();
        if (!botBubble) botBubble = addMessageToUI('', false);
        botBubble.textContent = 'Sorry, I encountered an error. Please try again.';
    } finally {
        // Re-enable controls
        chatInput.disabled    = false;
        sendButton.disabled   = false;
        deleteButton.disabled = false;
        if (shareButton) shareButton.disabled = false;
        chatInput.focus();

        // Only show Share once a full exchange is confirmed saved
        if (streamCompleted) {
            checkAndShowShareButton();
        }
    }
}

// Handle send button click
document.addEventListener('DOMContentLoaded', function() {
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

// Share modal logic + print button
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
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeModal();
    });

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
        window.open('https://twitter.com/intent/tweet?url=' + encodeURIComponent(linkInput.value) + '&text=' + encodeURIComponent(text), '_blank');
    });

    document.getElementById('shareViaMessenger').addEventListener('click', function () {
        const url = 'https://www.facebook.com/dialog/send?link=' + encodeURIComponent(linkInput.value) + '&app_id=291494419107518&redirect_uri=' + encodeURIComponent(linkInput.value);
        window.open(url, '_blank');
    });

    document.getElementById('shareViaInstagram').addEventListener('click', function () {
        navigator.clipboard.writeText(linkInput.value).then(() => {
            window.open('https://www.instagram.com/', '_blank');
        }).catch(() => {
            window.open('https://www.instagram.com/', '_blank');
        });
    });
});