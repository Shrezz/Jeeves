import type { StoredPolicy } from "@workspace/db";

export function serializePolicy(policy: StoredPolicy) {
  return {
    id: policy.id, label: policy.label, fileName: policy.fileName, size: policy.size,
    deductible: policy.deductible === null ? null : Number(policy.deductible),
    status: "saved" as const, createdAt: policy.createdAt.toISOString(),
    ...(policy.objectPath.startsWith("local-db:") ? { ingestionStatus: policy.ingestionStatus, indexedChunks: policy.indexedChunks } : {}),
    documentUrl: `/api/policies/${policy.id}/document`,
  };
}
