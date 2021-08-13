use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use crossbeam_channel::{bounded, Receiver, Sender};

use crate::errors;

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
    pub complete: Sender<usize>,
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
        status: TaskStatusCode,
        complete: Sender<usize>,
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
                status,
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
) -> Result<(usize, Receiver<usize>), errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    let (final_tx, result_rx) = bounded(1);
    match tp.put(0, data, TaskStatusCode::UnknownError, final_tx, cancel) {
        Ok(id) => Ok((id, result_rx)),
        Err(error) => Err(error),
    }
}

pub fn update_task(
    tp: &Arc<Mutex<TaskPool>>,
    tid: usize,
    data: Bytes,
    status: TaskStatusCode,
    complete: Sender<usize>,
    cancel: Receiver<()>,
) -> Result<usize, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.put(tid, data, status, complete, cancel)
}

pub fn get_task(tp: &Arc<Mutex<TaskPool>>, id: usize) -> Result<Task, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.get(id)
}
