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

use axum::{
    routing::{get, post},
    Router,
};
use bytes::Bytes;
use hyper::{body::to_bytes, header::HeaderValue, Body, Request, Response, StatusCode};
use prometheus::{Encoder, TextEncoder};
use tokio::signal::unix::{signal, SignalKind};
use tracing::info;
use tracing_subscriber::fmt::time::OffsetTime;
use tracing_subscriber::{filter, prelude::*, Layer};

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::errors::ServiceError;
use crate::metrics::Metrics;
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));
const RESPONSE_DEFAULT: &[u8] = b"MOSEC service";
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
                TaskCode::TimeoutError => StatusCode::REQUEST_TIMEOUT,
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

async fn shutdown_signal() {
    let mut interrupt = signal(SignalKind::interrupt()).unwrap();
    let mut terminate = signal(SignalKind::terminate()).unwrap();
    loop {
        tokio::select! {
            _ = interrupt.recv() => {
                info!("service received interrupt signal, will ignore it here \
                    since it should be controlled by the main process (send SIGTERM \
                    to `mosec` if you really want to kill it manually)");
            },
            _ = terminate.recv() => {
                info!("service received terminate signal");
                let task_manager = TaskManager::global();
                task_manager.shutdown().await;
                info!("service shutdown complete");
                break;
            },
        };
    }
}

#[tokio::main]
async fn run(opts: &Opts) {
    let coordinator = Coordinator::init_from_opts(opts);
    let barrier = coordinator.run();
    barrier.wait().await;

    let app = Router::new()
        .route("/", get(index))
        .route("/metrics", get(metrics))
        .route("/inference", post(inference));

    let addr: SocketAddr = format!("{}:{}", opts.address, opts.port).parse().unwrap();
    info!(?addr, "http service is running");
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

fn main() {
    let opts: Opts = argh::from_env();

    // this has to be defined before tokio multi-threads
    let timer = OffsetTime::local_rfc_3339().expect("local time offset");
    if opts.debug {
        // use colorful log for debug
        let output = tracing_subscriber::fmt::layer().compact().with_timer(timer);
        tracing_subscriber::registry()
            .with(
                output
                    .with_filter(filter::filter_fn(|metadata| {
                        !metadata.target().starts_with("hyper")
                    }))
                    .with_filter(filter::LevelFilter::DEBUG),
            )
            .init();
    } else {
        // use JSON format for production
        tracing_subscriber::fmt()
            .with_max_level(tracing::Level::INFO)
            .json()
            .with_timer(timer)
            .init();
    }

    info!(?opts, "parse service arguments");
    run(&opts);
}
