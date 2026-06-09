// Cloudflare Pages Function — GET /api/unsubscribe?email=...
// Marks a subscriber as inactive
// Requires KV namespace binding: SUBSCRIBERS

export async function onRequestGet(context) {
    const { request, env } = context;
    const url = new URL(request.url);
    const email = url.searchParams.get('email');

    if (!email) {
        return new Response('<h2>Invalid unsubscribe link.</h2>', {
            status: 400,
            headers: { 'Content-Type': 'text/html' }
        });
    }

    const normalizedEmail = decodeURIComponent(email).toLowerCase().trim();
    const key = `sub:${normalizedEmail}`;

    try {
        const existing = await env.SUBSCRIBERS.get(key);
        if (existing) {
            const data = JSON.parse(existing);
            data.active = false;
            data.unsubscribedAt = new Date().toISOString();
            await env.SUBSCRIBERS.put(key, JSON.stringify(data));
        }

        return new Response(`
            <!DOCTYPE html>
            <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Unsubscribed — Inspection Intel</title>
            <style>body{background:#0f1117;color:#e8eaed;font-family:-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;}
            .box{text-align:center;max-width:400px;padding:40px;}h1{font-size:22px;margin-bottom:12px;}p{color:#9aa0a6;font-size:14px;}a{color:#4fc3f7;text-decoration:none;}</style>
            </head><body><div class="box">
            <h1>You've been unsubscribed</h1>
            <p>You won't receive any more digest emails from Inspection Intel.</p>
            <p style="margin-top:20px;"><a href="/">← Back to Dashboards</a></p>
            </div></body></html>
        `, {
            status: 200,
            headers: { 'Content-Type': 'text/html' }
        });
    } catch (err) {
        console.error('Unsubscribe error:', err);
        return new Response('<h2>Something went wrong. Please try again.</h2>', {
            status: 500,
            headers: { 'Content-Type': 'text/html' }
        });
    }
}
