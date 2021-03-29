FROM python:3.9.6-alpine

WORKDIR /app

ADD requirements.txt /app/
RUN pip install -r requirements.txt

ADD *.py /app/

ENV FLASK_APP "app"
ENTRYPOINT python -m flask run --host 0.0.0.0
