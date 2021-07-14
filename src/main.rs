mod errors;
mod protocol;

use actix_web::{get, middleware, post, web, App, HttpResponse, HttpServer, Responder};
use errors::MosecError;
use protocol::{Protocol, TaskCode};
use tokio::{sync::oneshot, time::timeout};

use std::{time::Duration, vec};

const VERSION: &'static str = env!("CARGO_PKG_VERSION");

#[get("/")]
async fn index() -> impl Responder {
    HttpResponse::Ok().body("MOSEC service")
}

#[get("/metrics")]
async fn metrics() -> impl Responder {
    HttpResponse::Ok().body("TODO: metrics")
}

#[post("/inference")]
async fn inference(
    req: web::Bytes,
    protocol: web::Data<Protocol>,
) -> Result<HttpResponse, MosecError> {
    let (tx, rx) = oneshot::channel();
    let task_id = protocol.add_new_task(req, tx).await;
    if let Err(_) = timeout(Duration::from_millis(3000), rx).await {
        return Err(MosecError::Timeout);
    }

    let task_info = protocol.get_task_info(task_id).await;
    match task_info.code {
        TaskCode::Normal => Ok(HttpResponse::Ok().body(task_info.data.clone())),
        TaskCode::ValidationError => Err(MosecError::ValidationError),
        TaskCode::InternalError => Err(MosecError::InternalError),
        TaskCode::UnknownError => Err(MosecError::UnknownError),
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let p = Protocol::new(
        vec![1, 8, 1],
        "/tmp/mosec",
        1024,
        Duration::from_millis(3000),
    );
    HttpServer::new(move || {
        App::new()
            .app_data(p.clone())
            .wrap(
                middleware::DefaultHeaders::new()
                    .header("Server", format!("{} v{}", "MOSEC", VERSION)),
            )
            .wrap(middleware::Logger::default())
            .service(index)
            .service(metrics)
            .service(inference)
    })
    .bind("0.0.0.0:8000")?
    .run()
    .await
}
