# Digital Warranty & Purchase Tracker

A web platform for organizing purchases, storing invoice evidence, tracking warranty coverage, and managing warranty claims.

## Planned features

- Customer portal for account access and purchase registration
- Invoice upload and OCR-assisted extraction of purchase details
- Warranty status and expiry tracking
- Claim submission and claim-status tracking
- Admin dashboard for purchase verification and claim handling
- Duplicate serial/IMEI indicators for manual review
- Configurable product fields for different business types

## Architecture

- **Frontend:** HTML, CSS, JavaScript (GitHub Pages can host the static website)
- **Backend:** FastAPI (Python)
- **Database:** MySQL
- **Document processing:** OCR-assisted invoice extraction

GitHub Pages hosts only the frontend. The FastAPI service and MySQL database must be deployed separately for shared, cross-device data and production use.

## Project status

The initial frontend scaffold is being built first. Until a backend URL is configured, the interface may use demo data and must not be treated as a live warranty record system.

## Development roadmap

1. Build the responsive customer/admin frontend.
2. Connect forms and dashboards to the existing FastAPI API.
3. Add or complete missing backend endpoints after reviewing the API contract.
4. Configure secure environment variables and deploy the backend/database.
5. Deploy the frontend and test customer/admin workflows across devices.

## Security notes

- Never commit `.env` files, passwords, API keys, database credentials, or real invoice documents.
- Keep uploaded invoices private and restrict access by authenticated user.
- Admin actions must be authorized by the backend, not only hidden in the frontend.
