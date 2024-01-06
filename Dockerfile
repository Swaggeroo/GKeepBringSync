FROM python:3.10
LABEL authors="Swaggeroo"

# install dependencies from requirements.txt
COPY src/app.py .
COPY requirements.txt .

RUN pip install python-bring-api gkeepapi gpsoauth==1.0.2 urllib3==1.25.1 schedule

# start app
CMD [ "python", "./app.py" ]