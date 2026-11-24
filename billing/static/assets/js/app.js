/**
 * ADVANCE BILLING SYSTEM WITH QR - CLEAN & MINIMAL JS APP
 * UI helpers for Role Switching, Light/Dark Theme, Password Toggle & Modal
 */

const App = (function () {
    let timerId = null;

    /**
     * Initialize Theme Preference on Load
     */
    function initTheme() {
        const savedTheme = localStorage.getItem('theme_pref') || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('theme-light');
            updateThemeBtnIcon('☀️ Light');
        } else {
            document.body.classList.remove('theme-light');
            updateThemeBtnIcon('🌙 Dark');
        }
    }

    /**
     * Toggle Light / Dark Theme Mode
     */
    function toggleTheme() {
        const isLight = document.body.classList.toggle('theme-light');
        const modeName = isLight ? 'light' : 'dark';
        localStorage.setItem('theme_pref', modeName);
        updateThemeBtnIcon(isLight ? '☀️ Light' : '🌙 Dark');
        toast(`Switched to ${isLight ? 'Light' : 'Dark'} Mode`);
    }

    function updateThemeBtnIcon(text) {
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) btn.innerHTML = text;
    }

    /**
     * Toggle Role Mode (Distributor vs Admin)
     */
    function setRole(role) {
        document.body.classList.remove('mode-admin', 'mode-distributor');
        document.body.classList.add(role === 'admin' ? 'mode-admin' : 'mode-distributor');

        const distForm = document.getElementById('form-distributor');
        const adminForm = document.getElementById('form-admin');
        const roleBtns = document.querySelectorAll('.role-btn');

        roleBtns.forEach(b => b.classList.remove('active'));

        if (role === 'admin') {
            if (distForm) distForm.style.display = 'none';
            if (adminForm) adminForm.style.display = 'block';
            if (roleBtns[1]) roleBtns[1].classList.add('active');
        } else {
            if (distForm) distForm.style.display = 'block';
            if (adminForm) adminForm.style.display = 'none';
            if (roleBtns[0]) roleBtns[0].classList.add('active');
        }
    }

    /**
     * Toggle Password Input Visibility
     */
    function togglePassword(inputId, btn) {
        const input = document.getElementById(inputId);
        if (!input) return;

        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = '🙈';
        } else {
            input.type = 'password';
            btn.textContent = '👁️';
        }
    }

    /**
     * Distributor Auth Sub-Tabs (Password vs OTP vs Register)
     */
    function setSubTab(tabName) {
        const passBox = document.getElementById('sub-password');
        const otpBox = document.getElementById('sub-otp');
        const regBox = document.getElementById('sub-register');

        const btns = document.querySelectorAll('.sub-btn');
        btns.forEach(b => b.classList.remove('active'));

        if (passBox) passBox.style.display = tabName === 'password' ? 'block' : 'none';
        if (otpBox) otpBox.style.display = tabName === 'otp' ? 'block' : 'none';
        if (regBox) regBox.style.display = tabName === 'register' ? 'block' : 'none';

        if (tabName === 'password' && btns[0]) btns[0].classList.add('active');
        if (tabName === 'otp' && btns[1]) btns[1].classList.add('active');
        if (tabName === 'register' && btns[2]) btns[2].classList.add('active');
    }

    /**
     * Forgot Password Modal & Resend Timer
     */
    function openModal() {
        const modal = document.getElementById('forgot-modal');
        if (modal) modal.classList.add('active');
        setStep(1);
    }

    function closeModal() {
        const modal = document.getElementById('forgot-modal');
        if (modal) modal.classList.remove('active');
        if (timerId) clearInterval(timerId);
    }

    function setStep(step) {
        document.getElementById('step-1').style.display = step === 1 ? 'block' : 'none';
        document.getElementById('step-2').style.display = step === 2 ? 'block' : 'none';
    }

    function startTimer() {
        if (timerId) clearInterval(timerId);
        let sec = 30;
        const btn = document.getElementById('resend-btn');
        const label = document.getElementById('timer-label');

        if (btn) btn.disabled = true;

        timerId = setInterval(() => {
            sec--;
            if (label) label.textContent = `0:${sec < 10 ? '0' : ''}${sec}`;
            if (sec <= 0) {
                clearInterval(timerId);
                if (btn) btn.disabled = false;
                if (label) label.textContent = 'Ready';
            }
        }, 1000);
    }

    function resendOTP() {
        startTimer();
        toast('OTP Code Resent!');
    }

    /**
     * TASK 6: Modern Purple Gradient Professional Toast Notification Engine
     * Supports types: 'success', 'error' / 'danger', 'warning', 'info'
     * Features: Top-right positioning, auto-dismiss (4.5s), hover pause, manual close, deduplication
     */
    const activeToasts = new Set();

    function showToast(message, type = 'info', title = null, duration = 4500) {
        if (!message) return;
        const cleanMsg = String(message).trim();
        if (!cleanMsg) return;

        let normType = String(type || 'info').toLowerCase();
        if (normType === 'danger') normType = 'error';
        if (!['success', 'error', 'warning', 'info'].includes(normType)) {
            normType = 'info';
        }

        // Deduplication: prevent stacking identical messages within 2 seconds
        const toastKey = `${normType}:${cleanMsg}`;
        if (activeToasts.has(toastKey)) {
            return;
        }
        activeToasts.add(toastKey);
        setTimeout(() => activeToasts.delete(toastKey), 2000);

        // Get or create top-right toast container
        let container = document.getElementById('toastContainer') || document.querySelector('.toast-container') || document.querySelector('.toast-wrap');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        // Configuration with SVG icons & titles
        const config = {
            success: {
                title: title || 'Success',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
            },
            error: {
                title: title || 'Error',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
            },
            warning: {
                title: title || 'Warning',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
            },
            info: {
                title: title || 'Information',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
            }
        }[normType];

        const toast = document.createElement('div');
        toast.className = `toast-item toast-${normType}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', normType === 'error' ? 'assertive' : 'polite');

        // Allow safe HTML like links inside message if present (e.g. PDF download link)
        const isHtml = cleanMsg.includes('<a ') || cleanMsg.includes('<b>') || cleanMsg.includes('<strong>');
        const msgContent = isHtml ? cleanMsg : escapeHtml(cleanMsg);

        toast.innerHTML = `
            <div class="toast-icon-wrap">${config.icon}</div>
            <div class="toast-content">
                <div class="toast-title">${config.title}</div>
                <div class="toast-message">${msgContent}</div>
            </div>
            <button type="button" class="toast-close-btn" aria-label="Close">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
            <div class="toast-progress"></div>
        `;

        container.appendChild(toast);

        let remainingTime = duration;
        let startTime = Date.now();
        let dismissTimer = null;
        const progressEl = toast.querySelector('.toast-progress');

        function startDismissTimer() {
            startTime = Date.now();
            if (progressEl) {
                progressEl.style.transition = `transform ${remainingTime}ms linear`;
                progressEl.style.transform = 'scaleX(0)';
            }
            dismissTimer = setTimeout(dismissToast, remainingTime);
        }

        function pauseDismissTimer() {
            if (dismissTimer) clearTimeout(dismissTimer);
            const elapsed = Date.now() - startTime;
            remainingTime = Math.max(0, remainingTime - elapsed);
            if (progressEl) {
                const computed = window.getComputedStyle(progressEl);
                progressEl.style.transition = 'none';
                progressEl.style.transform = computed.transform;
            }
        }

        function dismissToast() {
            if (toast.classList.contains('toast-hiding')) return;
            toast.classList.add('toast-hiding');
            setTimeout(() => {
                try { toast.remove(); } catch (e) {}
            }, 250);
        }

        // Manual close button
        toast.querySelector('.toast-close-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (dismissTimer) clearTimeout(dismissTimer);
            dismissToast();
        });

        // Hover pause and resume
        toast.addEventListener('mouseenter', pauseDismissTimer);
        toast.addEventListener('mouseleave', startDismissTimer);

        // Start auto-dismiss countdown
        setTimeout(startDismissTimer, 30);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Automatically scan and trigger toasts from Django flash messages
     */
    function initDjangoMessages() {
        // 1. Scan for dedicated structured message elements
        const msgEls = document.querySelectorAll('.django-message, [data-django-message]');
        msgEls.forEach(el => {
            const text = el.getAttribute('data-text') || el.innerHTML.trim();
            const type = el.getAttribute('data-type') || 'info';
            if (text) {
                showToast(text, type);
            }
        });

        // 2. Scan for messages in message containers
        const legacyContainers = document.querySelectorAll('.messages-container, #messages-container, .alert-messages');
        legacyContainers.forEach(container => {
            const alerts = container.querySelectorAll('.alert');
            alerts.forEach(al => {
                const text = al.innerHTML.trim();
                let type = 'info';
                if (al.classList.contains('alert-danger') || al.classList.contains('alert-error')) {
                    type = 'error';
                } else if (al.classList.contains('alert-success')) {
                    type = 'success';
                } else if (al.classList.contains('alert-warning')) {
                    type = 'warning';
                }
                if (text) {
                    showToast(text, type);
                }
            });
        });
    }

    // Attach global showToast
    window.showToast = showToast;

    // Run theme & message initialization when DOM is loaded
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        initDjangoMessages();
    });

    return {
        toggleTheme: toggleTheme,
        setRole: setRole,
        togglePassword: togglePassword,
        setSubTab: setSubTab,
        openModal: openModal,
        closeModal: closeModal,
        resendOTP: resendOTP,
        toast: showToast,
        showToast: showToast,
        initDjangoMessages: initDjangoMessages
    };
})();
