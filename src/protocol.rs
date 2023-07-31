// Copyright 2022 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_channel::Receiver;
use bytes::{BufMut, Bytes, BytesMut};
use tokio::io::{self, AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::Barrier;
use tracing::{debug, error, info, warn};

use crate::metrics::{Metrics, StageConnectionLabel};
use crate::tasks::{TaskCode, TaskManager};

const FLAG_U8_SIZE: usize = 2;
const NUM_U8_SIZE: usize = 2;
const STATE_U8_SIZE: usize = 2;
const TASK_ID_U8_SIZE: usize = 4;
const LENGTH_U8_SIZE: usize = 4;

const BIT_STATUS_OK: u16 = 0b1;
const BIT_STATUS_BAD_REQ: u16 = 0b10;
const BIT_STATUS_VALIDATION_ERR: u16 = 0b100;
const BIT_STATUS_TIMEOUT_ERR: u16 = 0b10000;
const BIT_STATUS_STREAM_EVENT: u16 = 0b1000000000000000;
// Others are treated as Internal Error

#[allow(clippy::too_many_arguments)]
pub(crate) async fn communicate(
    path: PathBuf,
    batch_size: usize,
    wait_time: Duration,
    stage_name: String,
    receiver: Receiver<u32>,
    barrier: Arc<Barrier>,
) {
    let listener = UnixListener::bind(&path).expect("failed to bind to the socket");
    let mut connection_id: u32 = 0;
    loop {
        connection_id += 1;
        let receiver_clone = receiver.clone();
        let stage_name_label = stage_name.clone();
        let connection_id_label = connection_id.to_string();
        info!(?path, "begin listening to socket");
        match listener.accept().await {
            Ok((mut stream, addr)) => {
                info!(?addr, "socket accepted connection from");
                tokio::spawn(async move {
                    let mut code: TaskCode = TaskCode::InternalError;
                    let mut ids: Vec<u32> = Vec::with_capacity(batch_size);
                    let mut data: Vec<Bytes> = Vec::with_capacity(batch_size);
                    let mut states: Vec<u16> = Vec::with_capacity(batch_size);
                    let task_manager = TaskManager::global();
                    let metrics = Metrics::global();
                    let metric_label = StageConnectionLabel {
                        stage: stage_name_label.clone(),
                        connection: connection_id_label,
                    };
                    loop {
                        ids.clear();
                        data.clear();
                        states.clear();
                        let batch_timer =
                            get_batch(&receiver_clone, batch_size, &mut ids, wait_time).await;
                        if let Some(timer) = batch_timer {
                            metrics
                                .batch_duration
                                .get_or_create(&metric_label)
                                .observe(timer.elapsed().as_secs_f64())
                        }
                        // start record the duration metrics here because receiving the first task
                        // depends on when the request comes in.
                        let start_timer = Instant::now();
                        task_manager.get_multi_tasks_data(&mut ids, &mut data, &mut states);
                        if data.is_empty() {
                            continue;
                        }
                        if batch_size > 1 {
                            // only record the batch size when it's set to a number > 1
                            metrics
                                .batch_size
                                .get_or_create(&metric_label)
                                .observe(data.len() as f64);
                        }
                        if let Err(err) = send_message(&mut stream, &ids, &data, &states).await {
                            error!(%err, %stage_name_label, %connection_id, "socket send message error");
                            info!(
                                "service failed to write data to stream, will try to send task \
                                 back to see if other thread can handle it"
                            );
                            for id in &ids {
                                task_manager.send_task(id).await;
                            }
                            break;
                        }
                        debug!(%stage_name_label, %connection_id, "socket finished to send message");

                        ids.clear();
                        data.clear();
                        states.clear();
                        if let Err(err) =
                            read_message(&mut stream, &mut code, &mut ids, &mut data, &mut states)
                                .await
                        {
                            error!(%err, %stage_name_label, %connection_id, "socket receive message error");
                            break;
                        }
                        debug!(%stage_name_label, %connection_id, "socket finished to read message");
                        while code == TaskCode::StreamEvent {
                            send_stream_event(&ids, &data).await;
                            ids.clear();
                            data.clear();
                            states.clear();
                            if let Err(err) = read_message(
                                &mut stream,
                                &mut code,
                                &mut ids,
                                &mut data,
                                &mut states,
                            )
                            .await
                            {
                                error!(%err, %stage_name_label, %connection_id, "socket receive message error");
                                break;
                            }
                            debug!(%stage_name_label, %connection_id, "socket finished to read message");
                        }
                        task_manager.update_multi_tasks(code, &ids, &data).await;
                        match code {
                            TaskCode::Normal => {
                                for id in &ids {
                                    task_manager.send_task(id).await;
                                }
                                // only the normal tasks will be recorded
                                metrics
                                    .duration
                                    .get_or_create(&metric_label)
                                    .observe(start_timer.elapsed().as_secs_f64());
                            }
                            _ => {
                                warn!(
                                    ?ids,
                                    ?code,
                                    ?stage_name_label,
                                    ?connection_id,
                                    "abnormal tasks, check Python log for more details"
                                );
                            }
                        }
                    }
                });
                // ensure every stage is properly initialized (including warmup)
                if connection_id == 1 {
                    barrier.wait().await;
                }
            }
            Err(err) => {
                error!(%err, %stage_name, %connection_id, "socket failed to accept the connection");
                break;
            }
        }
    }
}

async fn send_stream_event(ids: &[u32], data: &[Bytes]) {
    let task_manager = TaskManager::global();
    debug!("sending stream event");
    for (id, data) in ids.iter().zip(data.iter()) {
        match task_manager.get_stream_sender(id) {
            Some(sender) => {
                if let Err(err) = sender.send((data.clone(), TaskCode::Normal)).await {
                    info!(%err, %id, "failed to send stream event");
                }
            }
            None => {
                info!(%id, "stream sender not found");
            }
        }
    }
}

async fn read_message(
    stream: &mut UnixStream,
    code: &mut TaskCode,
    ids: &mut Vec<u32>,
    data: &mut Vec<Bytes>,
    states: &mut Vec<u16>,
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
    } else if flag & BIT_STATUS_TIMEOUT_ERR > 0 {
        TaskCode::TimeoutError
    } else if flag & BIT_STATUS_STREAM_EVENT > 0 {
        TaskCode::StreamEvent
    } else {
        TaskCode::InternalError
    };
    debug!(?flag, ?flag_buf, "read message");

    let mut id_buf = [0u8; TASK_ID_U8_SIZE];
    let mut length_buf = [0u8; LENGTH_U8_SIZE];
    let mut state_buf = [0u8; STATE_U8_SIZE];
    for _ in 0..num {
        stream.read_exact(&mut id_buf).await?;
        stream.read_exact(&mut state_buf).await?;
        stream.read_exact(&mut length_buf).await?;
        let id = u32::from_be_bytes(id_buf);
        let state = u16::from_be_bytes(state_buf);
        let length = u32::from_be_bytes(length_buf);
        let mut data_buf = vec![0u8; length as usize];
        stream.read_exact(&mut data_buf).await?;
        ids.push(id);
        states.push(state);
        data.push(data_buf.into());
    }
    let byte_size = data.iter().fold(0, |acc, x| acc + x.len());
    debug!(
        ?ids,
        ?code,
        ?num,
        ?flag,
        ?byte_size,
        "received tasks from the socket"
    );
    Ok(())
}

