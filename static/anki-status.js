const { createApp } = Vue;

createApp({
    data() {
        return {
            connected: false,
            version: null,
            checking: true
        }
    },
    computed: {
        statusClass() {
            return this.connected ? 'connected' : 'disconnected';
        },
        tooltip() {
            if (this.checking) return 'Checking Anki...';
            return this.connected 
                ? `Anki: Online (v${this.version || 'unknown'})` 
                : 'Anki: Offline\nMake sure Anki is running with AnkiConnect';
        }
    },
    methods: {
        async checkStatus() {
            try {
                const response = await fetch('/api/anki-status');
                const data = await response.json();
                this.connected = data.connected;
                this.version = data.version;
                this.checking = false;
            } catch (error) {
                this.connected = false;
                this.checking = false;
            }
        }
    },
    mounted() {
        this.checkStatus();
        setInterval(() => this.checkStatus(), 2000);
    },
    template: `
        <div class="anki-status" :class="statusClass" :title="tooltip">
            <transition name="pulse" mode="out-in">
                <svg v-if="connected" key="online" class="anki-icon" width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <svg v-else key="offline" class="anki-icon" width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
                    <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
                    <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
                    <line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </transition>
        </div>
    `
}).mount('#ankiStatusApp');
