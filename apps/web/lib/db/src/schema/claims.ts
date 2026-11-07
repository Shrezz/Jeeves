import { check, foreignKey, index, jsonb, numeric, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { policiesTable } from "./policies";
import { usersTable } from "./users";
import { sql } from "drizzle-orm";
import { CLAIM_STATUS_VALUES, INSURER_OUTCOME_VALUES, REPAIR_STATUS_VALUES } from "@workspace/domain";

export const claimsTable = pgTable("claims", {
  id: uuid("id").primaryKey(),
  ownerId: text("owner_id").notNull().references(() => usersTable.id),
  policyId: uuid("policy_id").references(() => policiesTable.id),
  title: text("title").notNull(),
  status: text("status", { enum: CLAIM_STATUS_VALUES }).notNull().default("draft"),
  incidentJson: jsonb("incident_json").$type<Record<string, unknown>>().notNull().default({}),
  insurerOutcome: text("insurer_outcome", { enum: INSURER_OUTCOME_VALUES }).notNull().default("unknown"),
  insurerOutcomeSource: text("insurer_outcome_source", { enum: ["user_reported"] }),
  totalExpenses: numeric("total_expenses", { precision: 16, scale: 2 }).notNull().default("0"),
  latestUpdate: text("latest_update"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  check("claims_status_check", sql`${t.status} in (${sql.join(CLAIM_STATUS_VALUES.map(value => sql`${value}`), sql`, `)})`),
  check("claims_repair_status_check", sql`${t.incidentJson}->>'repair_status' is null or ${t.incidentJson}->>'repair_status' in (${sql.join(REPAIR_STATUS_VALUES.map(value => sql`${value}`), sql`, `)})`),
  check("claims_incident_object_check", sql`jsonb_typeof(${t.incidentJson}) = 'object'`),
  check("claims_insurer_outcome_check", sql`${t.insurerOutcome} in (${sql.join(INSURER_OUTCOME_VALUES.map(value => sql`${value}`), sql`, `)})`),
  check("claims_insurer_source_check", sql`(${t.insurerOutcomeSource} is null or ${t.insurerOutcomeSource} = 'user_reported') and (${t.insurerOutcome} = 'unknown' or ${t.insurerOutcomeSource} is not null)`),
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
