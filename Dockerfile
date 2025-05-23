# Start from a slim Python base image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Set UTF-8 encoding and locale for pandas/Dash
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1

# Install system dependencies for scientific Python and Dash
RUN apt-get update && \
    apt-get install -y gcc g++ build-essential libffi-dev libssl-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose port for Dash dashboard (default 8050)
EXPOSE 8050

# Healthcheck for container robustness (checks if Python is alive)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

# Set environment variables if needed
# ENV ENV_VAR_NAME=value

# Default command: run the trading bot
CMD ["python", "main.py"]
# To run the dashboard, override with:
# docker run -p 8050:8050 hydrobot python dashboard/app.py
# Or, for module entrypoint:
# CMD ["python", "-m", "hydrobot.trader"]
