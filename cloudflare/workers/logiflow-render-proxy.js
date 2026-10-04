/**
 * @deprecated Not used in production. Vercel calls the AppSail backend directly.
 * Legacy edge proxy (originally Render → Cloud Run → now Zoho Catalyst AppSail). See docs/miscellaneous/cloudflare-legacy.md.
 */
const ORIGIN = "https://logiflow-50046515745.development.catalystappsail.in";

export default {
  async fetch(request) {
    const incoming = new URL(request.url);

    if (incoming.pathname === "/" && request.method === "GET") {
      return new Response(
        JSON.stringify({
          service: "logiflow-render-proxy",
          origin: ORIGIN,
          health: "/health",
        }),
        { headers: { "content-type": "application/json" } },
      );
    }

    const target = new URL(incoming.pathname + incoming.search, ORIGIN);
    const headers = new Headers(request.headers);
    headers.set("Host", "logiflow-50046515745.development.catalystappsail.in");
    headers.set(
      "X-Forwarded-For",
      request.headers.get("CF-Connecting-IP") ||
        request.headers.get("X-Forwarded-For") ||
        "",
    );
    headers.set("X-Forwarded-Proto", "https");

    const init = { method: request.method, headers, redirect: "follow" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    try {
      const response = await fetch(target.toString(), init);
      const outHeaders = new Headers(response.headers);
      outHeaders.set("X-LogiFlow-Proxy", "cloudflare-workers");
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: outHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Origin unreachable", detail: String(err) }),
        { status: 502, headers: { "content-type": "application/json" } },
      );
    }
  },
};
