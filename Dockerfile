FROM python:3.14
LABEL authors="Swaggeroo"

WORKDIR /usr/src/app

# install dependencies from requirements.txt
COPY src/app.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

RUN mkdir ./data

# start app
CMD [ "python", "-u", "./app.py" ]
