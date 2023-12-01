FROM python:3.8.17-slim-bookworm

RUN apt-get update && apt-get install -y gcc python3-dev

# Copy requirements.txt to the container
COPY requirements.txt ./

# Install app dependencies
RUN pip install -r requirements.txt

# Copy the rest of the app source code to the container
COPY app /app

# Copy the demo source code to the container
COPY demo /demo

# COPY langchain /langchain

# COPY update_langchain.sh ./

# RUN bash update_langchain.sh

# Expose the port on which your FastAPI app listens
EXPOSE 8001

# Expose the ports on which your Streamlit app listens
EXPOSE 8501

EXPOSE 8502
