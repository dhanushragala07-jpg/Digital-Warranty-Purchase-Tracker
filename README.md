# Digital Warranty & Purchase Tracker

A web platform for organizing purchases, keeping invoice evidence together, tracking warranty coverage, and managing warranty claims.

## Repository contents

- `index.html`, `styles.css`, `app.js`: responsive customer/admin-preview frontend.
- `backend/`: initial FastAPI API, MySQL Docker Compose setup, account registration/login, purchase records, private invoice upload, claim endpoints, admin review routes, and setup notes.
- `.github/workflows/pages.yml`: static frontend deployment plus JavaScript/Python syntax checks.

## Live frontend

GitHub Pages URL: https://dhanushragala07-jpg.github.io/Digital-Warranty-Purchase-Tracker/

The current website is still a demo and uses in-memory sample data. It is **not yet connected** to the API. Customer accounts, real persistent frontend records, invoice OCR, and admin review are not yet available through the live UI.

## Backend status

An initial FastAPI backend is now present in `backend/`. See [`backend/README.md`](backend/README.md) for local Docker setup and API endpoints. The backend is a development scaffold and has not yet been deployed or independently security-tested. It uses SQLAlchemy, MySQL in Compose, password hashing, bearer tokens, owner-scoped purchase/claim access, and private invoice storage. OCR, email verification/password reset, rate limiting, audit history, migrations, file signature inspection, malware scanning, and production observability remain to be implemented.

GitHub Pages hosts only static files. FastAPI and MySQL need a separate host and a secure production configuration for shared, cross-device data.

## Deployment workflow

The workflow runs on pushes to `main`. Check the repository's Actions tab for the latest result. The site URL appears in **Settings → Pages** after successful deployment.

## Security

- Never commit `.env` files, credentials, API keys, or real invoice files.
- Use unique production secrets and strong database credentials; configure them in the backend host's secret manager.
- Do not expose MySQL directly to the public internet.
- Admin privileges must only be assigned through a trusted bootstrap/administrative process, never public registration.
- Duplicate serial/IMEI matches are review indicators, not proof of fraud.
