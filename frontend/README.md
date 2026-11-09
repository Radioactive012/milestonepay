# MilestonePay web

React + TypeScript + Tailwind + AG Grid. Needs Node 18 or newer.

```bash
cd frontend
npm install
npm run dev:fixtures   # no backend needed: shows the demo contract
npm run dev            # talks to the API on http://localhost:8000
npm run build          # type-checks and builds
```

The dev server proxies `/api` to port 8000, so start the backend first
(`uvicorn app.main:app --reload` in `backend/`).
