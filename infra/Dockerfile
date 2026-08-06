FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY services/ services/
COPY run.py .

RUN mkdir -p logs

EXPOSE 8080

CMD ["python", "run.py"]
