FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml alembic.ini ./
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

RUN pip install --upgrade pip && pip install \
    "fastapi>=0.110,<0.122" \
    "uvicorn[standard]>=0.29" \
    "sqlalchemy>=2.0,<2.1" \
    "asyncpg>=0.29" \
    "aiosqlite>=0.19" \
    "alembic>=1.13" \
    "pydantic>=2.5" \
    "pydantic-settings>=2.2" \
    "pyjwt>=2.8" \
    "passlib[bcrypt]>=1.7.4" \
    "bcrypt>=4.1,<4.3" \
    "redis>=5.0" \
    "structlog>=24.1" \
    "python-multipart>=0.0.9" \
    "email-validator>=2.0"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
