FROM python:3.11-slim

WORKDIR /app

# Install git, ssh and other dependencies
RUN apt-get update && \
    apt-get install -y git openssh-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Fix SSH permissions
RUN mkdir -p /root/.ssh && \
    chmod 700 /root/.ssh

# Copy project files
COPY bot.py .
COPY pyproject.toml .
COPY .env .

# Install dependencies
RUN pip install discord.py python-dotenv

# Configure git
RUN git config --global --add safe.directory '*'

# TODO: make these configurable
RUN git config --global user.email "arnavp103@gmail.com"
RUN git config --global user.name "Arnav Priyadarshi"

# Run the bot
CMD ["python", "bot.py"]