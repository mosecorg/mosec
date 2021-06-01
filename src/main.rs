use actix_web::{get, middleware, post, App, HttpResponse, HttpServer, Responder};

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
async fn inference(req: String) -> impl Responder {
    HttpResponse::Ok().body(req)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
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
