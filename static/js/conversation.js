// Auto-expanding textarea
document.addEventListener('DOMContentLoaded', function() {
    const chatInput = document.getElementById('chatInput');
    const messagesContainer = document.getElementById('messagesContainer');
    const scrollTopBtn = document.getElementById('scrollTopBtn');

    // Load conversation history
    loadConversationHistory();

    // Auto-expand textarea
    chatInput.addEventListener('input', function() {
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

    // Scroll to bottom button
    messagesContainer.addEventListener('scroll', function() {
        if (messagesContainer.scrollTop > 300) {
            scrollTopBtn.classList.add('show');
        } else {
            scrollTopBtn.classList.remove('show');
        }
    });

    scrollTopBtn.addEventListener('click', function() {
        messagesContainer.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
});

function adjustLayout() {
    const messagesContainer = document.getElementById('messagesContainer');
    const inputContainer = document.querySelector('.input-container');
    const navbar = document.querySelector('.navbar');

    const navbarHeight = navbar.offsetHeight;
    const inputHeight = inputContainer.offsetHeight;

    messagesContainer.style.top = navbarHeight + 'px';
    messagesContainer.style.bottom = inputHeight + 'px';
}

// Reveal Share button once at least one user + one bot message exists in the DOM
function checkAndShowShareButton() {
    const shareButton = document.getElementById('shareButton');
    if (!shareButton) return;
    const messages  = document.querySelectorAll('#messagesContainer .message');
    const hasUser   = [...messages].some(m => m.classList.contains('user'));
    const hasBot    = [...messages].some(m => m.classList.contains('bot'));
    if (hasUser && hasBot) {
        shareButton.classList.add('visible');
    }
}

// Load conversation history from database
async function loadConversationHistory() {
    try {
        const response = await fetch('/api/load-history/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.status === 'success' && data.messages && data.messages.length > 0) {
            const emptyState = document.getElementById('emptyState');
            if (emptyState) {
                emptyState.classList.add('hidden');
            }

            for (const msg of data.messages) {
                addMessageToUI(msg.content, msg.role === 'user');
            }

            scrollToBottom();
            checkAndShowShareButton();
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// ── Message action icon SVGs ──────────────────────────────────────────────────
const ICON_COPY  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;


function copyMessageText(bubble, btn) {
    const text = bubble.innerText || bubble.textContent;
    navigator.clipboard.writeText(text.trim()).then(() => {
        btn.innerHTML = ICON_CHECK;
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = ICON_COPY;
            btn.classList.remove('copied');
        }, 2000);
    }).catch(() => {
        // Fallback for browsers without clipboard API
        const ta = document.createElement('textarea');
        ta.value = text.trim();
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.innerHTML = ICON_CHECK;
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = ICON_COPY;
            btn.classList.remove('copied');
        }, 2000);
    });
}


// Add message to UI (without database save)
function addMessageToUI(content, isUser = false) {
    const messagesContainer = document.getElementById('messagesContainer');
    const emptyState = document.getElementById('emptyState');

    if (emptyState && !emptyState.classList.contains('hidden')) {
        emptyState.classList.add('hidden');
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;

    const avatarHtml = isUser
        ? `<div class="message-avatar">
               <img src="/static/images/user-profile.png" alt="User" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">
           </div>`
        : `<div class="message-avatar">
               <img src="/static/images/favicon.ico" alt="Charlie" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">
           </div>`;

    let displayContent = content;
    if (!isUser) {
        displayContent = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        displayContent = linkifyText(displayContent);
    }

    const actionsHtml = `<div class="message-actions">
               <button class="message-action-btn copy-btn" title="Copy message">${ICON_COPY}</button>
           </div>`;

    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            <div class="message-bubble">${displayContent}</div>
            <div class="message-time">${getCurrentTime()}</div>
            ${actionsHtml}
        </div>
    `;

    // Wire up copy button
    const copyBtn = messageDiv.querySelector('.copy-btn');
    const bubble  = messageDiv.querySelector('.message-bubble');
    copyBtn.addEventListener('click', () => copyMessageText(bubble, copyBtn));

    messagesContainer.appendChild(messageDiv);
    scrollToBottom();

    return bubble;
}

// Get current time
function getCurrentTime() {
    const now = new Date();
    let hours = now.getHours();
    let minutes = now.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    minutes = minutes < 10 ? '0' + minutes : minutes;
    return hours + ':' + minutes + ' ' + ampm;
}

// Get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}