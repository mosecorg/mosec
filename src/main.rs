mod errors;
mod protocol;

use std::{net::SocketAddr, time::Duration, vec};

use errors::{error_handler, MosecError};
use hyper::{body::to_bytes, Body, Request, Response, Server};
use protocol::{Protocol, TaskCode};
use routerify::prelude::*;
use routerify::{Router, RouterService};
use tokio::{sync::oneshot, time::timeout};

async fn index(_: Request<Body>) -> Result<Response<Body>, MosecError> {
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, MosecError> {
    Ok(Response::new(Body::from("TODO: metrics")))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, MosecError> {
    let protocol = req.data::<Protocol>().unwrap().clone();
    let (tx, rx) = oneshot::channel();
    let data = to_bytes(req.into_body()).await.unwrap();

    if data.is_empty() {
        return Ok(Response::new(Body::from("No data provided")));
    }

    let task_id = protocol.add_new_task(data, tx).await;
    if let Err(_) = timeout(protocol.timeout, rx).await {
        return Err(MosecError::Timeout);
    }

    let task_info = protocol.get_task_info(task_id).await;
    match task_info.code {
        TaskCode::Normal => Ok(Response::new(Body::from(task_info.data.clone()))),
        TaskCode::ValidationError => Err(MosecError::ValidationError),
        TaskCode::InternalError => Err(MosecError::InternalError),
        TaskCode::UnknownError => Err(MosecError::UnknownError),
    }
}

#[tokio::main]
async fn main() {
    let protocol = Protocol::new(
        vec![1, 8, 1],
        "/tmp/mosec",
        1024,
        Duration::from_millis(3000),
    );
    let mut protocol_runner = protocol.clone();
    tokio::spawn(async move {
        protocol_runner.run().await;
    });
    let state_router = Router::builder()
        .data(protocol.clone())
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
        eprintln!("Server error: {}", err);
    }
}
