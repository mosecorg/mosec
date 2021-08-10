use derive_more::Display;
use hyper::{Body, Response, StatusCode};
use routerify::RouteError;

#[derive(Debug, Display, derive_more::Error)]
pub enum ServiceError {
    #[display(fmt = "inference timeout")]
    Timeout,

    #[display(fmt = "bad request")]
    BadRequestError,

    #[display(fmt = "bad request: validation error")]
    ValidationError,

    #[display(fmt = "inference internal error")]
    InternalError,

    #[display(fmt = "mosec unknown error")]
    UnknownError,
}

pub async fn error_handler(err: RouteError) -> Response<Body> {
    let mosec_err = err.downcast::<ServiceError>().unwrap();
    let status = match mosec_err.as_ref() {
        ServiceError::Timeout => StatusCode::REQUEST_TIMEOUT,
        ServiceError::BadRequestError => StatusCode::BAD_REQUEST,
        ServiceError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        ServiceError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        ServiceError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };

    Response::builder()
        .status(status)
        .body(Body::from(mosec_err.to_string()))
        .unwrap()
}

#[derive(Debug)]
pub enum ProtocolError {
    SocketClosed,
    ReadIncomplete,
    ReadError,
    ReceiveError,
    WriteIncomplete,
    WriteError,
    SendError,
}
