use derive_more::Display;

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
