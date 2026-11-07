import { index, integer, jsonb, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { jeevConversationsTable } from "./jeev-conversations";
import { policiesTable } from "./policies";

export const jeevMessagesTable = pgTable("jeev_messages", {
  id: uuid("id").primaryKey(),
  conversationId: uuid("conversation_id").notNull().references(() => jeevConversationsTable.id, { onDelete: "cascade" }),
  content: text("content").notNull(),
  policyId: uuid("policy_id").references(() => policiesTable.id),
  route: text("route", { enum: ["answer_claim", "file_claim", "save_claim_status", "clarify"] }),
  sources: jsonb("sources").$type<{chunkId: string; page: number; section: string; excerpt: string}[]>().notNull().default([]),
  reply: text("reply"),
  replyState: text("reply_state", { enum: ["pending", "ready", "error"] }).notNull().default("pending"),
  leaseId: uuid("lease_id").notNull(),
  attempts: integer("attempts").notNull().default(1),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("jeev_messages_conversation_idx").on(t.conversationId)]);

export const insertJeevMessageSchema = createInsertSchema(jeevMessagesTable).omit({ createdAt: true, updatedAt: true });
export type InsertJeevMessage = z.infer<typeof insertJeevMessageSchema>;
export type StoredJeevMessage = typeof jeevMessagesTable.$inferSelect;
