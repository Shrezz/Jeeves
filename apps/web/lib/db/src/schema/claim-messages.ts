import { index, numeric, pgTable, text, timestamp, unique, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { claimsTable } from "./claims";

export const claimMessagesTable = pgTable("claim_messages", {
  id: uuid("id").primaryKey(),
  claimId: uuid("claim_id").notNull().references(() => claimsTable.id, { onDelete: "cascade" }),
  content: text("content").notNull(),
  kind: text("kind", { enum: ["ask", "preparation_request", "status_update"] }).notNull(),
  expense: numeric("expense", { precision: 12, scale: 2 }),
  status: text("status"),
  processingStatus: text("processing_status", { enum: ["saved_for_processing", "recorded"] }).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("claim_messages_claim_created_idx").on(t.claimId, t.createdAt),
  unique("claim_messages_claim_id_unique").on(t.claimId, t.id),
]);

export const insertClaimMessageSchema = createInsertSchema(claimMessagesTable).omit({ createdAt: true });
export type InsertClaimMessage = z.infer<typeof insertClaimMessageSchema>;
export type StoredClaimMessage = typeof claimMessagesTable.$inferSelect;
