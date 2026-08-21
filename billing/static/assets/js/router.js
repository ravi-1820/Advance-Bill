/**
 * ADVANCE BILLING SYSTEM WITH QR - MINIMAL ROUTER & UI HELPER
 */

const AppRouter = (function () {
    const SESSION_KEY = 'abs_session_auth';

    function getSession() {
        try {
            return JSON.parse(localStorage.getItem(SESSION_KEY));
        } catch (e) {
            return null;
        }
    }

    function setSession(userObj) {
        localStorage.setItem(SESSION_KEY, JSON.stringify(userObj));
    }

    function clearSession() {
        localStorage.removeItem(SESSION_KEY);
    }

    function navigate() {
        let hash = window.location.hash.replace('#/', '').replace('#', '');
        if (!hash) hash = 'distributor-login';
        if (hash === 'admin') hash = 'admin-login';
        if (hash === 'distributor') hash = 'distributor-login';

        // Apply Theme Class
        if (hash.startsWith('admin')) {
            document.body.className = 'theme-admin';
        } else {
            document.body.className = 'theme-distributor';
        }

        // View Toggler for SPA
        const views = document.querySelectorAll('.app-view');
        views.forEach(v => v.style.display = 'none');

        const activeView = document.getElementById(`view-${hash}`);
        if (activeView) activeView.style.display = 'block';

        // Highlight Nav Pills
        const pills = document.querySelectorAll('.nav-pill');
        pills.forEach(p => {
            p.classList.remove('active');
            const target = p.getAttribute('data-route');
            if (target && hash.startsWith(target)) p.classList.add('active');
        });
    }

    function showToast(message, type = 'info') {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️'}</span> ${message}`;
        container.appendChild(toast);

        setTimeout(() => toast.remove(), 3000);
    }

    window.addEventListener('hashchange', navigate);
    window.addEventListener('DOMContentLoaded', navigate);

    return {
        getSession: getSession,
        setSession: setSession,
        clearSession: clearSession,
        showToast: showToast
    };
})();
