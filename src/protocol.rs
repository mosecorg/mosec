use actix_web::web::Bytes;
use tokio::sync::oneshot;

#[derive(Debug)]
pub enum TaskCode {
    UnknownError,
    Normal,
    ValidationError,
    InternalError,
}

#[derive(Debug)]
pub struct Task {
    notifier: oneshot::Sender<bool>,
    pub data: Bytes,
    pub code: TaskCode,
}

impl Task {
    pub fn new(data: Bytes, notifier: oneshot::Sender<bool>) -> Self {
        Task {
            notifier,
            data,
            code: TaskCode::UnknownError,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Protocol {
    batches: Vec<u32>,
}

impl Protocol {
    pub fn new(batches: Vec<u32>) -> Self {
        Protocol { batches }
    }

    pub fn add_new_task(&self, task: &Task) {}
}
