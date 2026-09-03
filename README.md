# MedLocate

MedLocate is a server-rendered Django prototype for finding medicine stock at participating facilities and managing secure prescription workflows in Botswana.

The current vertical slice implements:

- Custom users with patient, doctor, dispenser, inventory, facility administrator and platform administrator roles.
- Patient self-registration and secure Django session authentication.
- Facility membership boundaries for staff.
- Facility and medicine master data.
- Audited facility inventory maintenance with freshness and low-stock indicators.
- Validated Excel inventory previews, row-level errors, upload history and atomic snapshot commits.
- Patient stock search by medicine name, generic name, alias, code or barcode.
- Optional browser geolocation and Haversine distance ranking.
- Doctor-created, expiring multi-item prescriptions delivered to patient accounts.
- Opaque QR tokens stored only as keyed hashes, with protected QR image access.
- Authorized partial/full dispensing with atomic stock deduction and audit records.
- A responsive institutional interface adapted from the TEBELO layout reference.

Only synthetic data should be used. This prototype does not diagnose, recommend treatment, reserve stock, or guarantee availability.

## Quick start

Python 3.12+ is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The seed command prints two synthetic demonstration accounts.

SQLite is used when `POSTGRES_DB` is unset for a quick local demonstration. Set the PostgreSQL variables shown in `.env.example` for database parity and deployment work.

## Tests

```bash
python manage.py test
```

## Implementation boundary

This implementation covers roadmap phases 1–7 from the technical design. Interactive maps, browser-based OCR/barcode capture, and final hardening/evaluation remain sequenced in the documented roadmap rather than being represented as completed.
