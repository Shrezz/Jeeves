import { foreignKey, index, numeric, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { policiesTable } from "./policies";

export const claimsTable = pgTable("claims", {
  id: uuid("id").primaryKey(),
  ownerId: text("owner_id").notNull(),
  policyId: uuid("policy_id").references(() => policiesTable.id),
  title: text("title").notNull(),
  status: text("status", { enum: ["Draft", "Gathering evidence", "Preparation requested", "Package prepared", "Submitted in Claimwise", "Filed by me with insurer", "Insurer decision received", "Resolved without filing"] }).notNull().default("Draft"),
  totalExpenses: numeric("total_expenses", { precision: 16, scale: 2 }).notNull().default("0"),
  latestUpdate: text("latest_update"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("claims_owner_updated_idx").on(t.ownerId, t.updatedAt),
  foreignKey({
    name: "claims_owned_policy_fk",
    columns: [t.policyId, t.ownerId],
    foreignColumns: [policiesTable.id, policiesTable.ownerId],
  }),
]);

export const insertClaimSchema = createInsertSchema(claimsTable).omit({ createdAt: true, updatedAt: true });
export type InsertClaim = z.infer<typeof insertClaimSchema>;
export type StoredClaim = typeof claimsTable.$inferSelect;
