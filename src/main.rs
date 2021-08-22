mod errors;
mod protocol;

use std::{net::SocketAddr, time::Duration, vec};

use errors::{error_handler, ServiceError};
use hyper::{body::to_bytes, Body, Request, Response, Server};
use protocol::{Protocol, TaskCode};
use routerify::prelude::*;
use routerify::{Router, RouterService};
use tokio::{sync::oneshot, time::timeout};
use tracing::error;
use tracing_subscriber::EnvFilter;

async fn index(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("TODO: metrics")))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let protocol = req.data::<Protocol>().unwrap().clone();
    let (tx, rx) = oneshot::channel();
    let data = to_bytes(req.into_body()).await.unwrap();

    if data.is_empty() {
        return Ok(Response::new(Body::from("No data provided")));
    }

    let task_id = match protocol.add_new_task(data, tx).await {
        Ok(id) => id,
        Err(_) => return Err(ServiceError::TooManyRequests),
    };
    if timeout(protocol.timeout, rx).await.is_err() {
        return Err(ServiceError::Timeout);
    }

    if let Some(task) = protocol.get_task(task_id).await {
        match task.code {
            TaskCode::Normal => Ok(Response::new(Body::from(task.data))),
            TaskCode::BadRequestError => Err(ServiceError::BadRequestError),
            TaskCode::ValidationError => Err(ServiceError::ValidationError),
            TaskCode::InternalError => Err(ServiceError::InternalError),
            TaskCode::UnknownError => Err(ServiceError::UnknownError),
        }
    } else {
        error!(%task_id, "cannot find this task");
        Err(ServiceError::UnknownError)
    }
}

#[tokio::main]
async fn main() {
    if std::env::var("RUST_LOG").is_err() {
        std::env::set_var("RUST_LOG", "info")
    }

    tracing_subscriber::fmt::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let protocol = Protocol::new(
        vec![1, 8, 1],
        "/tmp/mosec",
        1024,
        Duration::from_millis(3000),
        Duration::from_millis(10),
    );
    let mut protocol_runner = protocol.clone();
    tokio::spawn(async move {
        protocol_runner.run().await;
    });
    let state_router = Router::builder()
        .data(protocol.clone())
        .post("/", inference)
        .build()
        .unwrap();

    let router = Router::builder()
        .get("/", index)
        .get("/metrics", metrics)
        .scope("/inference", state_router)
        .err_handler(error_handler)
        .build()
        .unwrap();

    let service = RouterService::new(router).unwrap();
    let addr = SocketAddr::from(([127, 0, 0, 1], 8000));
    let server = Server::bind(&addr).serve(service);
    if let Err(err) = server.await {
        tracing::error!(%err, "server error");
    }
}
