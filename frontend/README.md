# Frontend

Vite + React + TypeScript scaffold. It establishes the frontend/backend
separation and does nothing else.

**The MDR UI is not implemented.** There is one page, and it checks that the
API is reachable. There is no dashboard and no processing screen — building
them before the backend phases that would fill them exist would mean shipping
a UI for capabilities that do not exist.

---

## The one rule

**The frontend implements no MDR business logic.**

No revision comparison, no identity normalisation, no status-code
interpretation, no latest determination. If a screen needs one of those, the
backend computes it and the frontend renders the answer.

Every network call goes through `src/services/apiClient.ts`. Nothing else calls
`fetch` directly.

---

## Layout

```
src/
├── app/          root, entry point, global styles
├── pages/        one page per route
├── components/   shared presentational components   (empty)
├── features/     feature-scoped UI                  (empty — Phase 7)
├── services/     API clients — the only network layer
├── types/        response shapes mirroring the backend's models
└── utils/        formatting helpers                 (empty)
```

## Commands

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck (tsc --noEmit) then bundle to dist/
npm run typecheck
```

`npm run dev` proxies `/api` to `http://127.0.0.1:8000`, so the frontend never
hard-codes the backend's origin. Start the backend separately:

```bash
cd ../backend && uvicorn app.main:app --reload
```

## Notes

- TypeScript runs in `strict` mode, with `noUncheckedIndexedAccess`.
- Response types in `src/types/api.ts` mirror the backend's Pydantic models.
  When the backend adds a field, add it there — do not compute it on the client.
