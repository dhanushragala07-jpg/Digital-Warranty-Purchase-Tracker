# Digital Warranty & Purchase Tracker

A web platform for organizing purchases, keeping invoice evidence together, tracking warranty coverage, and managing warranty claims.

## Current build

The repository now includes a responsive static website prototype with:

- Customer dashboard with purchase and warranty summary cards
- Purchase registry with search and warranty-status filtering
- Add-purchase form with date validation and duplicate serial-number warning
- Warranty timeline
- Demo claim creation and claim tracking
- Admin preview for purchase and claim overview
- Mobile-responsive layout
- GitHub Actions workflow for publishing the static frontend with GitHub Pages

**Important:** this is a frontend prototype. Demo records live in browser memory and reset when the page reloads. Login, real invoice uploads/OCR, backend verification, persistent records, and secure admin authorization are not connected yet.

## Architecture

- **Frontend:** HTML, CSS, JavaScript; hosted on GitHub Pages
- **Backend:** FastAPI (Python), to be connected after reviewing the existing API contract
- **Database:** MySQL
- **Document processing:** OCR-assisted invoice extraction, planned integration

GitHub Pages only hosts the static frontend. The FastAPI backend and MySQL database must be deployed separately for shared, cross-device data.

## Publish the frontend

1. Open the repository's **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Open the **Actions** tab and check the `Deploy WarrantyHub frontend` workflow.
4. When deployment succeeds, open **Settings → Pages** to find the published site URL.

The workflow runs on each push to `main` and can also be started manually.

## Next steps

1. Review and connect the frontend to the existing FastAPI endpoints.
2. Implement or complete missing purchase, invoice, and claim endpoints.
3. Deploy FastAPI and MySQL with secure environment variables.
4. Configure the frontend API URL and test workflows across devices.

## Security notes

- Never commit `.env` files, passwords, API keys, database credentials, or real invoice documents.
- Store uploaded invoices privately and restrict access by authenticated user.
- Enforce admin authorization and all important decisions in the backend, not only in the frontend.
- Treat duplicate serial/IMEI matches as review flags, not proof of fraud.
