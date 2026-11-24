FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer is cached between code changes
COPY pyproject.toml README.md ./
COPY windops/__init__.py windops/__init__.py
RUN pip install .

COPY . .
RUN pip install --no-deps . && useradd --create-home windops
USER windops

EXPOSE 8000 8501
# The command is set per service in docker-compose.yml
CMD ["uvicorn", "windops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
