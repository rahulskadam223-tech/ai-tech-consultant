FROM python:3.11-slim
WORKDIR /app
COPY task1-knowledge-brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY task1-knowledge-brain/app ./app
COPY prompts ./prompts
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
