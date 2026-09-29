import { PublishPayload } from "./payloadBuilder";

export interface PublishResult {
  ok: boolean;
  status: number;
  body: string;
  json?: unknown;
}

export async function publishToCentralCatalog(options: {
  targetUrl: string;
  payload: PublishPayload;
  webId?: string;
  token?: string;
  authFetch?: typeof fetch;
}): Promise<PublishResult> {
  const headers: Record<string, string> = {
    "Content-Type": options.payload.contentType
  };
  if (options.webId) {
    headers["X-Participant-WebID"] = options.webId;
    headers["X-Participant-Id"] = options.webId;
  }
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  const requestFetch = options.authFetch || fetch;
  const response = await requestFetch(options.targetUrl, {
    method: "POST",
    headers,
    body: options.payload.body
  });
  const body = await response.text();
  let json: unknown;
  try {
    json = body ? JSON.parse(body) : undefined;
  } catch {
    json = undefined;
  }
  return { ok: response.ok, status: response.status, body, json };
}
