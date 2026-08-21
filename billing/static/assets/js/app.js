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
     * Distributor Auth Sub-Tabs (Password vs QR vs OTP)
     */
    function setSubTab(tabName) {
        const passBox = document.getElementById('sub-password');
        const qrBox = document.getElementById('sub-qr');
        const otpBox = document.getElementById('sub-otp');

        const btns = document.querySelectorAll('.sub-btn');
        btns.forEach(b => b.classList.remove('active'));

        if (passBox) passBox.style.display = tabName === 'password' ? 'block' : 'none';
        if (qrBox) qrBox.style.display = tabName === 'qr' ? 'block' : 'none';
        if (otpBox) otpBox.style.display = tabName === 'otp' ? 'block' : 'none';

        if (tabName === 'password' && btns[0]) btns[0].classList.add('active');
        if (tabName === 'qr' && btns[1]) btns[1].classList.add('active');
        if (tabName === 'otp' && btns[2]) btns[2].classList.add('active');
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
        document.getElementById('step-3').style.display = step === 3 ? 'block' : 'none';
    }

    function sendOTP(e) {
        if (e) e.preventDefault();
        setStep(2);
        startTimer();
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

    function verifyOTP(e) {
        if (e) e.preventDefault();
        setStep(3);
    }

    function savePassword(e) {
        if (e) e.preventDefault();
        toast('Password Updated Successfully!');
        closeModal();
    }

    /**
     * Demo Toast Helper
     */
    function toast(msg) {
        let wrap = document.querySelector('.toast-wrap');
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.className = 'toast-wrap';
            document.body.appendChild(wrap);
        }

        const div = document.createElement('div');
        div.className = 'toast-msg';
        div.textContent = msg;
        wrap.appendChild(div);

        setTimeout(() => div.remove(), 2500);
    }

    // Run theme initialization when DOM is loaded
    document.addEventListener('DOMContentLoaded', initTheme);

    return {
        toggleTheme: toggleTheme,
        setRole: setRole,
        togglePassword: togglePassword,
        setSubTab: setSubTab,
        openModal: openModal,
        closeModal: closeModal,
        sendOTP: sendOTP,
        startTimer: startTimer,
        resendOTP: resendOTP,
        verifyOTP: verifyOTP,
        savePassword: savePassword,
        toast: toast
    };
})();
