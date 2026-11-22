FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY hinga ./hinga
COPY db ./db
RUN pip install --no-cache-dir .

ENV HINGA_PORT=8741
EXPOSE 8741
CMD ["python", "-m", "hinga"]
