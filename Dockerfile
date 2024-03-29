FROM python:3.10
LABEL authors="Swaggeroo"

WORKDIR /usr/src/app

# install dependencies from requirements.txt
COPY src/app.py .

ENV PYTHONUNBUFFERED=1

RUN mkdir ./data

RUN pip install python-bring-api gkeepapi schedule gpsoauth urllib3 python-decouple

# start app
CMD [ "python", "-u", "./app.py" ]
