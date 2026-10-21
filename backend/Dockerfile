FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy all backend Python modules, including entry_alerts and entry_confirmation.
# The entry monitor imports these lazily; missing files otherwise cause HTTP 500.
COPY *.py ./
RUN python -c "import entry_alerts, entry_confirmation"
RUN mkdir -p /var/lib/robin && chmod 0777 /var/lib/robin
COPY data ./data
COPY tests ./tests
CMD ["python", "main.py"]
