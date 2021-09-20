mod args;
mod coordinator;
mod errors;
mod metrics;
mod protocol;
mod tasks;

use std::net::SocketAddr;

use clap::Clap;
use hyper::{body::to_bytes, Body, Request, Response, Server, StatusCode};
use prometheus::{Encoder, TextEncoder};
use routerify::{Router, RouterService};
use tokio::signal::unix::{signal, SignalKind};
use tracing::info;
use tracing_subscriber::EnvFilter;

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::errors::{error_handler, ServiceError};
use crate::metrics::Metrics;
use crate::tasks::{TaskCode, TaskManager};

async fn index(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let task_manager = TaskManager::global();
    if task_manager.is_shutdown() {
        return Err(ServiceError::GracefulShutdown);
    }
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let encoder = TextEncoder::new();
    let metrics = prometheus::gather();
    let mut buffer = vec![];
    encoder.encode(&metrics, &mut buffer).unwrap();
    Ok(Response::new(Body::from(buffer)))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let task_manager = TaskManager::global();
    let data = to_bytes(req.into_body()).await.unwrap();
    let metrics = Metrics::global();

    if data.is_empty() {
        metrics
            .throughput
            .with_label_values(&[StatusCode::OK.as_str()])
            .inc();
        return Ok(Response::new(Body::from("No data provided")));
    }

    metrics.remaining_task.inc();
    let task = task_manager.submit_task(data).await?;
    metrics
        .duration
        .with_label_values(&["total", "total"])
        .observe(task.create_at.elapsed().as_secs_f64());
    match task.code {
        TaskCode::Normal => {
            metrics.remaining_task.dec();
            metrics
                .throughput
                .with_label_values(&[StatusCode::OK.as_str()])
                .inc();
            Ok(Response::new(Body::from(task.data)))
        }
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

async fn shutdown_signal() {
    let mut interrupt = signal(SignalKind::interrupt()).unwrap();
    let mut terminate = signal(SignalKind::terminate()).unwrap();
    tokio::select! {
        _ = interrupt.recv() => {
            info!("received interrupt signal");
        },
        _ = terminate.recv() => {
            info!("received terminate signal");
        },
    };
    let task_manager = TaskManager::global();
    task_manager.shutdown().await;
    info!("shutdown complete");
}

#[tokio::main]
async fn main() {
    init_env();
    let opts: Opts = Opts::parse();
    info!(?opts, "parse arguments");

    let coordinator = Coordinator::init_from_opts(&opts);
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
    let addr: SocketAddr = format!("{}:{}", opts.address, opts.port).parse().unwrap();
    let server = Server::bind(&addr).serve(service);
    let graceful = server.with_graceful_shutdown(shutdown_signal());
    if let Err(err) = graceful.await {
        tracing::error!(%err, "server error");
    }
}
