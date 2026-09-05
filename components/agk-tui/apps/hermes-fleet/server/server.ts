import { createReadStream, realpathSync } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer, request as createUpstreamRequest } from "node:http";
import type {
  IncomingHttpHeaders,
  IncomingMessage,
  OutgoingHttpHeaders,
  Server,
  ServerResponse,
} from "node:http";
import { extname, relative, resolve, sep } from "node:path";
import type { Duplex } from "node:stream";
import { fileURLToPath } from "node:url";

import {
  ORGANISATIONS,
  type OrganisationId,
} from "../src/organisations.js";

export const FLEET_LISTEN_HOST = "127.0.0.1";
export const DEFAULT_FLEET_PORT = 8459;

const LOOPBACK_HOSTS = ["localhost", "127.0.0.1"] as const;
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const CONTENT_TYPES: Readonly<Record<string, string>> = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

interface UpstreamTarget {
  id: OrganisationId;
  host: typeof FLEET_LISTEN_HOST;
  port: number;
  prefix: string;
}

export interface FleetServerOptions {
  allowedHosts?: readonly string[] | string;
  distDir?: string;
  upstreamPorts?: Partial<Record<OrganisationId, number>>;
  onProxyError?: (error: Error, target: OrganisationId) => void;
}

interface RequestAuthorization {
  allowed: boolean;
  status: number;
  message: string;
}

function canonicalHostname(value: string): string | null {
  const candidate = value.trim();
  if (!candidate || candidate.includes("/") || candidate.includes("@")) {
    return null;
  }

  try {
    const url = new URL(`http://${candidate}`);
    return url.hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return null;
  }
}

export function parseAllowedHosts(
  configured: readonly string[] | string | undefined =
    process.env.HERMES_FLEET_ALLOWED_HOSTS,
): ReadonlySet<string> {
  const values = Array.isArray(configured)
    ? configured
    : typeof configured === "string"
      ? configured.split(",")
      : [];
  const allowed = new Set<string>(LOOPBACK_HOSTS);

  for (const value of values) {
    const hostname = canonicalHostname(value);
    if (!hostname) {
      throw new Error(`Invalid HERMES_FLEET_ALLOWED_HOSTS entry: ${value}`);
    }
    allowed.add(hostname);
  }

  return allowed;
}

function originHostname(origin: string): string | null {
  try {
    const parsed = new URL(origin);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return null;
  }
}

function authorizeRequest(
  request: IncomingMessage,
  allowedHosts: ReadonlySet<string>,
): RequestAuthorization {
  const host = request.headers.host;
  const hostname = host ? canonicalHostname(host) : null;
  if (!hostname || !allowedHosts.has(hostname)) {
    return { allowed: false, status: 421, message: "Host is not allowed" };
  }

  const origin = request.headers.origin;
  if (origin) {
    const hostnameFromOrigin = originHostname(origin);
    if (
      !hostnameFromOrigin ||
      !allowedHosts.has(hostnameFromOrigin) ||
      hostnameFromOrigin !== hostname
    ) {
      return { allowed: false, status: 403, message: "Origin is not allowed" };
    }
  }

  return { allowed: true, status: 200, message: "OK" };
}

