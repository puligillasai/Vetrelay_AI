FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir uvicorn

COPY backend ./backend
COPY mock_data ./mock_data

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
