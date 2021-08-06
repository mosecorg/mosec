use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};
use std::usize;

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
    tasks: Arc<Mutex<TaskHub>>,
    batch_size: u32,
    listener: UnixListener,
    receiver: Receiver<usize>,
    sender: Sender<usize>,
}

impl Processor {
    fn new(
        tasks: Arc<Mutex<TaskHub>>,
        batch_size: u32,
        path: &PathBuf,
        receiver: Receiver<usize>,
        sender: Sender<usize>,
    ) -> Self {
        println!("listen on {:?}", path);
        let listener = UnixListener::bind(path).unwrap();
        Processor {
            tasks,
            batch_size,
            listener,
            receiver,
            sender,
        }
    }

    async fn run(&self) {
        loop {
            let tasks_clone = self.tasks.clone();
            let input_clone = self.receiver.clone();
            let output_clone = self.sender.clone();
            match self.listener.accept().await {
                Ok((stream, addr)) => {
                    println!("Accepted connection from {:?}", addr);
                    tokio::spawn(async move {
                        loop {
                            let task_id = input_clone.recv().await;
                            match task_id {
                                Ok(task_id) => {
                                    let tasks = tasks_clone.lock().await;
                                    let task = tasks.table.get(&task_id);
                                }
                                Err(_) => {
                                    break;
                                }
                            }
                        }
                    });
                }
                Err(e) => {
                    eprintln!("Error accepting connection: {:?}", e);
                    break;
                }
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
    capacity: usize,
    batches: Vec<u32>,
    path: String,
    sender: Sender<usize>,
    receiver: Receiver<usize>,
    pub timeout: Duration,
    tasks: Arc<Mutex<TaskHub>>,
}

impl Protocol {
    pub fn new<'a>(batches: Vec<u32>, unix_dir: &str, capacity: usize, timeout: Duration) -> Self {
        let (sender, receiver) = bounded::<usize>(capacity);
        Protocol {
            capacity,
            batches,
            path: unix_dir.to_string(),
            sender,
            receiver,
            timeout,
            tasks: Arc::new(Mutex::new(TaskHub {
                table: HashMap::with_capacity(capacity),
                current_id: 0,
            })),
        }
    }

    pub async fn run(&mut self) {
        let mut last_receiver = self.receiver.clone();
        let folder = Path::new(&self.path);
        if !folder.is_dir() {
            fs::create_dir(folder).unwrap();
        }

        for (i, batch) in self.batches.iter().enumerate() {
            let (sender, receiver) = bounded::<usize>(self.capacity);
            let processor = Processor::new(
                self.tasks.clone(),
                *batch,
                &folder.join(format!("ipc_{:?}.socket", i)),
                last_receiver.clone(),
                sender.clone(),
            );
            tokio::spawn(async move {
                processor.run().await;
            });
            last_receiver = receiver.clone();
        }
        self.receiver = last_receiver.clone();
    }

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
