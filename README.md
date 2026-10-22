# MedLocate

MedLocate is a Django and PostgreSQL staff platform for medicine availability, secure QR prescriptions and dispensing in Botswana. The October 2026 platform update follows `main.pdf` (RQ01–RQ09).

- Approved doctors and nurses search positive, unexpired stock at active facilities, with update times, optional distance ordering, manual starting points, maps and directions.
- Doctors create prescriptions with recipient name/reference, medicine, dosage, quantity, instructions and validity. Recipients do not need accounts. Printable QR references contain an opaque token; database lookup uses its keyed hash.
- Nurses and pharmacy staff verify and record full or partial dispensing. PostgreSQL row locks, confirmation keys and atomic transactions prevent duplicate submissions and inconsistent stock changes. Batch allocations link each dispensing event to the stock used.
- Pharmacy staff maintain assigned-facility stock, batch details and expiry dates, with validated Excel previews and retained row errors. Nurses and doctors cannot manually edit inventory.
- Five role-scoped reports cover stock/expiry, inventory activity, issued prescriptions, dispensing and verification. Filters include facility, medicine and date; CSV exports omit recipient names and clinical instructions.
- Dashboards summarize role responsibilities, low/zero stock, approaching expiry and recent activity. Staff with multiple assignments can select their working facility.
- Camera barcode/QR scanning uses the browser's native BarcodeDetector where supported. Manual entry is always available and medicine matches require confirmation. No images or device coordinates are stored. Label OCR is not included; the document permits barcode or label-image identification.
- Platform administration retains user creation, role/facility assignments, facility management and audit history.

Public patient registration, guest stock search and patient prescription routes are closed. Existing patient records are retained for historical references. Existing dispenser and inventory roles keep their original permissions; new staff accounts use doctor, nurse or pharmacy roles (plus administrative roles).

Use synthetic demonstration data only. Recorded stock is advisory, not a reservation. The prototype does not provide treatment advice or billing.

## Get the latest code on Windows

Open PowerShell in the folder where you keep your projects. If MedLocate is already on the PC, enter its folder and pull the latest code:

```powershell
cd .\MedLocate
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements/development.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

If this is a new Windows PC, clone the repository and create the virtual environment first:

```powershell
git clone https://github.com/Yardsphuthego/MedLocate.git
cd .\MedLocate
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/development.txt
```

Configure PostgreSQL as described below, then run the `migrate` and `runserver` commands from the first block. If an existing checkout has no `.venv` folder, run `py -m venv .venv` before the update commands. Save or commit local changes before pulling. The update commands do not reset database data. Open <http://127.0.0.1:8001/> after starting the server.

## Quick start on macOS/Linux

Python 3.12+ and PostgreSQL are required for the normal workflow. With a local PostgreSQL server accepting your OS account:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
createdb medlocate
python manage.py migrate
python manage.py seed_demo  # fresh synthetic demo databases only
python manage.py runserver 127.0.0.1:8001
```

Open <http://127.0.0.1:8001/>. Demo accounts:

The public header provides staff sign-in. The Django administration at <http://127.0.0.1:8001/admin/> uses Django Unfold and requires a superuser account. Its static assets are included by `collectstatic` in deployment.

| Role | Username | Password |
| --- | --- | --- |
| Doctor | demo.doctor | DemoDoctor2026! |
| Nurse | demo.nurse | DemoNurse2026! |
| Pharmacy staff | demo.pharmacy | DemoPharmacy2026! |

The seed command also maintains the legacy inventory/dispenser demonstration users. It resets legacy demo passwords and stock, so do not run it against operational data.

To fill a development workspace with connected synthetic facilities, medicines, stock, imports, prescriptions and dispensing history without resetting existing passwords or stock, run `python manage.py populate_workspace --apply`. The command is additive and repeatable, and refuses to run when `DEBUG` is off. Its records use `MLP-` pilot codes and synthetic recipient references; they are not clinical data.

For another database, export `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` and `POSTGRES_PORT` using `.env.example` as a reference. Environment files are not loaded automatically. Defaults are database `medlocate`, the current OS username, localhost and port 5432. Production requires an explicit PostgreSQL configuration. `MEDLOCATE_USE_SQLITE=1` exists only for legacy data transfer; concurrency guarantees require PostgreSQL.

The local update backed up SQLite to `.local/pre-staff-platform.sqlite3` and imported existing records into the separate `medlocate` PostgreSQL database. Media files remain in `media/`. Existing browser sessions require a fresh sign-in after the database switch.

## Tests

```bash
python manage.py test
```

## Validation and limitations

The test suite includes role denial, facility isolation, stock/import validation, full and partial dispensing, rollback, expiry checks, batch allocation, report filters and export privacy, plus a PostgreSQL concurrent-confirmation test. Run against PostgreSQL using a role allowed to create a test database.

Camera support varies by browser; unsupported browsers show manual entry. Maps/directions open external map services, while stock lists remain usable without them. Search/report response-time targets apply to the prototype load and are not a production load-test certification. Production deployment, clinical governance and external provider integrations remain separate deployment work.
