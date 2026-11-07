import type { File } from "@google-cloud/storage";
import { pipeline } from "node:stream/promises";
import { fileTypeFromBuffer } from "file-type";
import { InvalidPolicyDocument, readPolicyPdf } from "./policyDocuments";
import { ClaimRequestError } from "./claim-errors";

export const MAX_EVIDENCE_BYTES = 20 * 1024 * 1024;
export const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
export const EVIDENCE_UPLOAD_LIFETIME = 15 * 60 * 1000;

export function validEvidenceName(name: string, contentType: string) {
  const extensions: Record<string, RegExp> = {
    "application/pdf": /\.pdf$/i, "image/png": /\.png$/i, "image/jpeg": /\.jpe?g$/i,
    "video/mp4": /\.mp4$/i, "video/webm": /\.webm$/i, "video/quicktime": /\.mov$/i,
  };
  return !!name.trim() && !/[\x00-\x1f\x7f/\\]/.test(name) && !!extensions[contentType]?.test(name.trim());
}

// Video bytes are streamed to a new, non-signed private object. The validating
// stream is the saved snapshot, without buffering 100 MB per request in memory.
export async function copyVideoEvidence(source: File, destination: File, expectedSize: number, contentType: string) {
  const [metadata] = await source.getMetadata();
  if (Number(metadata.size) !== expectedSize || expectedSize > MAX_VIDEO_BYTES || expectedSize < 1) {
    throw new ClaimRequestError(400, "Choose a video up to 100 MB whose size matches the upload.");
  }
  async function* validatedBytes(input: AsyncIterable<Buffer>) {
    let size = 0;
    let headSize = 0;
    const head: Buffer[] = [];
    for await (const chunk of input) {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      size += bytes.length;
      if (size > expectedSize) throw new ClaimRequestError(400, "The video size changed during upload. Choose it again.");
      if (headSize < 65536) {
        const part = bytes.subarray(0, 65536 - headSize);
        head.push(part);
        headSize += part.length;
      }
      yield bytes;
    }
    let detected;
    try { detected = await fileTypeFromBuffer(Buffer.concat(head)); }
    catch { throw new ClaimRequestError(400, "This video could not be recognized. Choose a valid MP4, WebM, or MOV."); }
    if (size !== expectedSize || detected?.mime !== contentType) {
      throw new ClaimRequestError(400, "The video format does not match. Choose a valid MP4, WebM, or MOV.");
    }
  }
  await pipeline(
    source.createReadStream({ start: 0, end: expectedSize }),
    validatedBytes,
    destination.createWriteStream({
      resumable: false, validation: "crc32c",
      metadata: { contentType, cacheControl: "private, no-store" },
    }),
  );
}

export function validImageBytes(bytes: Buffer, contentType: string) {
  if (contentType === "image/png") {
    return bytes.length >= 45 && bytes.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex")) &&
      bytes.subarray(12, 16).toString("ascii") === "IHDR" &&
      bytes.subarray(-12, -4).equals(Buffer.from("0000000049454e44", "hex"));
  }
  return contentType === "image/jpeg" && bytes.length >= 4 &&
    bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff &&
    bytes[bytes.length - 2] === 0xff && bytes[bytes.length - 1] === 0xd9;
}

export async function readEvidence(file: File, expectedSize: number, contentType: string): Promise<Buffer> {
  if (contentType === "application/pdf") {
    try { return await readPolicyPdf(file, expectedSize); }
    catch (error) {
      if (error instanceof InvalidPolicyDocument) throw new ClaimRequestError(400, error.message);
      throw error;
    }
  }
  const [metadata] = await file.getMetadata();
  if (Number(metadata.size) !== expectedSize || expectedSize > MAX_EVIDENCE_BYTES || expectedSize < 1) {
    throw new ClaimRequestError(400, "The uploaded file size does not match. Choose the file again.");
  }
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of file.createReadStream({ start: 0, end: MAX_EVIDENCE_BYTES })) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_EVIDENCE_BYTES) throw new ClaimRequestError(400, "Choose evidence smaller than 20 MB.");
    chunks.push(bytes);
  }
  const bytes = Buffer.concat(chunks);
  if (bytes.length !== expectedSize || !validImageBytes(bytes, contentType)) {
    throw new ClaimRequestError(400, "This is not a complete file of the selected type. Choose a valid PDF, PNG, or JPEG.");
  }
  return bytes;
}
