FROM python:3.10
LABEL authors="Swaggeroo"

WORKDIR /usr/src/app

# install dependencies from requirements.txt
COPY src/app.py .

ENV PYTHONUNBUFFERED=1

RUN mkdir ./data

RUN pip install python-bring-api gkeepapi schedule gpsoauth==1.0.2 urllib3==1.25.1 python-decouple~=3.8

# start app
CMD [ "python", "-u", "./app.py" ]
