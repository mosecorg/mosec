use std::path::PathBuf;
use std::time::Duration;
use std::usize;

use async_channel::{Receiver, Sender};
use bytes::{BufMut, Bytes, BytesMut};
use tokio::io::{self, AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tracing::{debug, error, info};

use crate::tasks::{TaskCode, TaskManager};

const FLAG_U8_SIZE: usize = 2;
const NUM_U8_SIZE: usize = 2;
const TASK_ID_U8_SIZE: usize = 4;
const LENGTH_U8_SIZE: usize = 4;

const BIT_STATUS_OK: u16 = 0b1;
const BIT_STATUS_BAD_REQ: u16 = 0b10;
const BIT_STATUS_VALIDATION_ERR: u16 = 0b100;
const BIT_STATUS_INTERNAL_ERR: u16 = 0b1000;

pub(crate) async fn communicate(
    path: PathBuf,
    batch_size: u32,
    wait_time: Duration,
    receiver: Receiver<u32>,
    sender: Sender<u32>,
) {
    let listener = UnixListener::bind(&path).expect(&path.to_string_lossy());
    loop {
        let sender_clone = sender.clone();
        let receiver_clone = receiver.clone();
        match listener.accept().await {
            Ok((mut stream, addr)) => {
                info!(?addr, "accepted connection from");
                tokio::spawn(async move {
                    loop {
                        if let Err(err) =
                            send_message(&mut stream, &receiver_clone, batch_size, wait_time).await
                        {
                            error!(%err, "send message error");
                            break;
                        }
                        if let Err(err) = receive_message(&mut stream, &sender_clone).await {
                            error!(%err, "receive message error");
                            break;
                        }
                    }
                });
            }
            Err(err) => {
                error!(error=%err, "Error accepting connection");
                break;
            }
        }
    }
}

async fn receive_message(stream: &mut UnixStream, sender: &Sender<u32>) -> Result<(), io::Error> {
    stream.readable().await?;
    let mut flag_buf = [0u8; FLAG_U8_SIZE];
    let mut num_buf = [0u8; NUM_U8_SIZE];
    stream.read_exact(&mut flag_buf).await?;
    stream.read_exact(&mut num_buf).await?;
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
        stream.read_exact(&mut id_buf).await?;
        stream.read_exact(&mut length_buf).await?;
        let id = u32::from_be_bytes(id_buf);
        let length = u32::from_be_bytes(length_buf);
        let mut data_buf = vec![0u8; length as usize];
        stream.read_exact(&mut data_buf).await?;
        ids.push(id);
        data.push(data_buf.into());
    }
    debug!(?ids, ?code, ?num, ?flag, "received tasks from the stream");

    // update tasks received from the stream
    let task_manager = TaskManager::global();
    task_manager.update_multi_tasks(code, &ids, &data);

    // send normal tasks to the next channel
    match code {
        TaskCode::Normal => {
            for id in ids {
                sender.send(id).await.expect("next channel is closed");
            }
        }
        _ => {
            info!(?ids, "abnormal tasks");
        }
    }
    Ok(())
}

async fn get_batch(receiver: &Receiver<u32>, batch_size: usize, batch_vec: &mut Vec<u32>) {
    loop {
        match receiver.recv().await {
            Ok(id) => {
                batch_vec.push(id);
            }
            Err(err) => {
                error!(%err, "receive from channel error");
            }
        }
        if batch_vec.len() == batch_size {
            break;
        }
    }
    info!(batch_size=?batch_vec.len(), "received batch size from channel");
}

