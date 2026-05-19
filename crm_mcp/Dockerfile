FROM python:3.11-slim
WORKDIR /
COPY requirements.txt /crm_mcp/requirements.txt
RUN pip install --no-cache-dir -r /crm_mcp/requirements.txt
COPY . /crm_mcp/
ENV PYTHONPATH=/
CMD ["python", "/crm_mcp/server.py"]
