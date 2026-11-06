import assert from "node:assert/strict";
import { Readable } from "node:stream";
import test from "node:test";
import type { File } from "@google-cloud/storage";
import { InvalidPolicyDocument, MAX_POLICY_BYTES, readPolicyPdf } from "./policyDocuments";

function storedFile(bytes: Buffer, reportedSize = bytes.length): File {
  return {
    getMetadata: async () => [{ size: String(reportedSize) }],
    createReadStream: () => Readable.from([bytes]),
  } as unknown as File;
}

const pdf = Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n");

test("accepts a PDF snapshot and preserves its exact bytes", async () => {
  assert.deepEqual(await readPolicyPdf(storedFile(pdf), pdf.length), pdf);
});

test("rejects a non-PDF disguised by its extension", async () => {
  const bytes = Buffer.from("not a PDF at all");
  await assert.rejects(readPolicyPdf(storedFile(bytes), bytes.length), InvalidPolicyDocument);
});

test("rejects truncated PDFs", async () => {
  const bytes = Buffer.from("%PDF-1.7\n1 0 obj");
  await assert.rejects(readPolicyPdf(storedFile(bytes), bytes.length), InvalidPolicyDocument);
});

test("rejects mismatched upload sizes", async () => {
  await assert.rejects(readPolicyPdf(storedFile(pdf), pdf.length + 1), InvalidPolicyDocument);
});

test("rejects metadata over the size limit before reading", async () => {
  await assert.rejects(readPolicyPdf(storedFile(pdf, MAX_POLICY_BYTES + 1), MAX_POLICY_BYTES + 1), InvalidPolicyDocument);
});

test("rejects a changed stream even if metadata claimed a valid size", async () => {
  const bytes = Buffer.concat([pdf, Buffer.from("extra")]);
  await assert.rejects(readPolicyPdf(storedFile(bytes, pdf.length), pdf.length), InvalidPolicyDocument);
});
