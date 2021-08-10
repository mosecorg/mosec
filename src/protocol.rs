use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};
use std::usize;
use std::{fs, u32};

use async_channel::{bounded, Receiver, Sender};
use bytes::Bytes;
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::{oneshot, Mutex};

use crate::errors::ProtocolError;

const FLAG_U8_SIZE: usize = 2;
const NUM_U8_SIZE: usize = 2;
const TASK_ID_U8_SIZE: usize = 4;
const LENGTH_U8_SIZE: usize = 4;

const BIT_STATUS_OK: u16 = 0b1;
const BIT_STATUS_BAD_REQ: u16 = 0b10;
const BIT_STATUS_VALIDATION_ERR: u16 = 0b100;
const BIT_STATUS_INTERNAL_ERR: u16 = 0b1000;

#[derive(Debug, Clone, Copy)]
pub enum TaskCode {
    UnknownError,
    Normal,
    BadRequestError,
    ValidationError,
    InternalError,
}

#[derive(Debug, Clone)]
pub struct Task {
    pub code: TaskCode,
    pub data: Bytes,
    create_at: Instant,
}

impl Task {
    pub fn new(data: Bytes) -> Self {
        Task {
            code: TaskCode::UnknownError,
            data,
            create_at: Instant::now(),
        }
    }

    pub fn update(&mut self, code: TaskCode, data: &Bytes) {
        self.code = code;
        self.data = data.clone();
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
        path: &Path,
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
                            if receive(&stream, &tasks_clone).await.is_err() {
                                break;
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
struct Message {
    code: TaskCode,
    ids: Vec<u32>,
    data: Vec<Bytes>,
}

async fn read_exact(stream: &UnixStream, buf: &mut [u8]) -> Result<(), ProtocolError> {
    loop {
        match stream.try_read(buf) {
            Ok(0) => return Err(ProtocolError::SocketClosed),
            Ok(n) if n != buf.len() => return Err(ProtocolError::ReadIncomplete),
            Ok(_) => return Ok(()),
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => continue,
            Err(e) => {
                eprintln!("read socket err: {}", &e);
                return Err(ProtocolError::ReadError);
            }
        }
    }
}

async fn receive(
    stream: &UnixStream,
    tasks: &Arc<tokio::sync::Mutex<TaskHub>>,
) -> Result<(), ProtocolError> {
    stream.readable().await.unwrap();
    let mut flag_buf = [0u8; FLAG_U8_SIZE];
    let mut num_buf = [0u8; NUM_U8_SIZE];
    read_exact(stream, &mut flag_buf).await?;
    read_exact(stream, &mut num_buf).await?;
    let flag = u16::from_be_bytes(flag_buf);
    let num = u16::from_be_bytes(num_buf);

    let code = if flag & BIT_STATUS_OK > 0 {
        TaskCode::Normal
    } else if flag & BIT_STATUS_BAD_REQ > 0 {
        TaskCode::BadRequestError
    } else if flag & BIT_STATUS_VALIDATION_ERR > 0 {
        TaskCode::ValidationError
    } else if flag & BIT_STATUS_INTERNAL_ERR > 0 {
        TaskCode::InternalError
    } else {
        TaskCode::UnknownError
    };

    let mut id_buf = [0u8; TASK_ID_U8_SIZE];
    let mut length_buf = [0u8; LENGTH_U8_SIZE];
    let mut ids: Vec<u32> = Vec::new();
    let mut data: Vec<Bytes> = Vec::new();
    for _ in 0..num {
        read_exact(stream, &mut id_buf).await?;
        read_exact(stream, &mut length_buf).await?;
        let id = u32::from_be_bytes(id_buf);
        let length = u32::from_be_bytes(length_buf);
        let mut data_buf = vec![0u8; length as usize];
        read_exact(stream, &mut data_buf).await?;
        ids.push(id);
        data.push(data_buf.into());
    }

    {
        let mut tasks = tasks.lock().await;
        tasks.update_from_message(code, ids, data);
    }
    Ok(())
}

#[derive(Debug)]
struct TaskHub {
    table: HashMap<u32, Task>,
    notifiers: HashMap<u32, oneshot::Sender<()>>,
    current_id: u32,
}

impl TaskHub {
    pub fn update_from_message(&mut self, code: TaskCode, ids: Vec<u32>, data: Vec<Bytes>) {
        for i in 0..ids.len() {
            let task = self.table.get_mut(&ids[i]);
            match task {
                Some(task) => {
                    task.update(code, &data[i]);
                    match code {
                        TaskCode::Normal => {}
                        _ => {
                            if let Some(s) = self.notifiers.remove(&ids[i]) {
                                s.send(()).unwrap();
                            } else {
                                eprintln!("no notifier for task {}", &ids[i]);
                            }
                        }
                    }
                }
                None => {
                    eprintln!("cannot find id: {}", ids[i]);
                }
            }
        }
    }
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
    pub fn new(batches: Vec<u32>, unix_dir: &str, capacity: usize, timeout: Duration) -> Self {
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
                notifiers: HashMap::with_capacity(capacity),
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
        self.receiver = last_receiver;
    }

    pub async fn add_new_task(&self, data: Bytes, notifier: oneshot::Sender<()>) -> u32 {
        let mut tasks = self.tasks.lock().await;
        let id = tasks.current_id;
        tasks.table.insert(id, Task::new(data));
        tasks.notifiers.insert(id, notifier);
        let _ = tasks.current_id.wrapping_add(1);
        id
    }

    pub async fn get_task(&self, id: u32) -> Option<Task> {
        let mut tasks = self.tasks.lock().await;
        tasks.table.remove(&id)
    }
}
