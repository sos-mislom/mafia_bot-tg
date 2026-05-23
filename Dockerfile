FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
EXPOSE 8000

COPY pyproject.toml README.md ./
COPY mafia_bot ./mafia_bot
RUN pip install --no-cache-dir .

CMD ["python", "-m", "mafia_bot"]
