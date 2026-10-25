/** Decode complete SSE frames, including JSON split across arbitrary network chunks. */
export async function readPlanningStream(
  body: ReadableStream<Uint8Array>,
  onData: (value: unknown) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  function consume() {
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame.split("\n").filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart()).join("\n");
      if (data) onData(JSON.parse(data));
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Our API emits LF; normalize CRLF without breaking a trailing partial CR.
      buffer = buffer.replace(/\r\n/g, "\n");
      consume();
    }
    buffer += decoder.decode();
    consume();
  } finally {
    reader.releaseLock();
  }
}
