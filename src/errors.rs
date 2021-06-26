use actix_web::{
    dev::HttpResponseBuilder,
    error,
    http::{header, StatusCode},
    HttpResponse,
};
use derive_more::{Display, Error};

const TEXT_TYPE: &'static str = "text/html; charset=utf-8";

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

impl error::ResponseError for MosecError {
    fn error_response(&self) -> HttpResponse {
        HttpResponseBuilder::new(self.status_code())
            .set_header(header::CONTENT_TYPE, TEXT_TYPE)
            .body(self.to_string())
    }

    fn status_code(&self) -> StatusCode {
        match *self {
            MosecError::Timeout => StatusCode::REQUEST_TIMEOUT,
            MosecError::ValidationError => StatusCode::UNPROCESSABLE_ENTITY,
            MosecError::InternalError => StatusCode::INTERNAL_SERVER_ERROR,
            MosecError::UnknownError => StatusCode::NOT_IMPLEMENTED,
        }
    }
}
