// GET  /api/watchlist?email=xxx — returns the user's watchlist (array of tickers)
// POST /api/watchlist — body: {email, ticker, action: 'add'|'remove'}
// KV key: watchlist:{email} — value: JSON array of ticker strings

const HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*'
};

function normalizeEmail(email) {
    return (email || '').toLowerCase().trim();
}

function isValidEmail(email) {
    return email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// GET /api/watchlist?email=xxx
export async function onRequestGet(context) {
    const { env } = context;
    const url = new URL(context.request.url);
    const email = normalizeEmail(url.searchParams.get('email'));

    if (!isValidEmail(email))
        return new Response(JSON.stringify({ error: 'Invalid or missing email.' }), { status: 400, headers: HEADERS });

    const key = `watchlist:${email}`;
    const data = await env.SUBSCRIBERS.get(key);
    const tickers = data ? JSON.parse(data) : [];

    return new Response(JSON.stringify({ email, tickers }), { status: 200, headers: HEADERS });
}

// POST /api/watchlist
export async function onRequestPost(context) {
    const { request, env } = context;

    try {
        const body = await request.json();
        const email = normalizeEmail(body.email);
        const ticker = (body.ticker || '').toUpperCase().trim();
        const action = (body.action || '').toLowerCase();

        if (!isValidEmail(email))
            return new Response(JSON.stringify({ error: 'Invalid or missing email.' }), { status: 400, headers: HEADERS });

        if (!ticker)
            return new Response(JSON.stringify({ error: 'Missing ticker.' }), { status: 400, headers: HEADERS });

        if (!['add', 'remove'].includes(action))
            return new Response(JSON.stringify({ error: "Action must be 'add' or 'remove'." }), { status: 400, headers: HEADERS });

        const key = `watchlist:${email}`;
        const existing = await env.SUBSCRIBERS.get(key);
        let tickers = existing ? JSON.parse(existing) : [];

        if (action === 'add') {
            if (!tickers.includes(ticker)) {
                tickers.push(ticker);
                tickers.sort();
            }
        } else {
            tickers = tickers.filter(t => t !== ticker);
        }

        await env.SUBSCRIBERS.put(key, JSON.stringify(tickers));

        return new Response(JSON.stringify({ email, tickers, message: `${ticker} ${action === 'add' ? 'added to' : 'removed from'} watchlist.` }), { status: 200, headers: HEADERS });
    } catch (err) {
        return new Response(JSON.stringify({ error: 'Invalid request body.' }), { status: 400, headers: HEADERS });
    }
}

// Handle CORS preflight
export async function onRequestOptions() {
    return new Response(null, {
        status: 204,
        headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
    });
}
