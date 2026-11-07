import { getAuth } from "@clerk/express";
import type { RequestHandler } from "express";
import { clerkUserId } from "@workspace/domain";
import { db, usersTable } from "@workspace/db";

/** Reject API requests without a valid Clerk session, without HTML redirects. */
export const requireAuth: RequestHandler = async (req, res, next) => {
  const subject = getAuth(req).userId;
  if (!subject) {
    res.status(401).json({ error: "Sign in to access your workspace." });
    return;
  }
  // getAuth reads the verified Clerk session. Never upsert an ID from the request body.
  const ownerId = clerkUserId(subject);
  await db.insert(usersTable).values({ id: ownerId }).onConflictDoNothing();
  res.setHeader("Cache-Control", "no-store");
  next();
};
