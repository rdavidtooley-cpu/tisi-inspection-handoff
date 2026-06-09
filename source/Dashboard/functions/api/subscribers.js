// Cloudflare Pages Function — GET /api/subscribers
// Protected endpoint to list subscribers for the digest sender
// Requires KV namespace binding: SUBSCRIBERS
// Requires environment variable: API_SECRET

export async function onRequestGet(context) {
    const { request, env } = context;

    const headers = {
        'Content-Type': 'application/json',
    };

    // Authenticate with secret key (passed as Bearer token or query param)
    const authHeader = request.headers.get('Authorization');
    const url = new URL(request.url);
    const token = authHeader?.replace('Bearer ', '') || url.searchParams.get('key');

    if (!env.API_SECRET || token !== env.API_SECRET) {
        return new Response(JSON.stringify({ error: 'Unauthorized' }), {
            status: 401, headers
        });
    }

    // Optional frequency filter
    const frequencyFilter = url.searchParams.get('frequency'); // 'daily' or 'weekly'

    try {
        const indexData = await env.SUBSCRIBERS.get('_index');
        if (!indexData) {
            return new Response(JSON.stringify({ subscribers: [], count: 0 }), {
                status: 200, headers
            });
        }

        const emails = JSON.parse(indexData);
        const subscribers = [];

        for (const email of emails) {
            const data = await env.SUBSCRIBERS.get(`sub:${email}`);
            if (data) {
                const sub = JSON.parse(data);
                if (sub.active !== false) {
                    if (!frequencyFilter || sub.frequency === frequencyFilter) {
                        subscribers.push(sub);
                    }
                }
            }
        }

        return new Response(JSON.stringify({ subscribers, count: subscribers.length }), {
            status: 200, headers
        });

    } catch (err) {
        console.error('List subscribers error:', err);
        return new Response(JSON.stringify({ error: 'Failed to list subscribers.' }), {
            status: 500, headers
        });
    }
}
