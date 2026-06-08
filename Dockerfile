# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /code

# Install system dependencies (ffmpeg, libcairo2, build-essential for pip installs)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libcairo2 \
    libsndfile1-dev \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Hugging Face Spaces expect port 7860 to be exposed
EXPOSE 7860

# Run the streamlit application
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=7860", "--server.address=0.0.0.0"]
