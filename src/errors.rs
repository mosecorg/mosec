use derive_more::{Display, Error};

#[derive(Debug, Display, Error)]
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

#[derive(Debug, Display, Error, Clone, Copy)]
pub enum MosecError {
    #[display(fmt = "task not found in task pool")]
    TaskNotFoundError,

    #[display(fmt = "task already exists in task pool")]
    TaskAlreadyExistsError,

    #[display(fmt = "broken pipe between threads")]
    BrokenPipeError,
}

#[derive(Debug)]
pub enum ProtocolError {
    ReadError,
    ReceiveError,
    WriteError,
    SendError,
}
