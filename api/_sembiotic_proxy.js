function backendOrigin() {
  const value = String(
    process.env.SEMBIOTIC_BACKEND_URL || ""
  ).trim();

  if (!value) {
    throw new Error(
      "SEMBIOTIC_BACKEND_URL is not configured"
    );
  }

  return value.replace(/\/+$/, "");
}

async function requestBody(req) {
  if (
    req.body !== undefined &&
    req.body !== null
  ) {
    if (Buffer.isBuffer(req.body)) {
      return req.body;
    }

    if (typeof req.body === "string") {
      return Buffer.from(req.body);
    }

    return Buffer.from(
      JSON.stringify(req.body)
    );
  }

  const chunks = [];

  for await (const chunk of req) {
    chunks.push(
      Buffer.isBuffer(chunk)
        ? chunk
        : Buffer.from(chunk)
    );
  }

  return chunks.length
    ? Buffer.concat(chunks)
    : undefined;
}

async function proxyJson(
  req,
  res,
  pathname,
  allowedMethods,
  timeoutMs
) {
  const method = String(
    req.method || "GET"
  ).toUpperCase();

  if (!allowedMethods.includes(method)) {
    res.statusCode = 405;
    res.setHeader(
      "Allow",
      allowedMethods.join(", ")
    );
    res.setHeader(
      "Content-Type",
      "application/json; charset=utf-8"
    );
    res.end(
      JSON.stringify({
        error: "method not allowed"
      })
    );
    return;
  }

  let timer;

  try {
    const origin = backendOrigin();
    const incomingUrl = new URL(
      req.url,
      "https://sembiotic.invalid"
    );

    const upstreamUrl =
      origin +
      pathname +
      incomingUrl.search;

    const controller =
      new AbortController();

    timer = setTimeout(
      () => controller.abort(),
      timeoutMs
    );

    const headers = {
      Accept: "application/json",
      "User-Agent":
        "SEMBIOTIC-VERCEL-PROXY/2.0"
    };

    let body;

    if (
      method !== "GET" &&
      method !== "HEAD"
    ) {
      body = await requestBody(req);

      headers["Content-Type"] =
        String(
          req.headers["content-type"] ||
          "application/json"
        );
    }

    const upstream = await fetch(
      upstreamUrl,
      {
        method,
        headers,
        body,
        signal: controller.signal,
        cache: "no-store"
      }
    );

    const responseBody = Buffer.from(
      await upstream.arrayBuffer()
    );

    res.statusCode = upstream.status;

    res.setHeader(
      "Content-Type",
      upstream.headers.get(
        "content-type"
      ) ||
      "application/json; charset=utf-8"
    );

    res.setHeader(
      "Cache-Control",
      upstream.headers.get(
        "cache-control"
      ) ||
      "no-store"
    );

    res.setHeader(
      "X-Sembiotic-Proxy",
      "vercel-to-local-field"
    );

    if (method === "HEAD") {
      res.end();
      return;
    }

    res.setHeader(
      "Content-Length",
      String(responseBody.length)
    );

    res.end(responseBody);

  } catch (error) {
    const timeout =
      error &&
      error.name === "AbortError";

    const payload = Buffer.from(
      JSON.stringify({
        error: timeout
          ? "Sembiotic field request timed out"
          : "Sembiotic field backend is unreachable",
        detail:
          error instanceof Error
            ? error.message
            : String(error)
      })
    );

    res.statusCode = timeout
      ? 504
      : 502;

    res.setHeader(
      "Content-Type",
      "application/json; charset=utf-8"
    );

    res.setHeader(
      "Cache-Control",
      "no-store"
    );

    res.setHeader(
      "Content-Length",
      String(payload.length)
    );

    res.end(payload);

  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

module.exports = {
  proxyJson
};
