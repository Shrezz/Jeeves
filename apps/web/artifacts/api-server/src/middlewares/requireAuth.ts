import { getAuth } from "@clerk/express";
import type { RequestHandler } from "express";

/** Reject API requests without a valid Clerk session, without HTML redirects. */
export const requireAuth: RequestHandler = (req, res, next) => {
  if (!getAuth(req).userId) {
    res.status(401).json({ error: "Sign in to access your workspace." });
    return;
  }
  res.setHeader("Cache-Control", "no-store");
  next();
};
