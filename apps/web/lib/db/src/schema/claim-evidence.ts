import { foreignKey, index, integer, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { claimsTable } from "./claims";
import { claimMessagesTable } from "./claim-messages";

export const claimEvidenceTable = pgTable("claim_evidence", {
  id: uuid("id").primaryKey().defaultRandom(),
  claimId: uuid("claim_id").notNull().references(() => claimsTable.id, { onDelete: "cascade" }),
  messageId: uuid("message_id").references(() => claimMessagesTable.id),
  fileName: text("file_name").notNull(),
  contentType: text("content_type").notNull(),
  size: integer("size").notNull(),
  objectPath: text("object_path").notNull(),
  status: text("status", { enum: ["pending", "saved"] }).notNull().default("pending"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("claim_evidence_claim_status_idx").on(t.claimId, t.status),
  foreignKey({
    name: "evidence_message_same_claim_fk",
    columns: [t.claimId, t.messageId],
    foreignColumns: [claimMessagesTable.claimId, claimMessagesTable.id],
  }),
]);

export const insertClaimEvidenceSchema = createInsertSchema(claimEvidenceTable).omit({ id: true, createdAt: true });
export type InsertClaimEvidence = z.infer<typeof insertClaimEvidenceSchema>;
export type StoredClaimEvidence = typeof claimEvidenceTable.$inferSelect;