function parseRequestTarget(value: string | undefined): URL | null {
  const target = value ?? "/";
  // Fleet is an origin server, not a forward proxy. Reject alternate authority
  // forms and URL parser exceptions before either HTTP or WebSocket routing.
  if (!target.startsWith("/") || target.startsWith("//") || /[\\\x00-\x20\x7f#]/.test(target)) {
    return null;
  }
  try {
    return new URL(target, "http://fleet.invalid");
  } catch {
    return null;
  }
}

function makeUpstreams(
  portOverrides: FleetServerOptions["upstreamPorts"] = {},
): readonly UpstreamTarget[] {
  return ORGANISATIONS.map((organisation) => ({
    id: organisation.id,
    host: FLEET_LISTEN_HOST,
    port: portOverrides[organisation.id] ?? organisation.port,
    prefix: organisation.path,
  }));
}

function targetForPath(
  pathname: string,
  upstreams: readonly UpstreamTarget[],
): UpstreamTarget | null {
  return (
    upstreams.find((target) => {
      const withoutTrailingSlash = target.prefix.slice(0, -1);
      return pathname === withoutTrailingSlash || pathname.startsWith(target.prefix);
    }) ?? null
  );
}

function targetForUnprefixedAsset(
  request: IncomingMessage,
  pathname: string,
  upstreams: readonly UpstreamTarget[],
): UpstreamTarget | null {
  if (!pathname.startsWith("/assets/")) {
    return null;
  }

  const referer = request.headers.referer;
  const requestHost = request.headers.host;
  if (!referer || !requestHost) {
    return null;
  }

  try {
    const refererUrl = new URL(referer);
    if (refererUrl.hostname !== canonicalHostname(requestHost)) {
      return null;
    }
    return targetForPath(refererUrl.pathname, upstreams);
  } catch {
    return null;
  }
}

function upstreamPath(requestUrl: string, target: UpstreamTarget): string {
  const parsed = new URL(requestUrl, "http://fleet.invalid");
  const prefixWithoutTrailingSlash = target.prefix.slice(0, -1);
  const stripped = parsed.pathname.slice(prefixWithoutTrailingSlash.length);
  return `${stripped || "/"}${parsed.search}`;
}

function cloneProxyHeaders(
  source: IncomingHttpHeaders,
  request: IncomingMessage,
  target: UpstreamTarget,
  websocket: boolean,
): OutgoingHttpHeaders {
  const headers: OutgoingHttpHeaders = {};

  for (const [name, value] of Object.entries(source)) {
    if (!HOP_BY_HOP_HEADERS.has(name) && value !== undefined) {
      headers[name] = value;
    }
  }

  const upstreamAuthority = `${target.host}:${target.port}`;
  headers.host = upstreamAuthority;
  headers["x-forwarded-host"] = request.headers.host ?? "";
  headers["x-forwarded-prefix"] = target.prefix.slice(0, -1);
  headers["x-forwarded-proto"] = "https";

  if (request.headers.origin) {
    headers.origin = `http://${upstreamAuthority}`;
  }

  if (websocket) {
    headers.connection = "Upgrade";
    headers.upgrade = request.headers.upgrade ?? "websocket";
  }

  return headers;
}

function rewriteLocation(value: string, target: UpstreamTarget): string {
  if (value.startsWith("/") && !value.startsWith("//")) {
    return `${target.prefix.slice(0, -1)}${value}`;
  }

  try {
    const location = new URL(value);
    if (
      location.hostname === target.host &&
      Number(location.port || (location.protocol === "https:" ? 443 : 80)) ===
        target.port
    ) {
      return `${target.prefix.slice(0, -1)}${location.pathname}${location.search}${location.hash}`;
    }
  } catch {
    // Relative redirect values already stay below the proxied prefix.
  }

  return value;
}

function rewriteSetCookie(value: string, target: UpstreamTarget): string {
  const prefix = target.prefix;
  if (/;\s*Path=/i.test(value)) {
    return value.replace(
      /;\s*Path=(\/[^;]*)/i,
      (_match, upstreamCookiePath: string) =>
        `; Path=${prefix.slice(0, -1)}${upstreamCookiePath}`,
    );
  }
  return `${value}; Path=${prefix}`;
}

function responseHeaders(
  headers: IncomingHttpHeaders,
  target: UpstreamTarget,
): OutgoingHttpHeaders {
  const result: OutgoingHttpHeaders = {};

  for (const [name, value] of Object.entries(headers)) {
    if (HOP_BY_HOP_HEADERS.has(name) || value === undefined) {
      continue;
    }
    if (name === "location" && typeof value === "string") {
      result[name] = rewriteLocation(value, target);
    } else if (name === "set-cookie") {
      const cookies = Array.isArray(value) ? value : [value];
      result[name] = cookies.map((cookie) => rewriteSetCookie(cookie, target));
    } else {
      result[name] = value;
    }
  }

  return result;
}

function sendText(
  response: ServerResponse,
  status: number,
  message: string,
): void {
  const body = `${message}\n`;
  response.writeHead(status, {
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
    "content-type": "text/plain; charset=utf-8",
    "x-content-type-options": "nosniff",
  });
  response.end(body);
}

function proxyHttp(
  request: IncomingMessage,
  response: ServerResponse,
  target: UpstreamTarget,
  onProxyError: NonNullable<FleetServerOptions["onProxyError"]>,
  pathOverride?: string,
): void {
  const proxyRequest = createUpstreamRequest(
    {
      host: target.host,
      port: target.port,
      method: request.method,
      path: pathOverride ?? upstreamPath(request.url ?? "/", target),
      headers: cloneProxyHeaders(request.headers, request, target, false),
      agent: false,
    },
    (proxyResponse) => {
      response.writeHead(
        proxyResponse.statusCode ?? 502,
        proxyResponse.statusMessage,
        responseHeaders(proxyResponse.headers, target),
      );
      proxyResponse.on("error", (error) => response.destroy(error));
      proxyResponse.pipe(response);
    },
  );

  proxyRequest.on("error", (error) => {
    onProxyError(error, target.id);
    if (!response.headersSent) {
      sendText(response, 502, "Hermes dashboard is unavailable");
    } else {
      response.destroy(error);
    }
  });

  request.on("aborted", () => proxyRequest.destroy());
  request.on("error", (error) => proxyRequest.destroy(error));
  request.pipe(proxyRequest);
}

function contentType(filePath: string): string {
  return CONTENT_TYPES[extname(filePath).toLowerCase()] ?? "application/octet-stream";
}

async function serveStatic(
  request: IncomingMessage,
  response: ServerResponse,
  distDir: string,
): Promise<void> {
  const parsed = new URL(request.url ?? "/", "http://fleet.invalid");
  let decodedPath: string;
  try {
    decodedPath = decodeURIComponent(parsed.pathname);
  } catch {
    sendText(response, 400, "Malformed request path");
    return;
  }

  const relativePath = decodedPath === "/" ? "index.html" : decodedPath.replace(/^\/+/, "");
  let filePath = resolve(distDir, relativePath);
  const relativeToRoot = relative(distDir, filePath);
  if (relativeToRoot.startsWith(`..${sep}`) || relativeToRoot === "..") {
    sendText(response, 403, "Path is outside the Fleet application");
    return;
  }

  let fileStats;
  try {
    fileStats = await stat(filePath);
    if (fileStats.isDirectory()) {
      filePath = resolve(filePath, "index.html");
      fileStats = await stat(filePath);
    }
  } catch {
    if (request.headers.accept?.includes("text/html")) {
      filePath = resolve(distDir, "index.html");
      try {
        fileStats = await stat(filePath);
      } catch {
        sendText(response, 503, "Fleet frontend is not built");
        return;
      }
    } else {
      sendText(response, 404, "Not found");
      return;
    }
  }

  if (!fileStats.isFile()) {
    sendText(response, 404, "Not found");
    return;
  }

  response.writeHead(200, {
    "cache-control": filePath.endsWith("index.html")
      ? "no-cache"
      : "public, max-age=31536000, immutable",
    "content-length": fileStats.size,
    "content-type": contentType(filePath),
    "x-content-type-options": "nosniff",
  });

  if (request.method === "HEAD") {
    response.end();
    return;
  }

  const stream = createReadStream(filePath);
  stream.on("error", (error) => response.destroy(error));
  stream.pipe(response);
}

function rejectUpgrade(socket: Duplex, status: number, message: string): void {
  if (!socket.writable) {
    socket.destroy();
    return;
  }
  const body = `${message}\n`;
  socket.end(
    `HTTP/1.1 ${status} ${message}\r\n` +
      "Connection: close\r\n" +
      "Content-Type: text/plain; charset=utf-8\r\n" +
      `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`,
  );
}

function writeUpgradeResponse(
  socket: Duplex,
  response: IncomingMessage,
): void {
  socket.write(
    `HTTP/1.1 ${response.statusCode ?? 101} ${response.statusMessage ?? "Switching Protocols"}\r\n`,
  );
  for (let index = 0; index < response.rawHeaders.length; index += 2) {
    const name = response.rawHeaders[index];
    const value = response.rawHeaders[index + 1];
    if (name && value) {
      socket.write(`${name}: ${value}\r\n`);
    }
  }
  socket.write("\r\n");
}

function proxyWebSocket(
  request: IncomingMessage,
  clientSocket: Duplex,
  head: Buffer,
  target: UpstreamTarget,
  onProxyError: NonNullable<FleetServerOptions["onProxyError"]>,
): void {
  const proxyRequest = createUpstreamRequest({
    host: target.host,
    port: target.port,
    method: request.method,
    path: upstreamPath(request.url ?? "/", target),
    headers: cloneProxyHeaders(request.headers, request, target, true),
    agent: false,
  });

  proxyRequest.on("upgrade", (proxyResponse, upstreamSocket, upstreamHead) => {
    writeUpgradeResponse(clientSocket, proxyResponse);
    if (head.length > 0) {
      upstreamSocket.write(head);
    }
    if (upstreamHead.length > 0) {
      clientSocket.write(upstreamHead);
    }
    clientSocket.pipe(upstreamSocket).pipe(clientSocket);
    clientSocket.on("error", () => upstreamSocket.destroy());
    upstreamSocket.on("error", () => clientSocket.destroy());
  });

  proxyRequest.on("response", (proxyResponse) => {
    rejectUpgrade(
      clientSocket,
      proxyResponse.statusCode ?? 502,
      proxyResponse.statusMessage ?? "WebSocket upgrade rejected",
    );
    proxyResponse.resume();
  });

  proxyRequest.on("error", (error) => {
    onProxyError(error, target.id);
    rejectUpgrade(clientSocket, 502, "Hermes WebSocket is unavailable");
  });

  clientSocket.on("close", () => proxyRequest.destroy());
  proxyRequest.end();
}

export function createFleetServer(options: FleetServerOptions = {}): Server {
  const allowedHosts = parseAllowedHosts(options.allowedHosts);
  const upstreams = makeUpstreams(options.upstreamPorts);
  const distDir = resolve(
    options.distDir ??
      process.env.HERMES_FLEET_DIST ??
      fileURLToPath(new URL("../dist/", import.meta.url)),
  );
  const onProxyError =
    options.onProxyError ??
    ((error: Error, target: OrganisationId) => {
      console.error(`[hermes-fleet] ${target} proxy error: ${error.message}`);
    });

  const server = createServer((request, response) => {
    const authorization = authorizeRequest(request, allowedHosts);
    if (!authorization.allowed) {
      sendText(response, authorization.status, authorization.message);
      return;
    }

    const parsed = parseRequestTarget(request.url);
    if (!parsed) {
      sendText(response, 400, "Malformed request target");
      return;
    }
    if (parsed.pathname === "/healthz") {
      const body = JSON.stringify({ status: "ok", organisations: ORGANISATIONS.map(({ id }) => id) });
      response.writeHead(200, {
        "cache-control": "no-store",
        "content-length": Buffer.byteLength(body),
        "content-type": "application/json; charset=utf-8",
        "x-content-type-options": "nosniff",
      });
      response.end(body);
      return;
    }

    const target = targetForPath(parsed.pathname, upstreams);
    if (target) {
      proxyHttp(request, response, target, onProxyError);
      return;
    }

    const unprefixedAssetTarget = targetForUnprefixedAsset(
      request,
      parsed.pathname,
      upstreams,
    );
    if (unprefixedAssetTarget) {
      proxyHttp(
        request,
        response,
        unprefixedAssetTarget,
        onProxyError,
        `${parsed.pathname}${parsed.search}`,
      );
      return;
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      sendText(response, 405, "Method not allowed");
      return;
    }

    void serveStatic(request, response, distDir).catch((error: unknown) => {
      const failure = error instanceof Error ? error : new Error(String(error));
      if (!response.headersSent) {
        sendText(response, 500, "Fleet frontend failed to load");
      } else {
        response.destroy(failure);
      }
    });
  });

  server.on("upgrade", (request, socket, head) => {
    const authorization = authorizeRequest(request, allowedHosts);
    if (!authorization.allowed) {
      rejectUpgrade(socket, authorization.status, authorization.message);
      return;
    }

    const parsed = parseRequestTarget(request.url);
    if (!parsed) {
      rejectUpgrade(socket, 400, "Bad request");
      return;
    }
    const target = targetForPath(parsed.pathname, upstreams);
    if (!target) {
      rejectUpgrade(socket, 404, "WebSocket route not found");
      return;
    }

    proxyWebSocket(request, socket, head, target, onProxyError);
  });

  server.on("clientError", (_error, socket) => {
    rejectUpgrade(socket, 400, "Bad request");
  });
  server.headersTimeout = 15_000;
  server.keepAliveTimeout = 5_000;

  return server;
}

function configuredPort(value: string | undefined): number {
  const port = value ? Number(value) : DEFAULT_FLEET_PORT;
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error("HERMES_FLEET_PORT must be an integer between 1 and 65535");
  }
  return port;
}

export function isMainModule(
  entryPath: string | undefined,
  moduleUrl: string,
): boolean {
  if (!entryPath) {
    return false;
  }

  try {
    return realpathSync(entryPath) === realpathSync(fileURLToPath(moduleUrl));
  } catch {
    return false;
  }
}

if (isMainModule(process.argv[1], import.meta.url)) {
  const port = configuredPort(process.env.HERMES_FLEET_PORT);
  const server = createFleetServer();
  server.listen(port, FLEET_LISTEN_HOST, () => {
    console.info(`[hermes-fleet] listening on http://${FLEET_LISTEN_HOST}:${port}`);
  });
}
