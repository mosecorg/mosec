## How to build monitoring system for Mosec
In this tutorial, we will explain how to build monitoring system for Mosec, which includes Prometheus and Grafana.

### Prerequisites
Before starting, you need to have Docker and Docker Compose installed on your machine. If you don't have them installed, you can follow the instructions  [get-docker](https://docs.docker.com/get-docker/) and [compose](https://docs.docker.com/compose/install/) to install them.

## Starting the monitoring system
Clone the repository containing the docker-compose.yaml file:
```bash
git clone https://github.com/mosecorg/mosec.git
```

Navigate to the directory containing the docker-compose.yaml file:
```bash
cd mosec/examples/monitor
```

Start the monitoring system by running the following command:
```bash
docker-compose up -d
```
This command will start three containers: Mosec, Prometheus, and Grafana.


## Test
Run test and feed metrics to Prometheus.
```shell
http POST :8000/inference num=1
```

## Accessing Prometheus
Prometheus is a monitoring and alerting system that collects metrics from Mosec. You can access the Prometheus UI by visiting http://127.0.0.1:9090 in your web browser.

## Accessing Grafana
Grafana is a visualization tool for monitoring and analyzing metrics. You can access the Grafana UI by visiting http://127.0.0.1:3000 in your web browser. The default username and password are both admin.

## Stopping the monitoring system
To stop the monitoring system, run the following command:

```bash
docker-compose down
```
This command will stop and remove the containers created by Docker Compose.