async fn inner_batch(receiver: &Receiver<u32>, ids: &mut Vec<u32>, limit: usize) {
    loop {
        match receiver.recv().await {
            Ok(id) => {
                ids.push(id);
            }
            Err(err) => {
                error!(%err, "failed to collect the tasks in batch");
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
) -> Option<Instant> {
    let id = receiver.recv().await.expect("receiver is closed");
    ids.push(id);
    if batch_size <= 1 {
        return None;
    }
    // counting from receiving the first task
    let start_time = Instant::now();
    let _ = tokio::time::timeout(wait_time, inner_batch(receiver, ids, batch_size)).await;
    debug!("batch size: {}/{}", ids.len(), batch_size);
    Some(start_time)
}

async fn send_message(
    stream: &mut UnixStream,
    ids: &[u32],
    data: &[Bytes],
    states: &[u16],
) -> Result<(), io::Error> {
    stream.writable().await?;
    let mut buffer = BytesMut::new();
    buffer.put_u16(0); // flag
    buffer.put_u16(ids.len() as u16);
    for i in 0..ids.len() {
        buffer.put_u32(ids[i]);
        buffer.put_u16(states[i]);
        buffer.put_u32(data[i].len() as u32);
        buffer.put(data[i].clone());
    }
    stream.write_all(&buffer).await?;
    debug!(?ids, batch_size=%ids.len(), byte_size=%buffer.len(), "send data to the socket");

    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{env, vec};

    use super::*;

    #[tokio::test]
    async fn get_batch_from_channel() {
        let (sender, receiver) = async_channel::bounded(64);
        let wait = Duration::from_millis(1);
        for i in 0..32 {
            sender.send(i as u32).await.expect("sender is closed");
        }

        let mut ids = Vec::new();
        get_batch(&receiver, 8, &mut ids, wait).await;
        assert_eq!(ids, vec![0, 1, 2, 3, 4, 5, 6, 7]);

        ids.clear();
        get_batch(&receiver, 1, &mut ids, wait).await;
        assert_eq!(ids, vec![8]);

        ids.clear();
        get_batch(&receiver, 20, &mut ids, wait).await;
        assert_eq!(ids.len(), 20);

        ids.clear();
        get_batch(&receiver, 8, &mut ids, wait).await;
        assert_eq!(ids, vec![29, 30, 31]);

        // channel is empty
        ids.clear();
        let fut = tokio::time::timeout(wait * 2, get_batch(&receiver, 1, &mut ids, wait)).await;
        assert!(fut.is_err());

        sender.send(0).await.expect("sender is closed");
        ids.clear();
        get_batch(&receiver, 1, &mut ids, wait).await;
        assert_eq!(ids, vec![0]);
    }

    #[tokio::test]
    async fn stream_read_write() {
        let path = env::temp_dir().join("mosec_test.ipc");
        if path.exists() {
            std::fs::remove_file(&path).expect("remove file error");
        }
        let listener = UnixListener::bind(&path).expect("bind error");
        let ids = vec![0u32, 1];
        let data = vec![Bytes::from_static(b"hello"), Bytes::from_static(b"world")];
        let states = vec![1u16, 2];

        // setup the server in another tokio thread
        let ids_clone = ids.clone();
        let data_clone = data.clone();
        let states_clone = states.clone();
        tokio::spawn(async move {
            let (mut stream, _addr) = listener.accept().await.unwrap();
            send_message(&mut stream, &ids_clone, &data_clone, &states_clone)
                .await
                .expect("send message error");
            tokio::time::sleep(Duration::from_millis(1)).await;
        });

        let mut stream = UnixStream::connect(&path).await.unwrap();
        let mut recv_ids = Vec::new();
        let mut recv_states = Vec::new();
        let mut recv_data = Vec::new();
        let mut code = TaskCode::InternalError;
        read_message(
            &mut stream,
            &mut code,
            &mut recv_ids,
            &mut recv_data,
            &mut recv_states,
        )
        .await
        .expect("read message error");

        assert_eq!(recv_ids, ids);
        assert_eq!(recv_data, data);
        assert_eq!(recv_states, states);
        std::fs::remove_file(&path).expect("failed to remove the test socket file");
    }
}
