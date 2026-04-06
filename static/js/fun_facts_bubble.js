/**
 * Fun Facts Tooltip Handler
 * 
 * Displays random fun facts about Surigao del Norte in a tooltip bubble
 * with typing and untyping animations. Ensures all facts are shown before repeating.
 */

// Fun facts about Surigao del Norte
const funFacts = [
    "Surigao del Norte is the Surfing Capital of the Philippines! 🏄",
    "Did you know? We have a 98.28% literacy rate! 📚",
    "Our provincial flower is the beautiful Wensie Orchid! 🌸",
    "The Blue Marlin (Malasugi) is our provincial fish! 🐟",
    "We're home to 335 barangays across 20 municipalities! 🏘️",
    "Our provincial bird is the majestic Sea Eagle (Manaul)! 🦅",
    "The Magkono tree is our official provincial tree! 🌳",
    "Surigao City is the capital of our beautiful province! 🏛️",
    "The Sea Cow (Dujong) is our provincial animal! 🦭",
    "Nickel is our provincial metal, we're rich in minerals! ⛏️",
    "Our population is 485,088 people! That's a lot of friends! 👥",
    "We speak Cebuano, Surigaonon, Boholano, and more! 🗣️",
    "I was proudly created by two IT developers: Marc Daryll Trinidad and Jade Mancio! 💻👨‍💻"
];

// Easter egg fact index
const CREATOR_FACT_INDEX = 12; // The last fact about Marc

class FunFactsBubble {
    constructor() {
        this.facts = [...funFacts];
        this.availableFacts = [];
        this.isTyping = false;
        this.isUntyping = false;
        this.bubbleElement = null;
        this.contentElement = null;
        this.cursorElement = null;
        this.typingSpeed = 40;
        this.currentFactIndex = -1;
        this.isClickable = false;
        
        this.init();
    }
    
    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.createBubble());
        } else {
            this.createBubble();
        }
    }
    
    createBubble() {
        const imageWrapper = document.querySelector('.image-wrapper');
        if (!imageWrapper) return;
        
        this.bubbleElement = document.createElement('div');
        this.bubbleElement.className = 'fun-facts-bubble';
        
        this.contentElement = document.createElement('span');
        this.contentElement.className = 'bubble-content';
        
        this.cursorElement = document.createElement('span');
        this.cursorElement.className = 'bubble-cursor';
        
        this.bubbleElement.appendChild(this.contentElement);
        this.bubbleElement.appendChild(this.cursorElement);
        
        imageWrapper.appendChild(this.bubbleElement);
        
        // Add click event for Easter egg
        this.bubbleElement.addEventListener('click', (event) => this.handleClick(event));
        
        this.startCycle();
    }
    
    shuffleAvailableFacts() {
        this.availableFacts = [...this.facts];
        for (let i = this.availableFacts.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [this.availableFacts[i], this.availableFacts[j]] = 
                [this.availableFacts[j], this.availableFacts[i]];
        }
    }
    
    getNextFact() {
        if (this.availableFacts.length === 0) {
            this.shuffleAvailableFacts();
        }
        const fact = this.availableFacts.shift();
        this.currentFactIndex = this.facts.indexOf(fact);
        return fact;
    }
    
    async startCycle() {
        await this.delay(1000);
        
        while (true) {
            const fact = this.getNextFact();
            await this.typeFact(fact);
            
            // Enable clicking only for creator fact
            this.isClickable = (this.currentFactIndex === CREATOR_FACT_INDEX);
            if (this.isClickable) {
                this.bubbleElement.style.cursor = 'pointer';
            } else {
                this.bubbleElement.style.cursor = 'default';
            }
            
            await this.delay(6000);
            await this.untypeFact();
            this.isClickable = false;
            this.bubbleElement.style.cursor = 'default';
            await this.delay(3000);
        }
    }
    
    async typeFact(fact) {
        this.isTyping = true;
        this.contentElement.textContent = '';
        
        for (let i = 0; i < fact.length; i++) {
            if (!this.isTyping) break;
            this.contentElement.textContent += fact[i];
            await this.delay(this.typingSpeed);
        }
        
        this.isTyping = false;
    }
    
    async untypeFact() {
        this.isUntyping = true;
        const currentText = this.contentElement.textContent;
        
        for (let i = currentText.length; i >= 0; i--) {
            if (!this.isUntyping) break;
            this.contentElement.textContent = currentText.substring(0, i);
            await this.delay(this.typingSpeed / 2);
        }
        
        this.isUntyping = false;
    }
    
    handleClick(event) {
        if (!this.isClickable) return;
        
        // Create Philippine flag explosion at cursor position!
        this.createFlagExplosion(event);
    }
    
    createFlagExplosion(event) {
        const centerX = event.clientX;
        const centerY = event.clientY;
        const flagCount = 24;
        
        for (let i = 0; i < flagCount; i++) {
            const flag = document.createElement('div');
            flag.className = 'flag-confetti';
            
            flag.innerHTML = `
                <div class="ph-flag">
                    <div class="flag-blue"></div>
                    <div class="flag-red"></div>
                    <div class="flag-triangle">
                        <div class="flag-sun">☀</div>
                        <div class="flag-star star1">★</div>
                        <div class="flag-star star2">★</div>
                        <div class="flag-star star3">★</div>
                    </div>
                </div>
            `;
            
            // Random explosion angle
            const angle = (Math.random() * 360) * (Math.PI / 180);
            const distance = 200 + Math.random() * 250;
            const spreadX = Math.cos(angle) * distance;
            const spreadY = Math.sin(angle) * distance;
            
            // Random gentle rotation like a falling leaf
            const rotation = 360 + Math.random() * 720;
            
            flag.style.left = `${centerX}px`;
            flag.style.top = `${centerY}px`;
            flag.style.setProperty('--spread-x', `${spreadX}px`);
            flag.style.setProperty('--spread-y', `${spreadY}px`);
            flag.style.setProperty('--rotation', `${rotation}deg`);
            
            document.body.appendChild(flag);
            
            setTimeout(() => flag.remove(), 3500);
        }
    }
    
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    stop() {
        this.isTyping = false;
        this.isUntyping = false;
    }
}

let funFactsBubbleInstance;

document.addEventListener('DOMContentLoaded', function() {
    const emptyState = document.getElementById('emptyState');
    if (emptyState && !emptyState.classList.contains('hidden')) {
        funFactsBubbleInstance = new FunFactsBubble();
    }
    
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'class') {
                const emptyState = mutation.target;
                if (emptyState.classList.contains('hidden') && funFactsBubbleInstance) {
                    funFactsBubbleInstance.stop();
                }
            }
        });
    });
    
    if (emptyState) {
        observer.observe(emptyState, { attributes: true });
    }
});