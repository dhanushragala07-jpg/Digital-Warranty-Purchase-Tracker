# WarrantyHub API (initial backend)

This folder contains the first API implementation for customer accounts, purchase records, private invoice upload, warranty status, claims, and admin review.

## Included endpoints

- `GET /health` and `GET /docs`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/purchases`
- `POST /api/v1/purchases/{id}/invoice`
- `GET/POST /api/v1/claims`
- `GET /api/v1/admin/purchases`, `PATCH /api/v1/admin/purchases/{id}/verification`
- `GET /api/v1/admin/claims`, `PATCH /api/v1/admin/claims/{id}/status`

## Local run with Docker

1. Copy `.env.example` to `.env` **inside this backend folder** and replace every example password/secret with unique values. Keep `.env` out of Git.
2. Set `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD` in that `.env`; `JWT_SECRET` must be a unique random string of at least 32 characters. Use a password manager or a cryptographically secure generator.
3. Run `docker compose --env-file .env up --build -d` from this folder.
4. Open `http://localhost:8000/docs` and `http://localhost:8000/health`.
5. To create an administrator, run `docker compose --env-file .env exec api python create_admin.py` after supplying `ADMIN_EMAIL`, `ADMIN_NAME`, and `ADMIN_PASSWORD` to the container environment securely. Do not use a public customer-registration route to create admins.

The Compose file uses persistent Docker volumes for MySQL and private invoice files. Do not remove volumes if you need to preserve data.

## Important limitations before production

- Invoice files are stored privately and are not exposed through a public file-serving route. MIME type and size are checked, but production should additionally inspect file signatures, scan for malware, and use encrypted object storage with backups.
- OCR is not implemented yet (`ocr_status` returns `not_implemented`). Uploading an invoice does not verify authenticity or warranty eligibility.
- Verification decisions are manual; the current schema is an initial version without a full audit log or review-history table.
- Claim updates are administrator-only but currently use a simple endpoint and need audit history, notifications, and business-specific policy checks.
- SQLAlchemy creates initial tables automatically. Use Alembic migrations before schema changes in a persistent production database.
- Add rate limiting, password reset/email verification, login throttling, monitoring, backups, and a security review before public launch.
- The frontend still uses in-memory demo data; it has not yet been wired to these endpoints.
- Do not deploy MySQL with a public internet port. Deploy API and DB with HTTPS, restricted network access, and secret-manager configuration.
