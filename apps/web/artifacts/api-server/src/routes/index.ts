import { Router, type IRouter } from "express";
import healthRouter from "./health";
import { requireAuth } from "../middlewares/requireAuth";
import policiesRouter from "./policies";
import claimsRouter from "./claims";

const router: IRouter = Router();

router.use(healthRouter);

// Health is public. Mount all application data routers below this guard.
// Future data handlers must also scope each query to getAuth(req).userId.
router.use(requireAuth);
router.use(policiesRouter);
router.use(claimsRouter);

export default router;
