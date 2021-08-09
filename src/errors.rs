use derive_more::{Display, Error};
use hyper::{Body, Response, StatusCode};
use routerify::RouteError;

#[derive(Debug, Display, Error)]
pub enum WebError {
    #[display(fmt = "inference timeout")]
    Timeout,

    #[display(fmt = "bad request: validation error")]
    ValidationError,

    #[display(fmt = "inference internal error")]
    InternalError,

    #[display(fmt = "mosec unknown error")]
    UnknownError,
}

#[derive(Debug, Display, Error, Clone, Copy)]
pub enum MosecError {
    #[display(fmt = "task not found in task pool")]
    TaskNotFoundError,

    #[display(fmt = "task already exists in task pool")]
    TaskAlreadyExistsError,
}

pub async fn error_handler(err: RouteError) -> Response<Body> {
    let web_err = err.downcast::<WebError>().unwrap();
    let status = match web_err.as_ref() {
        WebError::Timeout => StatusCode::REQUEST_TIMEOUT,
        WebError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
        WebError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
        WebError::UnknownError => StatusCode::NOT_IMPLEMENTED,
    };

    Response::builder()
        .status(status)
        .body(Body::from(web_err.to_string()))
        .unwrap()
}
