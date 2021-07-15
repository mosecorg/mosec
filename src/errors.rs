use derive_more::{Display, Error};
use hyper::{Body, Response, StatusCode};
use routerify::RouteError;

#[derive(Debug, Display, Error)]
pub enum MosecError {
    #[display(fmt = "inference timeout")]
    Timeout,

    #[display(fmt = "bad request: validation error")]
    ValidationError,

    #[display(fmt = "inference internal error")]
    InternalError,

    #[display(fmt = "mosec unknown error")]
    UnknownError,
}

pub async fn error_handler(err: RouteError) -> Response<Body> {
    let mosec_err = err.downcast::<MosecError>().unwrap();
    let status = match mosec_err.as_ref() {
        MosecError::Timeout => StatusCode::REQUEST_TIMEOUT,
        MosecError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        MosecError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        MosecError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };

    Response::builder()
        .status(status)
        .body(Body::from(mosec_err.to_string()))
        .unwrap()
}
