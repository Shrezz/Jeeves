import { foreignKey, index, integer, jsonb, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { claimsTable } from "./claims";
import { claimMessagesTable } from "./claim-messages";

export const claimGuidanceTable = pgTable("claim_guidance", {
  id: uuid("id").primaryKey().defaultRandom(),
  claimId: uuid("claim_id").notNull().references(() => claimsTable.id, { onDelete: "cascade" }),
  messageId: uuid("message_id").notNull().unique().references(() => claimMessagesTable.id, { onDelete: "cascade" }),
  content: text("content"),
  workflow: jsonb("workflow").$type<Record<string, unknown>>(),
  sources: jsonb("sources").$type<{chunkId: string; page: number; section: string; excerpt: string}[]>().notNull().default([]),
  state: text("state", { enum: ["pending", "ready", "error"] }).notNull().default("pending"),
  leaseId: uuid("lease_id").notNull(),
  attempts: integer("attempts").notNull().default(1),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("claim_guidance_claim_idx").on(t.claimId),
  foreignKey({
    name: "guidance_message_same_claim_fk",
    columns: [t.claimId, t.messageId],
    foreignColumns: [claimMessagesTable.claimId, claimMessagesTable.id],
  }).onDelete("cascade"),
]);

export const insertClaimGuidanceSchema = createInsertSchema(claimGuidanceTable).omit({ id: true, createdAt: true, updatedAt: true });
export type InsertClaimGuidance = z.infer<typeof insertClaimGuidanceSchema>;
export type StoredClaimGuidance = typeof claimGuidanceTable.$inferSelect;
