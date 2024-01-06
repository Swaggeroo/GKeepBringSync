FROM python:3.10
LABEL authors="Swaggeroo"

# install dependencies from requirements.txt
COPY src/app.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

# start app
CMD [ "python", "./app.py" ]