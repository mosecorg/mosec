use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_channel::{bounded, Receiver, Sender};
use bytes::Bytes;
use tokio::net::UnixListener;
use tokio::sync::{oneshot, Mutex};

#[derive(Debug, Clone, Copy)]
pub enum TaskCode {
    UnknownError,
    Normal,
    ValidationError,
    InternalError,
}

#[derive(Debug, Clone)]
pub struct Info {
    pub code: TaskCode,
    pub data: Bytes,
}

#[derive(Debug)]
struct Task {
    info: Info,
    notifier: oneshot::Sender<()>,
    create_at: Instant,
}

impl Task {
    pub fn new(data: Bytes, notifier: oneshot::Sender<()>) -> Self {
        Task {
            notifier,
            create_at: Instant::now(),
            info: Info {
                code: TaskCode::UnknownError,
                data,
            },
        }
    }
}

#[derive(Debug)]
struct Processor {
    batch_size: u32,
    listener: UnixListener,
    receiver: Receiver<usize>,
    sender: Sender<usize>,
}

impl Processor {
    fn new(
        batch_size: u32,
        path: &PathBuf,
        receiver: Receiver<usize>,
        sender: Sender<usize>,
    ) -> Self {
        let listener = UnixListener::bind(path).unwrap();
        Processor {
            batch_size,
            listener,
            receiver,
            sender,
        }
    }

    async fn run(&self) {
        loop {
            match self.listener.accept().await {
                Ok((stream, addr)) => {}
                Err(e) => {}
            }
        }
    }
}

#[derive(Debug)]
struct TaskHub {
    table: HashMap<usize, Task>,
    current_id: usize,
}

#[derive(Debug, Clone)]
pub struct Protocol {
    pub timeout: Duration,
    tasks: Arc<Mutex<TaskHub>>,
}

impl Protocol {
    pub fn new<'a>(batches: Vec<u32>, unix_dir: &str, capacity: usize, timeout: Duration) -> Self {
        let mut senders = Vec::new();
        let mut receivers = Vec::new();
        let mut processors = Vec::new();

        let (s, r) = bounded(capacity);
        senders.push(s);
        receivers.push(r);
        for (i, batch) in batches.iter().enumerate() {
            let (s, r) = bounded(capacity);
            processors.push(Processor::new(
                *batch,
                &Path::new(unix_dir).join(i.to_string()),
                receivers.last().unwrap().clone(),
                s.clone(),
            ));
            senders.push(s);
            receivers.push(r);
        }

        Protocol {
            timeout,
            tasks: Arc::new(Mutex::new(TaskHub {
                table: HashMap::with_capacity(capacity),
                current_id: 0,
            })),
        }
    }

    pub async fn run(&self) {}

    pub async fn add_new_task(&self, data: Bytes, notifier: oneshot::Sender<()>) -> usize {
        let mut tasks = self.tasks.lock().await;
        let id = tasks.current_id;
        tasks.table.insert(id, Task::new(data, notifier));
        let _ = tasks.current_id.wrapping_add(1);
        id
    }

    pub async fn get_task_info(&self, id: usize) -> Info {
        let mut tasks = self.tasks.lock().await;
        match tasks.table.remove(&id) {
            Some(task) => task.info.clone(),
            None => Info {
                code: TaskCode::UnknownError,
                data: Bytes::from(""),
            },
        }
    }
}