async fn send_message(
    stream: &mut UnixStream,
    receiver: &Receiver<u32>,
    batch_size: u32,
    wait_time: Duration,
) -> Result<(), io::Error> {
    // get batch from the channel
    let mut batch: Vec<u32> = Vec::new();

    let id = receiver.recv().await.expect("receiver is closed");
    batch.push(id);
    if batch_size > 1 {
        // timing from receiving the first item
        if tokio::time::timeout(
            wait_time,
            get_batch(receiver, batch_size as usize, &mut batch),
        )
        .await
        .is_err()
        {
            info!(
                "timeout before the batch is full: {}/{}",
                batch.len(),
                batch_size
            );
        }
    }

    // send the batch tasks to the stream
    let task_manager = TaskManager::global();
    let data = task_manager.get_multi_tasks_data(&batch);
    if data.len() != batch.len() {
        error!(
            "cannot get all the data from table: {}/{}",
            data.len(),
            batch.len()
        );
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "incomplete data",
        ));
    }

    stream.writable().await?;
    let mut buffer = BytesMut::new();
    buffer.put_u16(0); // flag
    buffer.put_u16(batch.len() as u16);
    for i in 0..batch.len() {
        buffer.put_u32(batch[i]);
        buffer.put_u32(data[i].len() as u32);
        buffer.put(data[i].clone());
    }
    stream.write_all(&buffer).await?;
    debug!(batch_size=%batch.len(), byte_size=%buffer.len(), "send data to the stream");

    Ok(())
}

// #[derive(Debug, Clone)]
// pub(crate) struct Protocol {
//     capacity: usize,
//     path: String,
//     batches: Vec<u32>,
//     sender: Sender<u32>,
//     receiver: Receiver<u32>,
//     wait_time: Duration,
//     pub(crate) timeout: Duration,
// }

// impl Protocol {
// pub(crate) fn new(
//     batches: Vec<u32>,
//     unix_dir: &str,
//     capacity: usize,
//     timeout: Duration,
//     wait_time: Duration,
// ) -> Self {
//     let (sender, receiver) = bounded::<u32>(capacity);
//     Protocol {
//         capacity,
//         path: unix_dir.to_string(),
//         batches,
//         sender,
//         receiver,
//         tasks: Arc::new(Mutex::new(TaskManager {
//             table: HashMap::with_capacity(capacity),
//             notifiers: HashMap::with_capacity(capacity),
//             current_id: 0,
//         })),
//         timeout,
//         wait_time,
//     }
// }

// pub(crate) async fn run(&mut self) {
//     let mut last_receiver = self.receiver.clone();
//     let wait_time = self.wait_time;
//     let folder = Path::new(&self.path);
//     if folder.is_dir() {
//         info!(path=?folder, "path already exist, try to remove it");
//         fs::remove_dir_all(folder).unwrap();
//     }
//     fs::create_dir(folder).unwrap();

//     for (i, batch) in self.batches.iter().enumerate() {
//         let (sender, receiver) = bounded::<u32>(self.capacity);
//         let path = folder.join(format!("ipc_{:?}.socket", i));
//         let tasks_clone = self.tasks.clone();

//         let batch_size = *batch;
//         tokio::spawn(communicate(
//             path,
//             tasks_clone,
//             batch_size,
//             wait_time,
//             last_receiver.clone(),
//             sender.clone(),
//         ));
//         last_receiver = receiver.clone();
//     }
//     let tasks_clone = self.tasks.clone();
//     self.receiver = last_receiver;
//     let receiver_clone = self.receiver.clone();
//     tokio::spawn(finish_task(receiver_clone, tasks_clone));
// }

// pub async fn add_new_task(
//     &self,
//     data: Bytes,
//     notifier: oneshot::Sender<()>,
// ) -> Result<u32, io::Error> {
//     let mut tasks = self.tasks.lock().await;
//     let id = tasks.current_id;
//     tasks.table.insert(id, Task::new(data));
//     tasks.notifiers.insert(id, notifier);
//     tasks.current_id = tasks.current_id.wrapping_add(1);
//     debug!(%id, "add a new task");
//     if self.sender.try_send(id).is_err() {
//         error!(%id, "the first channel is full, delete this task");
//         tasks.table.remove(&id);
//         tasks.notifiers.remove(&id);
//         return Err(io::Error::new(
//             io::ErrorKind::WouldBlock,
//             "the first channel is full",
//         ));
//     }
//     Ok(id)
// }

// pub(crate) async fn get_task(&self, id: u32) -> Option<Task> {
//     let mut tasks = self.tasks.lock().await;
//     debug!(%id, "remove task from table");
//     tasks.table.remove(&id)
// }
// }
