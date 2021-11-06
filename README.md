# Service

## Setup

1. Install Docker
2. clone Repo
3. In Repo root, `mkdir ./docker/dynamodb` && `chmod 777 ./docker/dynamodb`.
   This is necessary because a volume mount is setup to allow dynamo store state as .db file.
4. Spin Up all 4 services using `docker-compose up --build`
5. Seed the application with the battery initial state using:
   `curl http://localhost:5003/state/?settlementPeriodStartTime=2021-10-04T00:00:00`
