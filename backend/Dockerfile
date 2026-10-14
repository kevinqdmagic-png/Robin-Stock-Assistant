FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py main.py analytics.py trading_calendar.py research_archive.py market_insights.py task_center.py research_stocks.py quote_providers.py daily_providers.py capital_behavior.py capital_watch.py intraday_scheduler.py learning_loop.py ./
RUN mkdir -p /var/lib/robin && chmod 0777 /var/lib/robin
COPY data ./data
COPY tests ./tests
CMD ["python", "main.py"]
