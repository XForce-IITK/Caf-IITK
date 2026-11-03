# One image for caf-api, caf-worker and mockpay; docker-compose.yml
# picks the process with `command`.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

COPY alembic.ini gunicorn.conf.py ./
COPY alembic ./alembic

RUN useradd --create-home caf
USER caf

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
