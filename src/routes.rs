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

use axum::body::BoxBody;
use axum::extract::State;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use bytes::Bytes;
use hyper::{
    body::to_bytes,
    header::{HeaderValue, CONTENT_TYPE},
    Body, Request, Response, StatusCode,
};
use prometheus_client::encoding::text::encode;

use crate::errors::ServiceError;
use crate::metrics::{CodeLabel, Metrics, DURATION_LABEL, REGISTRY};
use crate::tasks::{TaskCode, TaskManager};

const SERVER_INFO: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));
const RESPONSE_DEFAULT: &[u8] = b"MOSEC service";
const RESPONSE_EMPTY: &[u8] = b"no data provided";
const RESPONSE_SHUTDOWN: &[u8] = b"gracefully shutting down";

#[derive(Clone)]
pub(crate) struct AppState {
    pub mime: String,
}

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
    let mut encoded = String::new();
    let registry = REGISTRY.get().unwrap();
    encode(&mut encoded, registry).unwrap();
    build_response(StatusCode::OK, Bytes::from(encoded))
}

pub(crate) async fn inference(State(state): State<AppState>, req: Request<Body>) -> Response<Body> {
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
        })
        .inc();

    let mut resp = build_response(status, content);
    if status == StatusCode::OK {
        resp.headers_mut()
            .insert(CONTENT_TYPE, HeaderValue::from_str(&state.mime).unwrap());
    }
    resp
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
        Ok(mut rx) => {
            let stream = async_stream::stream! {
                while let Some((msg, code)) = rx.recv().await {
                    yield match code {
                        TaskCode::StreamEvent => Ok(Event::default().data(String::from_utf8_lossy(&msg))),
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
}
