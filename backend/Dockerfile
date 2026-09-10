FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app/backend

COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --timeout 180 --retries 5 --requirement requirements.lock

COPY backend ./

# The idempotent CMS seed reads the approved storefront translations when it
# is run inside the backend image during staging/bootstrap.
RUN mkdir -p /app/frontend/src/i18n
COPY frontend/src/i18n/translations.js /app/frontend/src/i18n/translations.js

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn server:app --host 0.0.0.0 --port 8000"]
