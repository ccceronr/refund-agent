#!/bin/sh
# Railway pre-deploy (design §11): runs in the new image, as app_rw, before it takes traffic.
# Schema first, then the demo data only if the database is empty (redeploys never wipe
# decisions); the seed also stores the staff password hashes from the variables.
# No roles bootstrap here: the app never holds the superuser URL (design §3.3).
set -eu
alembic upgrade head
# Only with DEMO_RESET=<domain>@<today>: a one-time, audited reload of the demo data.
python -m seed.reset_demo
python -m seed.seed --if-empty
