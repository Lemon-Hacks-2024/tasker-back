FROM python:3.12-slim
ENV PYTHONBUFFERED=1

RUN mkdir "app"
RUN pip install poetry

WORKDIR /app

COPY . .

RUN poetry config virtualenvs.create false

RUN poetry install --no-root --no-dev

CMD ["faststream", "run", "app.main:app"]



