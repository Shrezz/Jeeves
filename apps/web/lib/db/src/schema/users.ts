import { check, pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

/** Clerk owns credentials; this table mirrors authenticated subjects only. */
export const usersTable = pgTable("users", {
  id: text("id").primaryKey(),
  name: text("name"),
  email: text("email"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (table) => [
  check("users_clerk_subject_check", sql`${table.id} ~ '^user_[A-Za-z0-9_]+$'`),
]);
