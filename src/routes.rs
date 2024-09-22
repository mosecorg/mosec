// Copyright 2023 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use std::time::Duration;

use axum::body::{to_bytes, Body};
use axum::http::header::{HeaderValue, CONTENT_TYPE};
use axum::http::{Request, Response, StatusCode, Uri};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use bytes::Bytes;
use prometheus_client::encoding::text::encode;
use tracing::warn;
use utoipa::OpenApi;

use crate::errors::ServiceError;
use crate::metrics::{CodeLabel, Metrics, DURATION_LABEL, REGISTRY};
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));
const RESPONSE_DEFAULT: &[u8] = b"MOSEC service";
const RESPONSE_EMPTY: &[u8] = b"no data provided";
const RESPONSE_TOO_LARGE: &[u8] = b"request body is too large";
const RESPONSE_SHUTDOWN: &[u8] = b"gracefully shutting down";
const DEFAULT_RESPONSE_MIME: &str = "application/json";
const DEFAULT_MAX_REQUEST_SIZE: usize = 10 * 1024 * 1024; // 10MiB

fn build_response(status: StatusCode, content: Bytes) -> Response<Body> {
    Response::builder()
        .status(status)
        .header("server", HeaderValue::from_static(SERVER_INFO))
        .body(Body::from(content))
        .unwrap()
}

#[utoipa::path(
    get,
    path = "/",
    responses(
        (
            status = StatusCode::OK,
            description = "Root path, can be used for liveness health check",
            body = String,
        ),
        (
            status = StatusCode::SERVICE_UNAVAILABLE,
            description = "SERVICE_UNAVAILABLE",
            body = String,
        ),
    ),
)]
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

#[utoipa::path(
    get,
    path = "/metrics",
    responses(
        (status = StatusCode::OK, description = "Get metrics", body = String),
    ),
)]
pub(crate) async fn metrics(_: Request<Body>) -> Response<Body> {
    let mut encoded = String::new();
    let registry = REGISTRY.get().unwrap();
    encode(&mut encoded, registry).unwrap();
    build_response(StatusCode::OK, Bytes::from(encoded))
}

