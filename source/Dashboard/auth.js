// Inspection & Intel — Gateway-Aware Authentication
// Validates against __PROJECT_DOMAIN__ gateway, falls back to local auth
// Fetches use AbortController with 8s timeout; localStorage is try/catch wrapped
(function() {
    var TOKEN_KEY = 'ii_token';
    var USER_KEY = 'ii_user';
    var SITE_ID = 'inspection';
    var GATEWAY = 'https://sector-intel-hub.pages.dev';
    var FETCH_TIMEOUT_MS = 8000;

    // Safe localStorage wrappers (Safari private mode / disabled-storage throw)
    function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
    function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
    function lsRemove(k) { try { localStorage.removeItem(k); } catch (e) {} }

    function fetchWithTimeout(url, opts) {
        opts = opts || {};
        var c = new AbortController();
        var t = setTimeout(function() { c.abort(); }, FETCH_TIMEOUT_MS);
        opts.signal = c.signal;
        return fetch(url, opts).finally(function() { clearTimeout(t); });
    }

    // Skip auth on login page
    if (window.location.pathname === '/login.html') return;

    // Check for gateway_token in URL (arriving from hub)
    var params = new URLSearchParams(window.location.search);
    var gatewayToken = params.get('gateway_token');
    if (gatewayToken) {
        lsSet(TOKEN_KEY, gatewayToken);
        params.delete('gateway_token');
        var cleanUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
        history.replaceState(null, '', cleanUrl);
    }

    var token = lsGet(TOKEN_KEY);
    if (!token) {
        window.location.href = GATEWAY + '/login.html?redirect=' + encodeURIComponent(window.location.href);
        return;
    }

    function showPage(user) {
        window.SITE_USER = user;
        if (user && user.role === 'admin') {
            function showAdminLink() {
                var el = document.getElementById('admin-nav-link');
                if (el) el.style.display = '';
            }
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', showAdminLink);
            } else {
                showAdminLink();
            }
        }
    }

    function clearAndRedirect() {
        lsRemove(TOKEN_KEY);
        lsRemove(USER_KEY);
        window.location.href = GATEWAY + '/login.html?redirect=' + encodeURIComponent(window.location.href);
    }

    // Try gateway validation first (with timeout)
    fetchWithTimeout(GATEWAY + '/api/auth/validate?token=' + encodeURIComponent(token) + '&site=' + SITE_ID)
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (data.valid) {
                lsSet(USER_KEY, JSON.stringify(data.user));
                showPage(data.user);
            } else {
                clearAndRedirect();
            }
        })
        .catch(function() {
            // Gateway unreachable — clear session and redirect to hub login.
            clearAndRedirect();
        });

    // Global logout — clears both gateway and local sessions
    window.iiLogout = function() {
        var t = lsGet(TOKEN_KEY);
        if (t) {
            fetchWithTimeout(GATEWAY + '/api/auth/logout', { method: 'POST', headers: { 'Authorization': 'Bearer ' + t } }).catch(function(){});
        }
        lsRemove(TOKEN_KEY);
        lsRemove(USER_KEY);
        window.location.href = GATEWAY + '/login.html';
    };
})();
