// Progress Bar Manager - Modal Version
export class ProgressBar {
    constructor(title = 'Processing...') {
        this.title = title;
        this.modal = null;
        this.bar = null;
        this.percentEl = null;
        this.titleEl = null;
        this.value = 0;
    }

    show() {
        this.modal = document.getElementById('progressModal');
        this.bar = document.getElementById('progressModalBar');
        this.percentEl = document.getElementById('progressModalPercent');
        this.titleEl = document.getElementById('progressModalTitle');
        
        if (!this.modal) return;
        
        this.titleEl.textContent = this.title;
        this.modal.style.display = 'flex';
        this.value = 0;
        this.set(0);
    }

    set(percent) {
        if (!this.bar || !this.percentEl) return;
        
        this.value = Math.max(0, Math.min(100, Math.floor(percent)));
        this.bar.style.width = `${this.value}%`;
        this.percentEl.textContent = `${this.value}%`;
    }

    complete() {
        if (!this.modal) return;
        
        this.set(100);
        
        setTimeout(() => {
            if (this.modal) {
                this.modal.style.display = 'none';
            }
            this.value = 0;
        }, 800);
    }

    reset() {
        this.value = 0;
        if (this.bar) this.bar.style.width = '0%';
        if (this.percentEl) this.percentEl.textContent = '0%';
    }
}
