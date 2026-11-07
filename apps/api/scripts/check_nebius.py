"""Check the configured Nebius roles using synthetic inputs only. Run as a module."""

import argparse
import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.agents.prompts import ROUTER
from app.agents.reviews.packet import FACT_CHECK
from app.schemas.agents import IncidentFactReview, RouteDecision
from app.services.nebius import NEBIUS_BASE_URL, ModelUnavailable, nebius_pair


async def check(list_only: bool) -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / "web/.env.local", interpolate=False)
    key = (os.getenv("NEBIUS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("Set NEBIUS_API_KEY in apps/web/.env.local first.")
    async with httpx.AsyncClient(
        base_url=NEBIUS_BASE_URL, headers={"Authorization": "Bearer " + key}, timeout=20
    ) as client:
        response = await client.get("models")
        if not response.is_success:
            raise SystemExit(f"Nebius model catalog returned HTTP {response.status_code}.")
        available = {row["id"] for row in response.json()["data"]}
        if list_only:
            print("\n".join(sorted(available)))
            return
        gen, rev = nebius_pair(
            client, os.getenv("NEBIUS_GENERATOR_MODEL", ""), os.getenv("NEBIUS_REVIEWER_MODEL", "")
        )
        for model in (gen, rev):
            if model.model not in available:
                raise SystemExit(
                    f"{model.role} model is not in this project's catalog: {model.model}"
                )
        route = await gen.generate(
            prompt=ROUTER,
            payload={"message": "Is my broken window covered?"},
            output_type=RouteDecision,
        )
        if route.route != "answer_claim":
            raise SystemExit(
                f"Generator {gen.model} did not route the synthetic coverage question correctly."
            )
        print(f"Generator OK: {gen.model}")
        result = await rev.generate(
            prompt=FACT_CHECK,
            payload={
                "homeowner_reports": ["A branch broke my window. I do not know what made it fall."],
                "confirmed_incident": {},
                "proposed_facts": {},
                "proposed_narrative": "Lightning struck the tree and caused the branch to fall.",
            },
            output_type=IncidentFactReview,
        )
        if not any(issue.field == "narrative" for issue in result.unsupported):
            raise SystemExit(
                f"Reviewer {rev.model} missed the invented cause in the synthetic narrative."
            )
        print(f"Reviewer OK: {rev.model} caught the invented cause.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="Only list model IDs; no inference calls."
    )
    try:
        asyncio.run(check(parser.parse_args().list))
    except (ModelUnavailable, ValueError) as error:
        raise SystemExit(str(error)) from None
    except httpx.RequestError:
        raise SystemExit("Could not reach Nebius; check connectivity and retry.") from None
