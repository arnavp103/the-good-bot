FROM python:3.11-slim

WORKDIR /app

# Install git and other dependencies
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY bot.py .
COPY pyproject.toml .
COPY .env .
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Allow root user to access the users git directory
RUN git config --global --add safe.directory '*'


# Run the bot
CMD ["python", "bot.py"]