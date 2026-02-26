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
                            <p class="empty-state-text">No messages yet! Start chatting with Deebai to begin your conversation.</p>
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
    
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    
    // Add user message to UI
    addMessageToUI(message, true);
    
    // Disable input and button while processing
    chatInput.disabled = true;
    sendButton.disabled = true;
    
    // Show the animated typing indicator while waiting for first token
    showTypingIndicator();
    
    // Create the bot bubble now but keep it empty — we'll fill it as tokens arrive
    let botBubble = null;
    let firstToken = true;
    
    try {
        const response = await fetch('/api/chat-stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ message })
        });
        
        // If the server returned a non-streaming error (e.g. 429, 400, 500)
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
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // SSE lines are separated by \n\n
            const lines = buffer.split('\n');
            // Keep the last (possibly incomplete) line in the buffer
            buffer = lines.pop();
            
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                
                let parsed;
                try {
                    parsed = JSON.parse(line.slice(6));
                } catch (_) {
                    continue;
                }
                
                // Error sent from server mid-stream
                if (parsed.error) {
                    if (firstToken) removeTypingIndicator();
                    if (!botBubble) botBubble = addMessageToUI('', false);
                    await typeMessage(botBubble, parsed.error);
                    return;
                }
                
                // A token arrived — swap typing indicator for the real bubble
                if (parsed.token) {
                    if (firstToken) {
                        removeTypingIndicator();
                        botBubble = addMessageToUI('', false);
                        initStreamBubble(botBubble);
                        firstToken = false;
                    }
                    appendStreamToken(botBubble, parsed.token);
                }
                
                // Stream finished
                if (parsed.done) {
                    if (botBubble) finalizeStreamedBubble(botBubble);
                    break;
                }
            }
        }
        
        // Edge case: server closed without sending a token (empty response)
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
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatInput.focus();
    }
}

// Handle send button click
document.addEventListener('DOMContentLoaded', function() {
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    
    sendButton.addEventListener('click', () => {
        const message = chatInput.value.trim();
        if (message) {
            sendMessage(message);
            chatInput.value = '';
            chatInput.style.height = '45px';
            chatInput.classList.remove('scrollable');
            if (typeof adjustLayout === 'function') {
                adjustLayout();
            }
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
                if (typeof adjustLayout === 'function') {
                    adjustLayout();
                }
            }
        }
    });
});