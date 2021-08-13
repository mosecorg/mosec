use std::{net::SocketAddr, path::PathBuf, sync::Arc, thread, time::Duration};

use hyper::{body::to_bytes, Body, Request, Response, Server};
use mosec::errors::{error_handler, WebError};
use mosec::server::{self, MServer};
use routerify::{prelude::*, Router, RouterService};

async fn index(_: Request<Body>) -> Result<Response<Body>, WebError> {
    Ok(Response::new(Body::from("MOSEC service")))
}

async fn metrics(_: Request<Body>) -> Result<Response<Body>, WebError> {
    Ok(Response::new(Body::from("TODO: metrics")))
}

async fn inference(req: Request<Body>) -> Result<Response<Body>, WebError> {
    let mosec_server = req.data::<Arc<MServer>>().unwrap().clone();

    let req_data = to_bytes(req.into_body()).await.unwrap();

    if req_data.is_empty() {
        return Ok(Response::new(Body::from("No data provided")));
    }

    let (result, cancel) = mosec_server.submit(req_data).unwrap();
    println!("{:?}", mosec_server.task_pool);
    match result.recv_timeout(mosec_server.service_timeout) {
        Ok(id) => match mosec_server.retrieve(id) {
            Ok(resp_data) => Ok(Response::new(Body::from(resp_data))),
            Err(_) => Err(WebError::UnknownError), // TODO more detailed error
        },
        Err(_) => {
            cancel.send(()).unwrap();
            Err(WebError::Timeout)
        }
    }
}

#[tokio::main]
async fn main() {
    let mosec_server = server::MServer::new(
        vec![2, 1],
        Duration::from_millis(50),
        Duration::from_millis(10),
        PathBuf::from("/tmp/mosec"),
        vec![1, 2],
        1024,
        Duration::from_secs(3),
    );
    server::run(&mosec_server);

    let state_router = Router::builder()
        .data(Arc::clone(&mosec_server))
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
