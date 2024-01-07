FROM python:3.10
LABEL authors="Swaggeroo"

WORKDIR /usr/src/app

# install dependencies from requirements.txt
COPY src/app.py .

RUN mkdir ./data

RUN pip install python-bring-api gkeepapi schedule
RUN pip install gpsoauth==1.0.2 urllib3==1.25.1

# start app
CMD [ "python", "./app.py" ]