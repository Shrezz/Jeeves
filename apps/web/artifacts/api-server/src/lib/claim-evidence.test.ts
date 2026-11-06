import assert from "node:assert/strict";
import { Readable, Writable } from "node:stream";
import test from "node:test";
import type { File } from "@google-cloud/storage";
import { copyVideoEvidence, readEvidence, validEvidenceName, validImageBytes, MAX_EVIDENCE_BYTES, MAX_VIDEO_BYTES } from "./claim-evidence";

function storedFile(bytes: Buffer, reportedSize = bytes.length): File {
  return {
    getMetadata: async () => [{ size: String(reportedSize) }],
    createReadStream: () => Readable.from([bytes]),
  } as unknown as File;
}
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aTXsAAAAASUVORK5CYII=", "base64");

test("evidence names must match the allowed type and reject path/control characters", () => {
  assert.equal(validEvidenceName("kitchen.png", "image/png"), true);
  assert.equal(validEvidenceName("invoice.PDF", "application/pdf"), true);
  assert.equal(validEvidenceName("photo.jpeg", "image/jpeg"), true);
  assert.equal(validEvidenceName("../invoice.pdf", "application/pdf"), false);
  assert.equal(validEvidenceName("invoice\n.pdf", "application/pdf"), false);
  assert.equal(validEvidenceName("invoice.pdf", "image/png"), false);
  assert.equal(validEvidenceName("ceiling.mp4", "video/mp4"), true);
  assert.equal(validEvidenceName("damage.webm", "video/webm"), true);
  assert.equal(validEvidenceName("kitchen.mov", "video/quicktime"), true);
  assert.equal(validEvidenceName("kitchen.mp4", "image/jpeg"), false);
  assert.equal(validEvidenceName("test.jpg", "text/html"), false);
});

test("valid PNG bytes are preserved as one bounded immutable snapshot", async () => {
  assert.deepEqual(await readEvidence(storedFile(png), png.length, "image/png"), png);
});

test("PDF evidence uses the same full snapshot validation as policy PDFs", async () => {
  const bytes = Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n");
  assert.deepEqual(await readEvidence(storedFile(bytes), bytes.length, "application/pdf"), bytes);
});

test("files disguised as images fail validation", async () => {
  const bytes = Buffer.from("<html>not an image</html>");
  await assert.rejects(readEvidence(storedFile(bytes), bytes.length, "image/png"));
  assert.equal(validImageBytes(png, "image/jpeg"), false);
});

test("truncated PNG or JPEG markers fail validation", () => {
  assert.equal(validImageBytes(png.subarray(0, -4), "image/png"), false);
  assert.equal(validImageBytes(Buffer.from([0xff, 0xd8, 0xff, 0]), "image/jpeg"), false);
});

test("metadata and actual bytes must both match the allocated size", async () => {
  await assert.rejects(readEvidence(storedFile(png), png.length + 1, "image/png"));
  await assert.rejects(readEvidence(storedFile(png, png.length - 1), png.length - 1, "image/png"));
});

test("oversized image metadata fails before attempting a read", async () => {
  await assert.rejects(readEvidence(storedFile(png, MAX_EVIDENCE_BYTES + 1), MAX_EVIDENCE_BYTES + 1, "image/png"));
});

function videoDestination(onWrite: (chunk: Buffer) => void): File {
  return { createWriteStream: () => new Writable({
    write(chunk, _encoding, callback) { onWrite(Buffer.from(chunk)); callback(); },
  }) } as unknown as File;
}

// Container-sniffing fixture, not a decodable/processed video: the application
// stores attachments without promising codec support or semantic analysis.
const mp4Header = Buffer.from("00000018667479706d703432000000006d70343269736f6d000000086d646174", "hex");

test("video copying validates a recognized container and preserves streamed bytes", async () => {
  const chunks: Buffer[] = [];
  await copyVideoEvidence(storedFile(mp4Header), videoDestination((b) => chunks.push(b)), mp4Header.length, "video/mp4");
  assert.deepEqual(Buffer.concat(chunks), mp4Header);
});

test("a PDF disguised as a video is rejected", async () => {
  const bytes = Buffer.from("%PDF-1.7\n%%EOF\n");
  await assert.rejects(copyVideoEvidence(storedFile(bytes), videoDestination(() => {}), bytes.length, "video/mp4"));
});

test("video container must match the declared media type", async () => {
  await assert.rejects(copyVideoEvidence(storedFile(mp4Header), videoDestination(() => {}), mp4Header.length, "video/webm"));
});

test("oversized videos are rejected before reading", async () => {
  await assert.rejects(copyVideoEvidence(storedFile(mp4Header, MAX_VIDEO_BYTES + 1), videoDestination(() => {}), MAX_VIDEO_BYTES + 1, "video/mp4"));
});

test("video stream growth after metadata check is rejected", async () => {
  await assert.rejects(copyVideoEvidence(storedFile(mp4Header, mp4Header.length - 1), videoDestination(() => {}), mp4Header.length - 1, "video/mp4"));
});
