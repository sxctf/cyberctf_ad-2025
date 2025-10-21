class Chatbot {
    constructor() {
        this.isMinimized = false;
        this.conversationHistory = [];
        this.init();
    }

    init() {
        this.bindEvents();
        this.addMessage('bot', 'Привет! Я ваш космический помощник. Чем могу помочь?');
    }

    bindEvents() {
        document.getElementById('sendMessage').addEventListener('click', () => this.sendMessage());
        document.getElementById('minimizeChat').addEventListener('click', () => this.toggleMinimize());
        document.getElementById('chatInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });
    }

    toggleMinimize() {
        this.isMinimized = !this.isMinimized;
        const chatbot = document.getElementById('chatbot');
        chatbot.classList.toggle('minimized', this.isMinimized);
        
        const minimizeBtn = document.getElementById('minimizeChat');
        minimizeBtn.textContent = this.isMinimized ? '+' : '−';
    }

    async sendMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        
        if (!message) return;

        this.addMessage('user', message);
        input.value = '';

        this.showTypingIndicator();

        try {
            const response = await this.processMessage(message);
            this.removeTypingIndicator();
            this.addMessage('bot', response);
        } catch (error) {
            this.removeTypingIndicator();
            this.addMessage('bot', 'Извините, произошла ошибка. Попробуйте еще раз.');
        }
    }

    async processMessage(message) {
        const response = await fetch('/api/chatbot/process', {
            method: 'POST',
            headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message
            })
        });

        if (response.ok) {
            const result = await response.json();
            this.conversationHistory.push({ role: 'user', content: message });
            this.conversationHistory.push({ role: 'assistant', content: result.response });
            return result.response;
        } else {
            return "Не удалось связаться с Плуто";
        }
    }

    addMessage(sender, text) {
        const messagesContainer = document.getElementById('chatMessages');
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}`;
        messageElement.textContent = text;
        
        messagesContainer.appendChild(messageElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    showTypingIndicator() {
        const messagesContainer = document.getElementById('chatMessages');
        const indicator = document.createElement('div');
        indicator.className = 'message bot typing-indicator';
        indicator.id = 'typingIndicator';
        indicator.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
        
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    getAuthHeaders() {
        const token = localStorage.getItem('token');
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }
}

const chatbot = new Chatbot();