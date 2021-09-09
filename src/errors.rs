use derive_more::Display;
use hyper::{Body, Response, StatusCode};
use routerify::RouteError;

#[derive(Debug, Display, derive_more::Error)]
pub(crate) enum ServiceError {
    #[display(fmt = "inference timeout")]
    Timeout,

    #[display(fmt = "bad request")]
    BadRequestError,

    #[display(fmt = "bad request: validation error")]
    ValidationError,

    #[display(fmt = "inference internal error")]
    InternalError,

    #[display(fmt = "too many request: channel is full")]
    TooManyRequests,

    #[display(fmt = "cannot accept new request during the graceful shutdown")]
    GracefulShutdown,

    #[display(fmt = "mosec unknown error")]
    UnknownError,
}

pub(crate) async fn error_handler(err: RouteError) -> Response<Body> {
    let mosec_err = err.downcast::<ServiceError>().unwrap();
    let status = match mosec_err.as_ref() {
        ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
        ServiceError::BadRequestError => StatusCode::BAD_REQUEST,
        ServiceError::TooManyRequests => StatusCode::TOO_MANY_REQUESTS,
        ServiceError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        ServiceError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        ServiceError::GracefulShutdown => StatusCode::SERVICE_UNAVAILABLE,
        ServiceError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };

    Response::builder()
        .status(status)
        .body(Body::from(mosec_err.to_string()))
        .unwrap()
}
