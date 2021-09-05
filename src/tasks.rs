use std::collections::HashMap;
use std::time::{Duration, Instant};

use bytes::Bytes;
use once_cell::sync::OnceCell;
use parking_lot::{Mutex, RwLock};
use tokio::sync::oneshot;
use tokio::time::timeout;
use tracing::{debug, error, info};

use crate::errors::ServiceError;

#[derive(Debug, Clone, Copy)]
pub(crate) enum TaskCode {
    UnknownError,
    Normal,
    BadRequestError,
    ValidationError,
    InternalError,
}

#[derive(Debug, Clone)]
pub(crate) struct Task {
    pub(crate) code: TaskCode,
    pub(crate) data: Bytes,
    create_at: Instant,
}

impl Task {
    pub(crate) fn new(data: Bytes) -> Self {
        Self {
            code: TaskCode::UnknownError,
            data,
            create_at: Instant::now(),
        }
    }

    pub(crate) fn update(&mut self, code: TaskCode, data: &Bytes) {
        self.code = code;
        self.data = data.clone();
    }
}

#[derive(Debug)]
pub(crate) struct TaskManager {
    table: RwLock<HashMap<u32, Task>>,
    notifiers: Mutex<HashMap<u32, oneshot::Sender<()>>>,
    timeout: Duration,
    current_id: Mutex<u32>,
    channel: async_channel::Sender<u32>,
}

pub(crate) static TASK_MANAGER: OnceCell<TaskManager> = OnceCell::new();

impl TaskManager {
    pub fn global() -> &'static TaskManager {
        TASK_MANAGER.get().expect("task manager is not initialized")
    }

    pub fn new(timeout: Duration, channel: async_channel::Sender<u32>) -> Self {
        Self {
            table: RwLock::new(HashMap::new()),
            notifiers: Mutex::new(HashMap::new()),
            timeout,
            current_id: Mutex::new(0),
            channel,
        }
    }

    pub(crate) async fn submit_task(&self, data: Bytes) -> Result<Task, ServiceError> {
        let (id, rx) = self.add_new_task(data).await?;
        if let Err(err) = timeout(self.timeout, rx).await {
            error!(%id, %err, "task timeout");
            let mut table = self.table.write();
            let mut notifiers = self.notifiers.lock();
            table.remove(&id);
            notifiers.remove(&id);
            return Err(ServiceError::Timeout);
        }
        let mut table = self.table.write();
        match table.remove(&id) {
            Some(task) => Ok(task),
            None => {
                error!(%id, "cannot find the task when trying to remove it");
                Err(ServiceError::UnknownError)
            }
        }
    }

    pub(crate) async fn add_new_task(
        &self,
        data: Bytes,
    ) -> Result<(u32, oneshot::Receiver<()>), ServiceError> {
        let mut current_id = self.current_id.lock();
        let id = *current_id;
        let (tx, rx) = oneshot::channel();
        let mut table = self.table.write();
        let mut notifiers = self.notifiers.lock();
        table.insert(id, Task::new(data));
        notifiers.insert(id, tx);
        *current_id = id.wrapping_add(1);
        debug!(%id, "add a new task");

        if self.channel.try_send(id).is_err() {
            error!(%id, "the first channel is full, delete this task");
            table.remove(&id);
            notifiers.remove(&id);
            return Err(ServiceError::TooManyRequests);
        }
        Ok((id, rx))
    }

    pub(crate) fn notify_task_done(&self, id: u32) {
        let mut notifiers = self.notifiers.lock();
        if let Some(sender) = notifiers.remove(&id) {
            if !sender.is_closed() {
                sender.send(()).unwrap();
            }
        } else {
            // if the task is already timeout, the notifier may be removed by another thread
            info!(%id, "cannot find the oneshot notifier");
        }
    }

    pub(crate) fn get_multi_tasks_data(&self, ids: &mut Vec<u32>) -> Vec<Bytes> {
        let mut data: Vec<Bytes> = Vec::with_capacity(ids.len());
        let table = self.table.read();
        // delete the task_id if the task_id doesn't exist in the table
        ids.retain(|&id| match table.get(&id) {
            Some(task) => {
                data.push(task.data.clone());
                true
            }
            None => false,
        });
        data
    }

    pub(crate) fn update_multi_tasks(&self, code: TaskCode, ids: &[u32], data: &[Bytes]) {
        let mut table = self.table.write();
        for i in 0..ids.len() {
            let task = table.get_mut(&ids[i]);
            match task {
                Some(task) => {
                    task.update(code, &data[i]);
                    match code {
                        TaskCode::Normal => {}
                        _ => {
                            self.notify_task_done(ids[i]);
                        }
                    }
                }
                None => {
                    // if the task is already timeout, it may be removed by another thread
                    info!(id=%ids[i], "cannot find task id in the table");
                }
            }
        }
    }
}
