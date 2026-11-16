import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import NewJob from "./NewJob";

vi.mock("../lib/audio", () => ({
  MAX_UPLOAD_BYTES: 2 * 1024 * 1024 * 1024,
  UPLOAD_ACCEPT: ".wav,.mp4",
  readAudioDuration: async () => 120,
  validateUploadFile: () => null,
}));

class FakeXhr {
  upload = {
    onprogress: null as ((event: ProgressEvent) => void) | null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 204;
  responseText = "";
  withCredentials = false;

  open() {}
  setRequestHeader() {}
  abort() {
    this.onabort?.();
  }
  send() {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded: 100,
      total: 100,
    } as unknown as ProgressEvent);
    this.onload?.();
  }
}

class DeferredXhr extends FakeXhr {
  static last: DeferredXhr | null = null;

  constructor() {
    super();
    DeferredXhr.last = this;
  }

  send() {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded: 100,
      total: 100,
    } as unknown as ProgressEvent);
  }

  finish() {
    this.onload?.();
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NewJob />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  DeferredXhr.last = null;
  vi.unstubAllGlobals();
});

describe("NewJob", () => {
  it("creates a draft project and opens the editor", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr as unknown as typeof XMLHttpRequest);
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, _init?: RequestInit) => {
        const url = String(input);
      if (url === "/api/profile") {
        return json({
          user: {
            id: "u1",
            email: "a@example.com",
            full_name: "A",
            avatar_url: null,
            created_at: "2026-01-01T00:00:00Z",
          },
          profile: {
            credit_balance_minutes: 12,
            default_fps: "25",
            default_enhance_mix: 80,
            default_silence_pad_ms: 150,
          },
          jobs: [],
          ledger: [],
        });
      }
      if (url === "/api/uploads") {
        return json(
          {
            upload_url: "/api/uploads/token",
            upload_key: "uploads/take.wav",
            expires_at: "2026-01-01T00:15:00Z",
          },
          201,
        );
      }
      if (url === "/api/jobs") {
        return json({ id: "j1" }, 201);
      }
      throw new Error(`unexpected request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await userEvent.upload(
      screen.getByLabelText(/source media file/i),
      new File(["audio"], "take.wav", { type: "audio/wav" }),
    );

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /open editor/i })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: /open editor/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url) === "/api/jobs"),
      ).toBe(true);
    });

    const call = fetchMock.mock.calls.find(
      ([url]) => String(url) === "/api/jobs",
    );
    const init = call?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toMatchObject({
      upload_key: "uploads/take.wav",
      source_filename: "take.wav",
      fps: "25",
      draft: true,
    });
  });

  it("shows a credit error if the draft is rejected", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr as unknown as typeof XMLHttpRequest);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/profile") {
          return json({
            user: {
              id: "u1",
              email: "a@example.com",
              full_name: "A",
              avatar_url: null,
              created_at: "2026-01-01T00:00:00Z",
            },
            profile: {
              credit_balance_minutes: 0,
              default_fps: "25",
              default_enhance_mix: 80,
              default_silence_pad_ms: 150,
            },
            jobs: [],
            ledger: [],
          });
        }
        if (url === "/api/uploads") {
          return json(
            {
              upload_url: "/api/uploads/token",
              upload_key: "uploads/take.wav",
              expires_at: "2026-01-01T00:15:00Z",
            },
            201,
          );
        }
        if (url === "/api/jobs") {
          return json({ detail: "Insufficient credits" }, 402);
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    await userEvent.upload(
      screen.getByLabelText(/source media file/i),
      new File(["audio"], "take.wav", { type: "audio/wav" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /open editor/i })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: /open editor/i }));

    expect(
      await screen.findByText(/insufficient credits for this upload/i),
    ).toBeInTheDocument();
  });

  it("keeps the editor locked until the server finishes storing the file", async () => {
    vi.stubGlobal(
      "XMLHttpRequest",
      DeferredXhr as unknown as typeof XMLHttpRequest,
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/profile") {
          return json({
            user: {
              id: "u1",
              email: "a@example.com",
              full_name: "A",
              avatar_url: null,
              created_at: "2026-01-01T00:00:00Z",
            },
            profile: {
              credit_balance_minutes: 12,
              default_fps: "25",
              default_enhance_mix: 80,
              default_silence_pad_ms: 150,
            },
            jobs: [],
            ledger: [],
          });
        }
        if (url === "/api/uploads") {
          return json(
            {
              upload_url: "/api/uploads/token",
              upload_key: "uploads/take.wav",
              expires_at: "2026-01-01T00:15:00Z",
            },
            201,
          );
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    await userEvent.upload(
      screen.getByLabelText(/source media file/i),
      new File(["audio"], "take.wav", { type: "audio/wav" }),
    );

    expect(
      await screen.findByText(/large files can take a few minutes/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /saving to storage/i }),
    ).toBeDisabled();

    DeferredXhr.last?.finish();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /open editor/i })).toBeEnabled(),
    );
    expect(screen.getByText("Uploaded")).toBeInTheDocument();
  });
});
