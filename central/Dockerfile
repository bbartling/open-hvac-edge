FROM python:3.14-slim-bookworm

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/bask_223p ./src/bask_223p
COPY central ./central
RUN pip install --no-cache-dir -e "." && pip install --no-cache-dir -e ./central

EXPOSE 8780
CMD ["python", "-m", "central", "--config", "/config/central.yaml"]
