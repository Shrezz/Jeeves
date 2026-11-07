import { index, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const jeevConversationsTable = pgTable("jeev_conversations", {
  id: uuid("id").primaryKey(),
  ownerId: text("owner_id").notNull(),
  title: text("title").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("jeev_conversations_owner_idx").on(t.ownerId)]);

export const insertJeevConversationSchema = createInsertSchema(jeevConversationsTable).omit({ createdAt: true, updatedAt: true });
export type InsertJeevConversation = z.infer<typeof insertJeevConversationSchema>;
export type StoredJeevConversation = typeof jeevConversationsTable.$inferSelect;
