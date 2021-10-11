use derive_more::Display;

#[derive(Debug, Display, derive_more::Error)]
pub(crate) enum ServiceError {
    #[display(fmt = "inference timeout")]
    Timeout,

    #[display(fmt = "too many request: task queue is full")]
    TooManyRequests,

    #[display(fmt = "mosec unknown error")]
    UnknownError,
}
