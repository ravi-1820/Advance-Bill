/**
 * ADVANCE BILLING SYSTEM WITH QR - LIGHTWEIGHT FRONTEND HELPER
 * Clean & minimal UI script (Ready for backend API integration)
 */

const AuthModule = (function () {
    let resendTimer = null;

    /**
     * 1. Toggle Password Visibility (Show/Hide)
     */
    function togglePasswordVisibility(inputId, btn) {
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
     * 2. Distributor Login Sub-Tabs (Password vs QR vs OTP)
     */
    function switchSubTab(tabType) {
        const passForm = document.getElementById('sub-form-password');
        const qrForm = document.getElementById('sub-form-qr');
        const otpForm = document.getElementById('sub-form-otp');

        const btns = document.querySelectorAll('.sub-tab-btn');
        btns.forEach(b => b.classList.remove('active'));

        if (passForm) passForm.style.display = tabType === 'password' ? 'block' : 'none';
        if (qrForm) qrForm.style.display = tabType === 'qr' ? 'block' : 'none';
        if (otpForm) otpForm.style.display = tabType === 'otp' ? 'block' : 'none';

        if (tabType === 'password' && btns[0]) btns[0].classList.add('active');
        if (tabType === 'qr' && btns[1]) btns[1].classList.add('active');
        if (tabType === 'otp' && btns[2]) btns[2].classList.add('active');
    }

    /**
     * 3. Forgot Password Modal Controls
     */
    function openForgotPasswordModal(prefillValue = '') {
        const modal = document.getElementById('forgot-password-modal');
        if (modal) {
            modal.classList.add('active');
            setWizardStep(1);
            const input = document.getElementById('reset-email-input');
            if (input && prefillValue) input.value = prefillValue;
        }
    }

    function closeForgotPasswordModal() {
        const modal = document.getElementById('forgot-password-modal');
        if (modal) modal.classList.remove('active');
        if (resendTimer) clearInterval(resendTimer);
    }

    function setWizardStep(stepNum) {
        const s1 = document.getElementById('forgot-step-1');
        const s2 = document.getElementById('forgot-step-2');
        const s3 = document.getElementById('forgot-step-3');

        const pills = document.querySelectorAll('.wizard-step');
        pills.forEach((p, idx) => {
            p.classList.remove('active', 'completed');
            if (idx + 1 === stepNum) p.classList.add('active');
            if (idx + 1 < stepNum) p.classList.add('completed');
        });

        if (s1) s1.style.display = stepNum === 1 ? 'block' : 'none';
        if (s2) s2.style.display = stepNum === 2 ? 'block' : 'none';
        if (s3) s3.style.display = stepNum === 3 ? 'block' : 'none';
    }

    /**
     * 4. OTP Resend Timer (UI Only)
     */
    function requestResetOTP(e) {
        if (e) e.preventDefault();
        setWizardStep(2);
        startResendTimer();
    }

    function startResendTimer() {
        if (resendTimer) clearInterval(resendTimer);
        let seconds = 30;
        const btn = document.getElementById('btn-resend-otp');
        const display = document.getElementById('otp-timer-display');

        if (btn) btn.disabled = true;

        resendTimer = setInterval(() => {
            seconds--;
            if (display) display.textContent = `Resend in 0:${seconds < 10 ? '0' : ''}${seconds}`;

            if (seconds <= 0) {
                clearInterval(resendTimer);
                if (btn) btn.disabled = false;
                if (display) display.textContent = 'Resend Ready';
            }
        }, 1000);
    }

    function resendOTP() {
        startResendTimer();
        AppRouter.showToast('OTP code resent!', 'info');
    }

    function verifyResetOTP(e) {
        if (e) e.preventDefault();
        setWizardStep(3);
    }

    function saveNewPassword(e) {
        if (e) e.preventDefault();
        AppRouter.showToast('Password updated!', 'success');
        closeForgotPasswordModal();
    }

    /**
     * 5. Backend Form Submit Handlers (Minimal Frontend Forwarder)
     * Replace these dummy functions with real backend API calls (e.g. fetch('/api/login')) when connecting to backend.
     */
    function handleAdminLogin(e) {
        if (e) e.preventDefault();
        // BACKEND API HOOK: fetch('/api/admin/login', { method: 'POST', body: ... })
        AppRouter.setSession({ role: 'admin', name: 'Admin User' });
        window.location.hash = '#/admin/dashboard';
    }

    function handleDistributorLogin(e) {
        if (e) e.preventDefault();
        // BACKEND API HOOK: fetch('/api/distributor/login', { method: 'POST', body: ... })
        AppRouter.setSession({ role: 'distributor', name: 'Distributor User' });
        window.location.hash = '#/distributor/dashboard';
    }

    function simulateQRScan() {
        AppRouter.setSession({ role: 'distributor', name: 'QR Partner' });
        window.location.hash = '#/distributor/dashboard';
    }

    function logout() {
        AppRouter.clearSession();
        window.location.hash = '#/distributor/login';
    }

    // Public UI Methods
    return {
        togglePasswordVisibility: togglePasswordVisibility,
        switchSubTab: switchSubTab,
        openForgotPasswordModal: openForgotPasswordModal,
        closeForgotPasswordModal: closeForgotPasswordModal,
        requestResetOTP: requestResetOTP,
        resendOTP: resendOTP,
        verifyResetOTP: verifyResetOTP,
        saveNewPassword: saveNewPassword,
        handleAdminLogin: handleAdminLogin,
        handleDistributorLogin: handleDistributorLogin,
        simulateQRScan: simulateQRScan,
        logout: logout
    };
})();
