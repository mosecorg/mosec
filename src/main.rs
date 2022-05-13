// Copyright 2022 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

mod args;
mod coordinator;
mod errors;
mod metrics;
mod protocol;
mod tasks;

use std::net::SocketAddr;

use bytes::Bytes;
use clap::Parser;
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
const RESPONSE_DEFAULT: &[u8] = b"MOSEC service";
const RESPONSE_NOT_FOUND: &[u8] = b"not found";
const RESPONSE_EMPTY: &[u8] = b"no data provided";
const RESPONSE_SHUTDOWN: &[u8] = b"gracefully shutting down";

async fn index(_: Request<Body>) -> Response<Body> {
    let task_manager = TaskManager::global();
    if task_manager.is_shutdown() {
        build_response(
            StatusCode::SERVICE_UNAVAILABLE,
            Bytes::from_static(RESPONSE_SHUTDOWN),
        )
    } else {
        build_response(StatusCode::OK, Bytes::from_static(RESPONSE_DEFAULT))
    }
}

async fn metrics(_: Request<Body>) -> Response<Body> {
    let encoder = TextEncoder::new();
    let metrics = prometheus::gather();
    let mut buffer = vec![];
    encoder.encode(&metrics, &mut buffer).unwrap();
    build_response(StatusCode::OK, Bytes::from(buffer))
}

async fn inference(req: Request<Body>) -> Response<Body> {
    let task_manager = TaskManager::global();
    let data = to_bytes(req.into_body()).await.unwrap();
    let metrics = Metrics::global();

    if task_manager.is_shutdown() {
        return build_response(
            StatusCode::SERVICE_UNAVAILABLE,
            Bytes::from_static(RESPONSE_SHUTDOWN),
        );
    }

    if data.is_empty() {
        return build_response(StatusCode::OK, Bytes::from_static(RESPONSE_EMPTY));
    }

    let (status, content);
    metrics.remaining_task.inc();
    match task_manager.submit_task(data).await {
        Ok(task) => {
            content = task.data;
            status = match task.code {
                TaskCode::Normal => {
                    // Record latency only for successful tasks
                    metrics
                        .duration
                        .with_label_values(&["total", "total"])
                        .observe(task.create_at.elapsed().as_secs_f64());
                    StatusCode::OK
                }
                TaskCode::BadRequestError => StatusCode::BAD_REQUEST,
                TaskCode::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
                TaskCode::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
            }
        }
        Err(err) => {
            // Handle errors for which tasks cannot be retrieved
            content = Bytes::from(err.to_string());
            status = match err {
                ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
                ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
                ServiceError::UnknownError => StatusCode::INTERNAL_SERVER_ERROR,
            };
        }
    }
    metrics.remaining_task.dec();
    metrics
        .throughput
        .with_label_values(&[status.as_str()])
        .inc();

    build_response(status, content)
}

fn build_response(status: StatusCode, content: Bytes) -> Response<Body> {
    Response::builder()
        .status(status)
        .header("server", HeaderValue::from_static(SERVER_INFO))
        .body(Body::from(content))
        .unwrap()
}

async fn service_func(req: Request<Body>) -> Result<Response<Body>, hyper::Error> {
    match (req.method(), req.uri().path()) {
        (&Method::GET, "/") => Ok(index(req).await),
        (&Method::GET, "/metrics") => Ok(metrics(req).await),
        (&Method::POST, "/inference") => Ok(inference(req).await),
        _ => Ok(build_response(
            StatusCode::NOT_FOUND,
            Bytes::from(RESPONSE_NOT_FOUND),
        )),
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
    let barrier = coordinator.run();
    barrier.wait().await;

    let service = make_service_fn(|_| async { Ok::<_, hyper::Error>(service_fn(service_func)) });
    let addr: SocketAddr = format!("{}:{}", opts.address, opts.port).parse().unwrap();
    let server = hyper::Server::bind(&addr).serve(service);
    info!(?addr, "http server is running at");
    let graceful = server.with_graceful_shutdown(shutdown_signal());
    if let Err(err) = graceful.await {
        tracing::error!(%err, "server error");
    }
}
