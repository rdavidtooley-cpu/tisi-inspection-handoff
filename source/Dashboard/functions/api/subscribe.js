// Cloudflare Pages Function — POST /api/subscribe
// Requires KV namespace binding: SUBSCRIBERS

export async function onRequestPost(context) {
    const { request, env } = context;

    // CORS headers
    const headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
    };

    try {
        const { email, frequency } = await request.json();

        // Validate email
        if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            return new Response(JSON.stringify({ error: 'Please enter a valid email address.' }), {
                status: 400, headers
            });
        }

        // Validate frequency
        if (!['daily', 'weekly'].includes(frequency)) {
            return new Response(JSON.stringify({ error: 'Frequency must be daily or weekly.' }), {
                status: 400, headers
            });
        }

        // Check if KV is bound
        if (!env.SUBSCRIBERS) {
            console.error('SUBSCRIBERS KV namespace not bound');
            return new Response(JSON.stringify({ error: 'Service not configured. Please contact admin.' }), {
                status: 500, headers
            });
        }

        const normalizedEmail = email.toLowerCase().trim();
        const key = `sub:${normalizedEmail}`;

        // Check if already subscribed
        const existing = await env.SUBSCRIBERS.get(key);
        if (existing) {
            const data = JSON.parse(existing);
            if (data.frequency === frequency) {
                return new Response(JSON.stringify({ message: 'You are already subscribed with this frequency.' }), {
                    status: 200, headers
                });
            }
            // Update frequency
            data.frequency = frequency;
            data.updatedAt = new Date().toISOString();
            await env.SUBSCRIBERS.put(key, JSON.stringify(data));
            return new Response(JSON.stringify({ message: `Subscription updated to ${frequency}.` }), {
                status: 200, headers
            });
        }

        // Store new subscriber
        const subscriber = {
            email: normalizedEmail,
            frequency,
            subscribedAt: new Date().toISOString(),
            active: true
        };

        await env.SUBSCRIBERS.put(key, JSON.stringify(subscriber));

        // Also maintain an index of all subscriber emails for easy listing
        let index = [];
        const indexData = await env.SUBSCRIBERS.get('_index');
        if (indexData) {
            index = JSON.parse(indexData);
        }
        if (!index.includes(normalizedEmail)) {
            index.push(normalizedEmail);
            await env.SUBSCRIBERS.put('_index', JSON.stringify(index));
        }

        return new Response(JSON.stringify({ message: 'Successfully subscribed!' }), {
            status: 200, headers
        });

    } catch (err) {
        console.error('Subscribe error:', err);
        return new Response(JSON.stringify({ error: 'An unexpected error occurred.' }), {
            status: 500, headers
        });
    }
}

// Handle CORS preflight
export async function onRequestOptions() {
    return new Response(null, {
        status: 204,
        headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
    });
}
