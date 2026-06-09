// Cloudflare Pages Function — Finnhub quote proxy
// Fetches live quotes for NDT universe, caches 30s to stay within free tier (60 calls/min)

const TICKERS = [
  { yf: 'MG',      fh: 'MG',      display: 'MG',   name: 'Mistras' },
  { yf: 'TISI',    fh: 'TISI',    display: 'TISI', name: 'Team' },
  { yf: 'TIC',     fh: 'TIC',     display: 'TIC',  name: 'Acuren' },
  { yf: 'OII',     fh: 'OII',     display: 'OII',  name: 'Oceaneering' },
  { yf: 'XPRO',    fh: 'XPRO',    display: 'XPRO', name: 'Expro' },
  { yf: 'TRNS',    fh: 'TRNS',    display: 'TRNS', name: 'Transcat' },
  { yf: 'THR',     fh: 'THR',     display: 'THR',  name: 'Thermon' },
  { yf: 'BVI.PA',  fh: 'BVI.PA',  display: 'BVI',  name: 'Bureau Veritas' },
  { yf: 'ITRK.L',  fh: 'ITRK.L',  display: 'ITRK', name: 'Intertek' },
  { yf: 'COTN.SW', fh: 'COTN.SW', display: 'COTN', name: 'Comet' },
];

let cache = { data: null, ts: 0 };
const CACHE_TTL = 30000; // 30 seconds

export async function onRequest(context) {
  const now = Date.now();

  // Return cached data if fresh
  if (cache.data && (now - cache.ts) < CACHE_TTL) {
    return new Response(JSON.stringify(cache.data), {
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=30' },
    });
  }

  const apiKey = context.env.FINNHUB_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'API key not configured' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
    });
  }

  try {
    // Fetch all quotes in parallel
    const results = await Promise.allSettled(
      TICKERS.map(async (t) => {
        const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${t.fh}&token=${apiKey}`);
        if (!res.ok) return null;
        const q = await res.json();
        if (!q.c || q.c === 0) return null;
        return {
          ticker: t.yf,
          display: t.display,
          name: t.name,
          price: q.c,
          change: q.d,
          changePct: q.dp,
          high: q.h,
          low: q.l,
          prevClose: q.pc,
          timestamp: q.t,
        };
      })
    );

    const quotes = results
      .filter(r => r.status === 'fulfilled' && r.value)
      .map(r => r.value);

    const payload = { quotes, updated: new Date().toISOString() };
    /* __cache_only_nonempty_v1 */ if ((payload.quotes||[]).length > 0) cache = { data: payload, ts: now };

    return new Response(JSON.stringify(payload), {
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=30' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
    });
  }
}
