use std::collections::HashMap;
use std::time::{Duration, Instant};

use bytes::Bytes;
use once_cell::sync::OnceCell;
use parking_lot::{Mutex, RwLock};
use tokio::io;
use tokio::sync::oneshot;
use tokio::time::timeout;
use tracing::{debug, error};

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
    senders: Mutex<HashMap<u32, oneshot::Sender<()>>>,
    receivers: Mutex<HashMap<u32, oneshot::Receiver<()>>>,
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
            senders: Mutex::new(HashMap::new()),
            receivers: Mutex::new(HashMap::new()),
            timeout,
            current_id: Mutex::new(0),
            channel,
        }
    }

    pub(crate) async fn add_new_task(&self, data: Bytes) -> Result<u32, io::Error> {
        let mut current_id = self.current_id.lock();
        let id = *current_id;
        let (tx, rx) = oneshot::channel();
        let mut table = self.table.write();
        let mut senders = self.senders.lock();
        let mut receivers = self.receivers.lock();
        table.insert(id, Task::new(data));
        senders.insert(id, tx);
        receivers.insert(id, rx);
        *current_id = id.wrapping_add(1);
        debug!(%id, "add a new task");

        if self.channel.try_send(id).is_err() {
            error!(%id, "the first channel is full, delete this task");
            table.remove(&id);
            senders.remove(&id);
            receivers.remove(&id);
            return Err(io::Error::new(
                io::ErrorKind::WouldBlock,
                "the first channel is full",
            ));
        }
        Ok(id)
    }

    pub(crate) async fn wait_task_done(&self, id: u32) -> Result<(), io::Error> {
        let rx: oneshot::Receiver<()>;
        {
            let mut receivers = self.receivers.lock();
            match receivers.remove(&id) {
                Some(r) => rx = r,
                None => {
                    error!(%id, "task not found in the oneshot receivers");
                    return Err(io::Error::new(
                        io::ErrorKind::NotFound,
                        "cannot find this id",
                    ));
                }
            }
        }
        if let Err(err) = timeout(self.timeout, rx).await {
            error!(%id, %err, "task timeout");
            return Err(io::Error::new(io::ErrorKind::TimedOut, "task timeout"));
        }
        Ok(())
    }

    pub(crate) fn pop_task(&self, id: u32) -> Option<Task> {
        let mut table = self.table.write();
        table.remove(&id)
    }

    pub(crate) fn notify_task_done(&self, id: u32) {
        let mut senders = self.senders.lock();
        if let Some(sender) = senders.remove(&id) {
            if !sender.is_closed() {
                sender.send(()).unwrap();
            }
        } else {
            error!(%id, "cannot find the oneshot sender");
        }
    }

    pub(crate) fn get_multi_tasks_data(&self, ids: &[u32]) -> Vec<Bytes> {
        let mut data: Vec<Bytes> = Vec::with_capacity(ids.len());
        let table = self.table.read();
        for id in ids {
            if let Some(task) = table.get(id) {
                data.push(task.data.clone());
            }
        }
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
                    error!(id=%ids[i], "cannot find id");
                }
            }
        }
    }
}
