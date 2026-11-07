import { integer, jsonb, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { claimsTable } from "./claims";

export const claimReviewsTable = pgTable("claim_reviews", {
  claimId: uuid("claim_id").primaryKey().references(() => claimsTable.id, { onDelete: "cascade" }),
  comments: text("comments").notNull().default(""),
  version: integer("version").notNull().default(0),
  submittedAt: timestamp("submitted_at", { withTimezone: true }),
  snapshot: jsonb("snapshot").$type<Record<string, unknown>>(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertClaimReviewSchema = createInsertSchema(claimReviewsTable).omit({ updatedAt: true });
export type InsertClaimReview = z.infer<typeof insertClaimReviewSchema>;
export type StoredClaimReview = typeof claimReviewsTable.$inferSelect;
