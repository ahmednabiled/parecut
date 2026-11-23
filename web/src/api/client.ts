export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string" && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let payload: unknown = null;
    try {
      const body: unknown = await response.json();
      payload = body;
      if (body !== null && typeof body === "object" && "detail" in body) {
        const value = (body as { detail?: unknown }).detail;
        if (typeof value === "string" && value.trim()) {
          detail = value;
        } else if (Array.isArray(value)) {
          const messages = value
            .map((item) => {
              if (
                item !== null &&
                typeof item === "object" &&
                "msg" in item &&
                typeof (item as { msg?: unknown }).msg === "string"
              ) {
                return (item as { msg: string }).msg.replace(/^Value error,\s*/i, "");
              }
              return null;
            })
            .filter((msg): msg is string => Boolean(msg));
          if (messages.length > 0) {
            detail = messages.join(". ");
          }
        }
      }
    } catch {
      // keep the generic message
    }
    throw new ApiError(response.status, detail, payload);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
