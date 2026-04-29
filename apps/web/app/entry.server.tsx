import { PassThrough } from "node:stream";

import type { EntryContext } from "@remix-run/node";
import { createReadableStreamFromReadable } from "@remix-run/node";
import { RemixServer } from "@remix-run/react";
import { renderToPipeableStream } from "react-dom/server";

import { logSsrEvent, requestIdFromHeaders } from "@/lib/logging";

const ABORT_DELAY = 5_000;

export default function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  remixContext: EntryContext,
): Promise<Response> {
  return new Promise((resolve, reject) => {
    const requestId = requestIdFromHeaders(request.headers);
    const pathname = new URL(request.url).pathname;
    let shellRendered = false;
    const body = new PassThrough();
    const stream = createReadableStreamFromReadable(body);

    const { abort, pipe } = renderToPipeableStream(
      <RemixServer context={remixContext} url={request.url} />,
      {
        onAllReady() {
          shellRendered = true;
          responseHeaders.set("Content-Type", "text/html");
          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode,
            }),
          );
          pipe(body);
        },
        onError(error: unknown) {
          responseStatusCode = 500;
          if (shellRendered) {
            logSsrEvent("error", "render.error", {
              error: error instanceof Error ? error.message : String(error),
              path: pathname,
              request_id: requestId,
              status: responseStatusCode,
            });
            return;
          }
          reject(error);
        },
      },
    );

    setTimeout(abort, ABORT_DELAY);
  });
}
