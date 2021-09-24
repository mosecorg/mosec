mod args;
mod coordinator;
mod errors;
mod metrics;
mod protocol;
mod tasks;

use std::net::SocketAddr;

use clap::Clap;
use hyper::{body::to_bytes, header::HeaderValue, Body, Request, Response, Server, StatusCode};
use prometheus::{Encoder, TextEncoder};
use routerify::{Middleware, RouteError, Router, RouterService};
use tokio::signal::unix::{signal, SignalKind};
use tracing::info;
use tracing_subscriber::EnvFilter;

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::errors::ServiceError;
use crate::metrics::Metrics;
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &'static str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));

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
        return Ok(Response::new(Body::from("No data provided")));
    }

    metrics.remaining_task.inc();
    let task = task_manager.submit_task(data).await?;
    match task.code {
        TaskCode::Normal => {
            metrics.remaining_task.dec();
            metrics
                .duration
                .with_label_values(&["total", "total"])
                .observe(task.create_at.elapsed().as_secs_f64());
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

async fn error_handler(err: RouteError) -> Response<Body> {
    let mosec_err = err.downcast::<ServiceError>().unwrap();
    let status = match mosec_err.as_ref() {
        ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
        ServiceError::BadRequestError => StatusCode::BAD_REQUEST,
        ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
        ServiceError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        ServiceError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        ServiceError::GracefulShutdown => StatusCode::SERVICE_UNAVAILABLE,
        ServiceError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };
    let metrics = Metrics::global();

    metrics.remaining_task.dec();
    metrics
        .throughput
        .with_label_values(&[status.as_str()])
        .inc();

    Response::builder()
        .status(status)
        .body(Body::from(mosec_err.to_string()))
        .unwrap()
}

async fn post_middleware_handler(mut resp: Response<Body>) -> Result<Response<Body>, ServiceError> {
    resp.headers_mut()
        .insert("Server", HeaderValue::from_static(SERVER_INFO));
    Ok(resp)
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

    let coordinator = Coordinator::init_from_opts(&opts);
    tokio::spawn(async move {
        coordinator.run().await;
    });

    let router = Router::builder()
        .get("/", index)
        .get("/metrics", metrics)
        .post("/inference", inference)
        .err_handler(error_handler)
        .middleware(Middleware::post(post_middleware_handler))
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
