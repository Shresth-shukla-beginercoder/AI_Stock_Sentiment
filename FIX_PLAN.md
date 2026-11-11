# Fix Plan: Hygiene and README Alignment

## Status
- All phases COMPLETE up to Phase 13.
- Current state: Ready for production but needs README and config hygiene check.

## Plan
1. Hygiene:
   - Check `backend/app/collectors/apify.py` for leftover candidate actors/unused code.
   - Align `README.md` and `docs/` with the now-complete status of the project (remove "planned" / "todo" mentions).
   - Ensure `docker-compose.yml` and `docker-compose.prod.yml` match project design.
2. Verification:
   - Run existing tests to ensure no regressions.
   - Re-check API endpoints for correct responses.
3. Finalize:
   - Final report generation.
