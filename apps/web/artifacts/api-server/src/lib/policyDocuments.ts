import type { File } from "@google-cloud/storage";

export const MAX_POLICY_BYTES = 20 * 1024 * 1024;

export class InvalidPolicyDocument extends Error {}

// Read a bounded snapshot: validation and saving must use the same bytes, since
// a staging PUT URL remains valid until expiry and could otherwise be reused.
export async function readPolicyPdf(file: File, expectedSize: number): Promise<Buffer> {
  const [metadata] = await file.getMetadata();
  if (Number(metadata.size) !== expectedSize || expectedSize > MAX_POLICY_BYTES) {
    throw new InvalidPolicyDocument("The uploaded file size does not match. Choose the PDF again.");
  }
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of file.createReadStream({ start: 0, end: MAX_POLICY_BYTES })) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_POLICY_BYTES) {
      throw new InvalidPolicyDocument("Choose a PDF smaller than 20 MB.");
    }
    chunks.push(bytes);
  }
  const buffer = Buffer.concat(chunks);
  if (buffer.length !== expectedSize ||
      !/^%PDF-(1\.[0-7]|2\.0)/.test(buffer.subarray(0, 10).toString("ascii")) ||
      !buffer.subarray(-2048).includes(Buffer.from("%%EOF"))) {
    throw new InvalidPolicyDocument("This file is not a complete PDF. Please choose a valid PDF document.");
  }
  return buffer;
}
