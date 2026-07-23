function backend() {
  return String(process.env.SEMBIOTIC_BACKEND_URL || "").trim().replace(/\/+$/, "");
}

module.exports = async function mediaManifest(req, res) {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.setHeader("Allow", "GET, HEAD");
    return res.status(405).json({error: "method not allowed"});
  }
  const base = backend();
  if (!base) return res.status(503).json({error: "SEMBIOTIC_BACKEND_URL is not configured"});
  try {
    const upstream = await fetch(`${base}/field/v1/media-manifest`, {
      method: req.method,
      headers: {
        accept: "application/json",
        "ngrok-skip-browser-warning": "1",
        "user-agent": "SEMBIOTIC/1.0"
      },
      redirect: "follow",
      signal: AbortSignal.timeout(20000)
    });
    const body = Buffer.from(await upstream.arrayBuffer());
    res.status(upstream.status);
    res.setHeader("Content-Type", upstream.headers.get("content-type") || "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    if (req.method === "HEAD") return res.end();
    return res.send(body);
  } catch (error) {
    return res.status(502).json({
      error: "Sembiotic media manifest is unreachable",
      detail: error instanceof Error ? error.message : String(error)
    });
  }
};
