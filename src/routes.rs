use std::convert::Infallible;
use std::time::Duration;

use async_stream::stream;
use axum::body::BoxBody;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use bytes::Bytes;
use futures::Stream;
use hyper::service::Service;
use hyper::{body::to_bytes, header::HeaderValue, Body, Request, Response, StatusCode};
use prometheus::{Encoder, TextEncoder};

use crate::errors::ServiceError;
use crate::metrics::Metrics;
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));
const RESPONSE_DEFAULT: &[u8] = b"MOSEC service";
const RESPONSE_EMPTY: &[u8] = b"no data provided";
const RESPONSE_SHUTDOWN: &[u8] = b"gracefully shutting down";

fn build_response(status: StatusCode, content: Bytes) -> Response<Body> {
    Response::builder()
        .status(status)
        .header("server", HeaderValue::from_static(SERVER_INFO))
        .body(Body::from(content))
        .unwrap()
}

pub(crate) async fn index(_: Request<Body>) -> Response<Body> {
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

pub(crate) async fn metrics(_: Request<Body>) -> Response<Body> {
    let encoder = TextEncoder::new();
    let metrics = prometheus::gather();
    let mut buffer = vec![];
    encoder.encode(&metrics, &mut buffer).unwrap();
    build_response(StatusCode::OK, Bytes::from(buffer))
}

pub(crate) async fn inference(req: Request<Body>) -> Response<Body> {
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
                _ => StatusCode::INTERNAL_SERVER_ERROR,
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

pub(crate) async fn sse_inference(req: Request<Body>) -> Response<BoxBody> {
    let task_manager = TaskManager::global();
    let data = to_bytes(req.into_body()).await.unwrap();
    // let metrics = Metrics::global();

    if task_manager.is_shutdown() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Bytes::from_static(RESPONSE_SHUTDOWN),
        )
            .into_response();
    }

    if data.is_empty() {
        return (StatusCode::OK, Bytes::from_static(RESPONSE_EMPTY)).into_response();
    }

    // metrics.remaining_task.inc();
    match task_manager.submit_sse_task(data).await {
        Ok((task, mut rx)) => {
            let stream = async_stream::stream! {
                while let Some(_) = rx.recv().await {
                    yield match task.code {
                        TaskCode::Normal => Ok(Event::default().data(String::from_utf8_lossy(&task.data))),
                        _ => Err(ServiceError::SseError),
                    }
                }
            };
            Sse::new(stream)
                .keep_alive(KeepAlive::new().interval(Duration::from_secs(3)))
                .into_response()
            // content = task.data;
            // status = match task.code {
            //     TaskCode::Normal => {
            //         // Record latency only for successful tasks
            //         metrics
            //             .duration
            //             .with_label_values(&["total", "total"])
            //             .observe(task.create_at.elapsed().as_secs_f64());
            //         StatusCode::OK
            //     }
            //     TaskCode::BadRequestError => StatusCode::BAD_REQUEST,
            //     TaskCode::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
            //     TaskCode::TimeoutError => StatusCode::REQUEST_TIMEOUT,
            //     TaskCode::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
            // }
        }
        Err(err) => {
            // Handle errors for which tasks cannot be retrieved
            let content = Bytes::from(err.to_string());
            let status = match err {
                ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
                ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
                _ => StatusCode::INTERNAL_SERVER_ERROR,
            };
            (status, content).into_response()
        }
    }
    // metrics.remaining_task.dec();
    // metrics
    //     .throughput
    //     .with_label_values(&[status.as_str()])
    //     .inc();

    // if status == StatusCode::CONTINUE {
    //     return Sse::new(stream)
    //         .keep_alive(KeepAlive::new().interval(Duration::from_secs(3)))
    //         .into_response();
    // }
    // (status, content).into_response()
}