#[utoipa::path(
    post,
    path = "/openapi/reserved/inference",
    responses(
        (status = StatusCode::OK, description = "Inference"),
        (status = StatusCode::BAD_REQUEST, description = "BAD_REQUEST"),
        (status = StatusCode::SERVICE_UNAVAILABLE, description = "SERVICE_UNAVAILABLE"),
        (status = StatusCode::UNPROCESSABLE_ENTITY, description = "UNPROCESSABLE_ENTITY"),
        (status = StatusCode::REQUEST_TIMEOUT, description = "REQUEST_TIMEOUT"),
        (status = StatusCode::INTERNAL_SERVER_ERROR, description = "INTERNAL_SERVER_ERROR"),
        (status = StatusCode::TOO_MANY_REQUESTS, description = "TOO_MANY_REQUESTS"),
    ),
)]
pub(crate) async fn inference(uri: Uri, req: Request<Body>) -> Response<Body> {
    let task_manager = TaskManager::global();
    let endpoint = uri.path();
    let mime = match task_manager.get_mime_type(endpoint) {
        Some(mime) => mime.as_str(),
        None => DEFAULT_RESPONSE_MIME,
    };

    if task_manager.is_shutdown() {
        return build_response(
            StatusCode::SERVICE_UNAVAILABLE,
            Bytes::from_static(RESPONSE_SHUTDOWN),
        );
    }

    let data = match to_bytes(req.into_body(), DEFAULT_MAX_REQUEST_SIZE).await {
        Ok(data) => data,
        Err(err) => {
            warn!(?err, "failed to read request body (too large)");
            return build_response(
                StatusCode::PAYLOAD_TOO_LARGE,
                Bytes::from_static(RESPONSE_TOO_LARGE),
            );
        }
    };
    if data.is_empty() {
        return build_response(StatusCode::OK, Bytes::from_static(RESPONSE_EMPTY));
    }

    let (status, content);
    let metrics = Metrics::global();
    metrics.remaining_task.inc();
    match task_manager.submit_task(data, endpoint).await {
        Ok(task) => {
            content = task.data;
            status = match task.code {
                TaskCode::Normal => {
                    // Record latency only for successful tasks
                    metrics
                        .duration
                        .get_or_create(
                            DURATION_LABEL
                                .get()
                                .expect("DURATION_LABEL is not initialized"),
                        )
                        .observe(task.create_at.elapsed().as_secs_f64());
                    StatusCode::OK
                }
                TaskCode::BadRequestError => StatusCode::BAD_REQUEST,
                TaskCode::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
                TaskCode::TimeoutError => StatusCode::REQUEST_TIMEOUT,
                _ => StatusCode::INTERNAL_SERVER_ERROR,
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
        .get_or_create(&CodeLabel {
            code: status.as_u16(),
            endpoint: endpoint.to_string(),
        })
        .inc();

    let mut resp = build_response(status, content);
    if status == StatusCode::OK {
        resp.headers_mut()
            .insert(CONTENT_TYPE, HeaderValue::from_str(mime).unwrap());
    }
    resp
}

#[utoipa::path(
    post,
    path = "/openapi/reserved/inference_sse",
    responses(
        (status = StatusCode::OK, description = "Inference"),
        (status = StatusCode::BAD_REQUEST, description = "BAD_REQUEST"),
        (status = StatusCode::SERVICE_UNAVAILABLE, description = "SERVICE_UNAVAILABLE"),
        (status = StatusCode::UNPROCESSABLE_ENTITY, description = "UNPROCESSABLE_ENTITY"),
        (status = StatusCode::REQUEST_TIMEOUT, description = "REQUEST_TIMEOUT"),
        (status = StatusCode::INTERNAL_SERVER_ERROR, description = "INTERNAL_SERVER_ERROR"),
        (status = StatusCode::TOO_MANY_REQUESTS, description = "TOO_MANY_REQUESTS"),
    ),
)]
pub(crate) async fn sse_inference(uri: Uri, req: Request<Body>) -> Response<Body> {
    let task_manager = TaskManager::global();
    let endpoint = uri.path();

    if task_manager.is_shutdown() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Bytes::from_static(RESPONSE_SHUTDOWN),
        )
            .into_response();
    }

    let data = match to_bytes(req.into_body(), DEFAULT_MAX_REQUEST_SIZE).await {
        Ok(data) => data,
        Err(err) => {
            warn!(?err, "failed to read request body (too large)");
            return build_response(
                StatusCode::PAYLOAD_TOO_LARGE,
                Bytes::from_static(RESPONSE_TOO_LARGE),
            );
        }
    };
    if data.is_empty() {
        return (StatusCode::OK, Bytes::from_static(RESPONSE_EMPTY)).into_response();
    }

    let metrics = Metrics::global();
    match task_manager.submit_sse_task(data, endpoint).await {
        Ok(mut rx) => {
            let stream = async_stream::stream! {
                while let Some((msg, code)) = rx.recv().await {
                    yield match code {
                        TaskCode::Normal => {
                            Ok(Event::default().data(String::from_utf8_lossy(&msg)))
                        },
                        TaskCode::BadRequestError | TaskCode::InternalError | TaskCode::ValidationError | TaskCode::TimeoutError => {
                            Ok(Event::default().event("error").data(
                                format!("{}: {}", ServiceError::SSEError(code), String::from_utf8_lossy(&msg))),
                            )
                        }
                        _ => {
                            warn!(?code, ?msg, "unexpected error in SSE");
                            Err(ServiceError::SSEError(code))
                        }
                    }
                }
            };
            Sse::new(stream)
                .keep_alive(KeepAlive::new().interval(Duration::from_secs(3)))
                .into_response()
        }
        Err(err) => {
            // Handle errors for which tasks cannot be retrieved
            let content = Bytes::from(err.to_string());
            let status = match err {
                ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
                ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
                _ => StatusCode::INTERNAL_SERVER_ERROR,
            };
            metrics
                .throughput
                .get_or_create(&CodeLabel {
                    code: status.as_u16(),
                    endpoint: endpoint.to_string(),
                })
                .inc();
            (status, content).into_response()
        }
    }
}

#[derive(OpenApi)]
#[openapi(paths(index, metrics, inference, sse_inference))]
pub(crate) struct RustAPIDoc;
