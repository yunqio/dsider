FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py test_api.py README.md ./
COPY env .env

# Create required directories
RUN mkdir -p conversations exports

# Expose port
EXPOSE 7860

# Command to run the application
CMD ["python", "app.py"]