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
    batch_size: usize,
    wait_time: Duration,
    receiver: Receiver<u32>,
    sender: Sender<u32>,
    last_sender: Sender<u32>,
) {
    let listener = UnixListener::bind(&path).expect("failed to bind to the socket");
    loop {
        let sender_clone = sender.clone();
        let last_sender_clone = last_sender.clone();
        let receiver_clone = receiver.clone();
        match listener.accept().await {
            Ok((mut stream, addr)) => {
                info!(?addr, "accepted connection from");
                tokio::spawn(async move {
                    let mut code: TaskCode = TaskCode::UnknownError;
                    let mut ids: Vec<u32> = Vec::with_capacity(batch_size);
                    let mut data: Vec<Bytes> = Vec::with_capacity(batch_size);
                    let task_manager = TaskManager::global();
                    loop {
                        ids.clear();
                        data.clear();
                        get_batch(&receiver_clone, batch_size, &mut ids, wait_time).await;
                        task_manager.get_multi_tasks_data(&mut ids, &mut data);
                        if data.is_empty() {
                            // if all the ids in this batch are timeout, the data will be empty
                            continue;
                        }
                        if let Err(err) = send_message(&mut stream, &ids, &data).await {
                            error!(%err, "send message error");
                            info!(
                                "write to stream error, try to send task_ids to the last channel"
                            );
                            for id in &ids {
                                last_sender_clone.send(*id).await.expect("sender is closed");
                            }
                            break;
                        }
                        ids.clear();
                        data.clear();
                        if let Err(err) =
                            read_message(&mut stream, &mut code, &mut ids, &mut data).await
                        {
                            error!(%err, "receive message error");
                            break;
                        }
                        task_manager.update_multi_tasks(code, &mut ids, &data);
                        match code {
                            TaskCode::Normal => {
                                for id in &ids {
                                    sender_clone
                                        .send(*id)
                                        .await
                                        .expect("next channel is closed");
                                }
                            }
                            _ => {
                                info!(?ids, ?code, "abnormal tasks");
                            }
                        }
                    }
                });
            }
            Err(err) => {
                error!(error=%err, "accept connection error");
                break;
            }
        }
    }
}

async fn read_message(
    stream: &mut UnixStream,
    code: &mut TaskCode,
    ids: &mut Vec<u32>,
    data: &mut Vec<Bytes>,
) -> Result<(), io::Error> {
    stream.readable().await?;
    let mut flag_buf = [0u8; FLAG_U8_SIZE];
    let mut num_buf = [0u8; NUM_U8_SIZE];
    stream.read_exact(&mut flag_buf).await?;
    stream.read_exact(&mut num_buf).await?;
    let flag = u16::from_be_bytes(flag_buf);
    let num = u16::from_be_bytes(num_buf);

    *code = if flag & BIT_STATUS_OK > 0 {
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
    Ok(())
}

async fn inner_batch(receiver: &Receiver<u32>, ids: &mut Vec<u32>, limit: usize) {
    loop {
        match receiver.recv().await {
            Ok(id) => {
                ids.push(id);
            }
            Err(err) => {
                error!(%err, "receive from channel error");
            }
        }
        if ids.len() == limit {
            break;
        }
    }
}

async fn get_batch(
    receiver: &Receiver<u32>,
    batch_size: usize,
    ids: &mut Vec<u32>,
    wait_time: Duration,
) {
    let id = receiver.recv().await.expect("receiver is closed");
    ids.push(id);
    if batch_size > 1 {
        let _ = tokio::time::timeout(wait_time, inner_batch(receiver, ids, batch_size)).await;
        debug!("batch size: {}/{}", ids.len(), batch_size);
    }
}

async fn send_message(
    stream: &mut UnixStream,
    ids: &[u32],
    data: &[Bytes],
) -> Result<(), io::Error> {
    stream.writable().await?;
    let mut buffer = BytesMut::new();
    buffer.put_u16(0); // flag
    buffer.put_u16(ids.len() as u16);
    for i in 0..ids.len() {
        buffer.put_u32(ids[i]);
        buffer.put_u32(data[i].len() as u32);
        buffer.put(data[i].clone());
    }
    stream.write_all(&buffer).await?;
    debug!(?ids, batch_size=%ids.len(), byte_size=%buffer.len(), "send data to the stream");

    Ok(())
}
