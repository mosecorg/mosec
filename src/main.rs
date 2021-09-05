mod args;
mod coordinator;
mod errors;
mod protocol;
mod tasks;

use std::net::SocketAddr;

use clap::Clap;
use hyper::{body::to_bytes, Body, Request, Response, Server};
use routerify::{Router, RouterService};
use tracing::info;
use tracing_subscriber::EnvFilter;

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::errors::{error_handler, ServiceError};
use crate::tasks::{TaskCode, TaskManager};

async fn index(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("TODO: metrics")))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let task_manager = TaskManager::global();
    let data = to_bytes(req.into_body()).await.unwrap();

    if data.is_empty() {
        return Ok(Response::new(Body::from("No data provided")));
    }

    let task = task_manager.submit_task(data).await?;
    match task.code {
        TaskCode::Normal => Ok(Response::new(Body::from(task.data))),
        TaskCode::BadRequestError => Err(ServiceError::BadRequestError),
        TaskCode::ValidationError => Err(ServiceError::ValidationError),
        TaskCode::InternalError => Err(ServiceError::InternalError),
        TaskCode::UnknownError => Err(ServiceError::UnknownError),
    }
}

fn init_env() {
    if std::env::var("RUST_LOG").is_err() {
        std::env::set_var("RUST_LOG", "info")
    }

    tracing_subscriber::fmt::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();
}

#[tokio::main]
async fn main() {
    init_env();
    let opts: Opts = Opts::parse();
    info!(?opts, "parse arguments");

    let mut coordinator = Coordinator::init_from_opts(&opts);
    tokio::spawn(async move {
        coordinator.run().await;
    });

    let router = Router::builder()
        .get("/", index)
        .get("/metrics", metrics)
        .post("/inference", inference)
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
