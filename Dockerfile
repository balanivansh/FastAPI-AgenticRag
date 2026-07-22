# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 7860 (Hugging Face default port)
EXPOSE 7860

# Set execution permission on start script
RUN chmod +x start.sh

# Run both services via start.sh
CMD ["./start.sh"]
