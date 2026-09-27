This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Release

### Environment

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes in production | Base URL of the backend API (HTTP/HTTPS). Malformed, non-HTTP(S), or localhost values fail fast with a clear error in production. Localhost fallback (`http://127.0.0.1:8000/api/v1`) is development-only. |

Never put secrets in `NEXT_PUBLIC_*` variables — they are inlined into the browser bundle. Server credentials live in deployment-owned configuration only.

### Verify (gates run in CI before deploy)

```bash
npm ci --frozen-lockfile
npx tsc --noEmit
npm run test -- --poolOptions.threads.maxThreads=1
npm run lint
npx next build --webpack
```

### Build and start (canonical production commands)

```bash
npm run build
npm run start
```

Smoke-check `/`, `/docs`, `/auth/login` after start, then stop the process.

### Deployment ownership

- Frontend: UI, `next start`, client env above, production console stripping.
- Backend: APIs, authorization, durable logs, health/readiness endpoints.
- Deployment platform: TLS, security headers, probes, secrets, scaling, rollout/rollback execution (see `docs/PRODUCTION_CHECKLIST.md`).

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
