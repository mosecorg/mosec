mod args;
mod coordinator;
mod errors;
mod metrics;
mod protocol;
mod tasks;

use std::net::SocketAddr;

use clap::Clap;
use hyper::service::{make_service_fn, service_fn};
use hyper::{body::to_bytes, header::HeaderValue, Body, Method, Request, Response, StatusCode};
use prometheus::{Encoder, TextEncoder};
use tokio::signal::unix::{signal, SignalKind};
use tracing::info;
use tracing_subscriber::EnvFilter;

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::errors::ServiceError;
use crate::metrics::Metrics;
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));
const NOT_FOUND: &[u8] = b"Not Found";

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
    metrics.remaining_task.dec();
    let mut status_code = StatusCode::OK;
    match task.code {
        TaskCode::Normal => {
            metrics
                .duration
                .with_label_values(&["total", "total"])
                .observe(task.create_at.elapsed().as_secs_f64());
            metrics
                .throughput
                .with_label_values(&[status_code.as_str()])
                .inc();
            Ok(Response::new(Body::from(task.data)))
        }
        TaskCode::ValidationError => {
            // Allow user's customized error message
            status_code = StatusCode::UNPROCESSABLE_ENTITY;
            metrics
                .throughput
                .with_label_values(&[status_code.as_str()])
                .inc();
            Ok(Response::builder()
                .status(status_code)
                .header("server", HeaderValue::from_static(SERVER_INFO))
                .body(Body::from(task.data))
                .unwrap())
        }
        TaskCode::BadRequestError => Err(ServiceError::BadRequestError),
        TaskCode::InternalError => Err(ServiceError::InternalError),
        TaskCode::UnknownError => Err(ServiceError::UnknownError),
    }
}

fn error_handler(err: ServiceError) -> Response<Body> {
    let status = match err {
        ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
        ServiceError::BadRequestError => StatusCode::BAD_REQUEST,
        ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
        ServiceError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        ServiceError::GracefulShutdown => StatusCode::SERVICE_UNAVAILABLE,
        ServiceError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };
    let metrics = Metrics::global();

    metrics
        .throughput
        .with_label_values(&[status.as_str()])
        .inc();

    Response::builder()
        .status(status)
        .header("server", HeaderValue::from_static(SERVER_INFO))
        .body(Body::from(err.to_string()))
        .unwrap()
}

async fn service_func(req: Request<Body>) -> Result<Response<Body>, hyper::Error> {
    let res = match (req.method(), req.uri().path()) {
        (&Method::GET, "/") => index(req).await,
        (&Method::GET, "/metrics") => metrics(req).await,
        (&Method::POST, "/inference") => inference(req).await,
        _ => Ok(Response::builder()
            .status(StatusCode::NOT_FOUND)
            .body(NOT_FOUND.into())
            .unwrap()),
    };
    match res {
        Ok(mut resp) => {
            resp.headers_mut()
                .insert("server", HeaderValue::from_static(SERVER_INFO));
            Ok(resp)
        }
        Err(err) => Ok(error_handler(err)),
    }
}

async fn shutdown_signal() {
    let mut interrupt = signal(SignalKind::interrupt()).unwrap();
    let mut terminate = signal(SignalKind::terminate()).unwrap();
    loop {
        tokio::select! {
            _ = interrupt.recv() => {
                info!("received interrupt signal and ignored at controller side");
            },
            _ = terminate.recv() => {
                info!("received terminate signal");
                let task_manager = TaskManager::global();
                task_manager.shutdown().await;
                info!("shutdown complete");
                break;
            },
        };
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

    let coordinator = Coordinator::init_from_opts(&opts);
    tokio::spawn(async move {
        coordinator.run().await;
    });

    let service = make_service_fn(|_| async { Ok::<_, hyper::Error>(service_fn(service_func)) });
    let addr: SocketAddr = format!("{}:{}", opts.address, opts.port).parse().unwrap();
    let server = hyper::Server::bind(&addr).serve(service);
    let graceful = server.with_graceful_shutdown(shutdown_signal());
    if let Err(err) = graceful.await {
        tracing::error!(%err, "server error");
    }
}
