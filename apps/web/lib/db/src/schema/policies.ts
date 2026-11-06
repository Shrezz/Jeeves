import { index, integer, numeric, pgTable, text, timestamp, unique, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const policiesTable = pgTable("policies", {
  id: uuid("id").primaryKey().defaultRandom(),
  ownerId: text("owner_id").notNull(),
  fileName: text("file_name").notNull(),
  size: integer("size").notNull(),
  objectPath: text("object_path").notNull(),
  label: text("label").notNull(),
  deductible: numeric("deductible", { precision: 12, scale: 2 }),
  status: text("status", { enum: ["pending", "saved"] }).notNull().default("pending"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (table) => [
  index("policies_owner_status_idx").on(table.ownerId, table.status),
  unique("policies_id_owner_unique").on(table.id, table.ownerId),
]);

export const insertPolicySchema = createInsertSchema(policiesTable).omit({ id: true, createdAt: true });
export type InsertPolicy = z.infer<typeof insertPolicySchema>;
export type StoredPolicy = typeof policiesTable.$inferSelect;
