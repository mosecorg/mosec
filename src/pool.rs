use crate::errors;
use bytes::Bytes;
use crossbeam_channel::{bounded, Receiver, Sender};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Copy)]
pub enum TaskStatusCode {
    Normal,
    ValidationError,
    InternalError,
    UnknownError,
}

#[derive(Debug, Clone)]
pub struct Task {
    // task info
    pub status: TaskStatusCode,
    pub data: Bytes,

    // notifiers
    pub complete: Sender<()>,
    pub cancel: Receiver<()>,
}

#[derive(Debug)]
pub struct TaskPool {
    tasks: HashMap<usize, Task>,
    total_count: usize,
}

impl TaskPool {
    pub fn new() -> Arc<Mutex<Self>> {
        let map: HashMap<usize, Task> = HashMap::new();
        Arc::new(Mutex::new(TaskPool {
            tasks: map,
            total_count: 1,
        }))
    }
    fn put(
        &mut self,
        tid: usize,
        data: Bytes,
        complete: Sender<()>,
        cancel: Receiver<()>,
    ) -> Result<usize, errors::MosecError> {
        let mut id = tid;
        if tid == 0 {
            // initialize a task, or otherwise reuse the task id
            id = self.total_count;
            self.total_count = self.total_count.wrapping_add(1);
            if self.total_count == 0 {
                self.total_count += 1;
            }
        }
        match self.tasks.insert(
            id,
            Task {
                status: TaskStatusCode::UnknownError,
                data,
                complete,
                cancel,
            },
        ) {
            None => Ok(id),
            Some(_) => Err(errors::MosecError::TaskAlreadyExistsError),
        }
    }
    fn get(&mut self, id: usize) -> Result<Task, errors::MosecError> {
        match self.tasks.remove(&id) {
            Some(task) => Ok(task),
            None => Err(errors::MosecError::TaskNotFoundError),
        }
    }
}

pub fn init_task(
    tp: &Arc<Mutex<TaskPool>>,
    data: Bytes,
    cancel: Receiver<()>,
) -> (Result<usize, errors::MosecError>, Receiver<()>) {
    let mut tp = tp.lock().unwrap();
    let (final_tx, result_rx) = bounded(1);
    (tp.put(0, data, final_tx, cancel), result_rx)
}

pub fn update_task(
    tp: &Arc<Mutex<TaskPool>>,
    tid: usize,
    data: Bytes,
    complete: Sender<()>,
    cancel: Receiver<()>,
) -> Result<usize, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.put(tid, data, complete, cancel)
}

pub fn get_task(tp: &Arc<Mutex<TaskPool>>, id: usize) -> Result<Task, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.get(id)
}
