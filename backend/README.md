# VibeWealth Backend

The backend is a modular FastAPI foundation for VibeWealth 2.0. It currently
provides application configuration, configurable CORS, and a health endpoint.
The local PostgreSQL service is available through Docker Compose. The API does
not connect to the database yet; authentication and financial features are
planned but not implemented.

## Requirements

- Python 3.11 or newer
- pip
- Docker Engine and Docker Compose (the project's configured setup uses WSL2 Ubuntu)

## Set up a Python environment

From the repository root:

```sh
cd backend
python -m venv .venv
```

Activate the environment:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```sh
source .venv/bin/activate
```

## Install dependencies

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure environment variables

Copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` with a private,
locally chosen value before starting the database. The example password is a
placeholder and must not be used as a credential. Settings are read from
environment variables; a local `.env` file is optional for the API.

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_DB` | `vibewealth` | Local PostgreSQL database name |
| `POSTGRES_USER` | `vibewealth_app` | Local PostgreSQL user |
| `POSTGRES_PASSWORD` | *(set locally)* | Local PostgreSQL password |
| `POSTGRES_PORT` | `5432` | Host loopback port mapped to PostgreSQL |
| `APP_TITLE` | `VibeWealth API` | FastAPI application title |
| `APP_VERSION` | `0.1.0` | API version |
| `DATABASE_URL` | `postgresql+psycopg://localhost:5432/vibewealth` | Reserved for future API database integration; no connection is made yet |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list of allowed browser origins |

`.env` and other local secret files are excluded from Git. Do not commit local
credentials.

## Run the development server

From `backend/` with the virtual environment active:

```sh
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; its health endpoint is
`http://127.0.0.1:8000/health`.

## Run tests

```sh
python -m pytest
```

## Manage the local PostgreSQL database

Run these commands in WSL2 Ubuntu from the repository's `backend/` directory.
Create `.env` from `.env.example` once, then set a private `POSTGRES_PASSWORD`
before starting the service. The database port is bound only to `127.0.0.1` on
the host; set `POSTGRES_PORT` in `.env` to change it.

Start PostgreSQL in the background:

```sh
docker compose up -d db
```

Inspect service state and logs:

```sh
docker compose ps
docker compose logs -f db
```

Check readiness from inside the container:

```sh
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Stop the container while keeping database data:

```sh
docker compose down
```

Reset the local database by stopping it and removing its named data volume:

```sh
docker compose down -v
```

The reset command permanently deletes local PostgreSQL data. The named volume
is `vibewealth_postgres_data`.
