use std::{env, net::SocketAddr, path::PathBuf, sync::Arc, time::Duration};

use hyper::{body::to_bytes, Body, Request, Response, Server, StatusCode};
use mosec::{errors::ServiceError, server};
use routerify::{prelude::*, RouteError, Router, RouterService};
use tracing::error;
use tracing_subscriber::{fmt, EnvFilter};

async fn index(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, ServiceError> {
    Ok(Response::new(Body::from("TODO: metrics")))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, ServiceError> {
    let mosec_server = req.data::<Arc<server::MServer>>().unwrap().clone();

    let req_data = to_bytes(req.into_body()).await.unwrap();

    if req_data.is_empty() {
        return Ok(Response::new(Body::from("No data provided")));
    }

    let (result, cancel) = mosec_server.submit(req_data).unwrap();
    match mosec_server.retrieve(result, cancel) {
        Ok(resp_data) => Ok(Response::new(Body::from(resp_data))),
        Err(error) => {
            error!("service error: {:?}", error);
            Err(error)
        }
    }
}

async fn error_handler(err: RouteError) -> Response<Body> {
    let web_err = err.downcast::<ServiceError>().unwrap();
    let status = match web_err.as_ref() {
        ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
        ServiceError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        ServiceError::BadRequestError => StatusCode::BAD_REQUEST,
        ServiceError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        ServiceError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };

    Response::builder()
        .status(status)
        .body(Body::from(web_err.to_string()))
        .unwrap()
}

#[tokio::main]
async fn main() {
    if env::var("RUST_LOG").is_err() {
        env::set_var("RUST_LOG", "info")
    }

    fmt::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let mosec_server = server::MServer::new(
        vec![1, 8, 1],
        Duration::from_millis(50),
        Duration::from_millis(10),
        String::from("/tmp/mosec"),
        1024,
        Duration::from_secs(3),
    );
    server::run(mosec_server.clone());

    let state_router = Router::builder()
        .data(mosec_server)
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
        error!("Server error: {}", err);
    }
}
