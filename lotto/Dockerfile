FROM python:3.14

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY src /app
WORKDIR /app

ENTRYPOINT ["python", "-m", "uvicorn", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*", "lotto.main:app"]
CMD ["--reload"]
