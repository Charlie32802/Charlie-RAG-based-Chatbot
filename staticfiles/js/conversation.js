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

function scrollToBottom() {
    const messagesContainer = document.getElementById('messagesContainer');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
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
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Convert URLs and emails to clickable links
function linkify(text) {
    const urlPattern = /(\b(https?:\/\/|www\.)[^\s<]+)/gi;
    const emailPattern = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/gi;
    
    text = text.replace(urlPattern, (url) => {
        const href = url.startsWith('www.') ? 'https://' + url : url;
        return `<a href="${href}" target="_blank" rel="noopener noreferrer" style="color: #1976d2; text-decoration: underline;">${url}</a>`;
    });
    
    text = text.replace(emailPattern, (email) => {
        return `<a href="mailto:${email}" style="color: #1976d2; text-decoration: underline;">${email}</a>`;
    });
    
    return text;
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
               <img src="/static/images/user-profile.png" alt="Charlie" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">
           </div>`
        : `<div class="message-avatar">
               <img src="/static/images/favicon.ico" alt="Charlie" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">
           </div>`;
    
    let displayContent = content;
    if (!isUser) {
        displayContent = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        displayContent = linkify(displayContent);
    }
    
    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            <div class="message-bubble">${displayContent}</div>
            <div class="message-time">${getCurrentTime()}</div>
        </div>
    `;
    
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    
    return messageDiv.querySelector('.message-bubble');
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