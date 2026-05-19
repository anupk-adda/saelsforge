FROM python:3.11-slim
WORKDIR /
COPY requirements.txt /backend/requirements.txt
RUN pip install --no-cache-dir -r /backend/requirements.txt
COPY . /backend/
ENV PYTHONPATH=/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
