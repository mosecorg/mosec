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

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, RwLock};
use std::time::{Duration, Instant};

use bytes::Bytes;
use hyper::StatusCode;
use once_cell::sync::OnceCell;
use tokio::sync::{mpsc, oneshot};
use tokio::time;
use tracing::{debug, error, info, warn};

use crate::errors::ServiceError;
use crate::metrics::{CodeLabel, Metrics, DURATION_LABEL};

#[derive(Debug, Clone, Copy, PartialEq, Eq, derive_more::Display, derive_more::Error)]
pub(crate) enum TaskCode {
    #[display(fmt = "200: OK")]
    Normal,
    #[display(fmt = "400: Bad Request")]
    BadRequestError,
    #[display(fmt = "422: Unprocessable Content")]
    ValidationError,
    #[display(fmt = "408: Request Timeout")]
    TimeoutError,
    #[display(fmt = "500: Internal Server Error")]
    InternalError,
    // special case
    #[display(fmt = "500: Internal Server Error")]
    StreamEvent,
}

#[derive(Debug, Clone)]
pub(crate) struct Task {
    pub(crate) code: TaskCode,
    pub(crate) data: Bytes,
    pub(crate) create_at: Instant,
}

impl Task {
    fn new(data: Bytes) -> Self {
        Self {
            code: TaskCode::InternalError,
            data,
            create_at: Instant::now(),
        }
    }

    fn update(&mut self, code: TaskCode, data: &Bytes) {
        self.code = code;
        self.data = data.clone();
    }
}

#[derive(Debug)]
pub(crate) struct TaskManager {
    table: RwLock<HashMap<u32, Task>>,
    notifiers: Mutex<HashMap<u32, oneshot::Sender<()>>>,
    stream_senders: Mutex<HashMap<u32, mpsc::Sender<(Bytes, TaskCode)>>>,
    timeout: Duration,
    current_id: Mutex<u32>,
    channel: async_channel::Sender<u32>,
    shutdown: AtomicBool,
}

pub(crate) static TASK_MANAGER: OnceCell<TaskManager> = OnceCell::new();

impl TaskManager {
    pub(crate) fn global() -> &'static TaskManager {
        TASK_MANAGER.get().expect("task manager is not initialized")
    }

    pub(crate) fn new(timeout: Duration, channel: async_channel::Sender<u32>) -> Self {
        Self {
            table: RwLock::new(HashMap::new()),
            notifiers: Mutex::new(HashMap::new()),
            stream_senders: Mutex::new(HashMap::new()),
            timeout,
            current_id: Mutex::new(0),
            channel,
            shutdown: AtomicBool::new(false),
        }
    }

    pub(crate) async fn shutdown(&self) {
        self.shutdown.store(true, Ordering::Release);
        let fut = time::timeout(self.timeout, async {
            let mut interval = time::interval(Duration::from_millis(100));
            let mut retry = 0;
            loop {
                interval.tick().await;
                let remaining_task_num = self.table.read().unwrap().len();
                if remaining_task_num == 0 {
                    break;
                }
                retry += 1;
                if (retry % 10) == 0 {
                    info!(%remaining_task_num, "waiting for remaining tasks to complete");
                }
            }
        });
        if fut.await.is_err() {
            error!("service task manager shutdown timeout");
        }
    }

    pub(crate) async fn submit_task(&self, data: Bytes) -> Result<Task, ServiceError> {
        let (id, rx) = self.add_new_task(data)?;
        if let Err(err) = time::timeout(self.timeout, rx).await {
            warn!(%id, %err, "task was not completed in the expected time, if this happens a lot, \
                you might want to increase the service timeout");
            self.delete_task(id, false);
            return Err(ServiceError::Timeout);
        }
        let mut table = self.table.write().unwrap();
        match table.remove(&id) {
            Some(task) => Ok(task),
            None => {
                error!(%id, "cannot find the task when trying to remove it");
                Err(ServiceError::UnknownError)
            }
        }
    }

    pub(crate) async fn submit_sse_task(
        &self,
        data: Bytes,
    ) -> Result<mpsc::Receiver<(Bytes, TaskCode)>, ServiceError> {
        let (id, rx) = self.add_new_task(data)?;
        let (sender, receiver) = mpsc::channel(16);

        {
            let mut stream_senders = self.stream_senders.lock().unwrap();
            stream_senders.insert(id, sender);
        }
        let metrics = Metrics::global();
        metrics.remaining_task.inc();
        tokio::spawn(wait_sse_finish(id, self.timeout, rx));

        Ok(receiver)
    }

    pub(crate) fn get_stream_sender(&self, id: &u32) -> Option<mpsc::Sender<(Bytes, TaskCode)>> {
        let stream_senders = self.stream_senders.lock().unwrap();
        stream_senders.get(id).cloned()
    }

    pub(crate) fn delete_task(&self, id: u32, has_stream: bool) -> Option<Task> {
        let task;
        {
            let mut notifiers = self.notifiers.lock().unwrap();
            notifiers.remove(&id);
        }
        {
            let mut table = self.table.write().unwrap();
            task = table.remove(&id);
        }
        if has_stream {
            let mut stream_senders = self.stream_senders.lock().unwrap();
            stream_senders.remove(&id);
        }
        task
    }

    pub(crate) fn is_shutdown(&self) -> bool {
        self.shutdown.load(Ordering::Acquire)
    }

    fn add_new_task(&self, data: Bytes) -> Result<(u32, oneshot::Receiver<()>), ServiceError> {
        let (tx, rx) = oneshot::channel();
        let id: u32;
        {
            let mut current_id = self.current_id.lock().unwrap();
            id = *current_id;
            *current_id = id.wrapping_add(1);
        }
        {
            let mut notifiers = self.notifiers.lock().unwrap();
            notifiers.insert(id, tx);
        }
        {
            let mut table = self.table.write().unwrap();
            table.insert(id, Task::new(data));
        }
        debug!(%id, "add a new task");

        if self.channel.try_send(id).is_err() {
            warn!(%id, "reach the capacity limit, will delete this task");
            self.delete_task(id, false);
            return Err(ServiceError::TooManyRequests);
        }
        Ok((id, rx))
    }

    pub(crate) fn notify_task_done(&self, id: u32) {
        let res;
        {
            let mut notifiers = self.notifiers.lock().unwrap();
            res = notifiers.remove(&id);
        }
        if let Some(sender) = res {
            if !sender.is_closed() {
                sender.send(()).unwrap();
            } else {
                warn!(%id, "the task notifier is already closed, will delete it \
                    (this is usually because the client side has closed the connection)");
                {
                    let mut table = self.table.write().unwrap();
                    table.remove(&id);
                }
                let metrics = Metrics::global();
                metrics.remaining_task.dec();
            }
        } else {
            // if the task is already timeout, the notifier may be removed by another thread
            info!(%id, "cannot find the task notifier, maybe this task has expired");
        }
    }

    pub(crate) fn get_multi_tasks_data(&self, ids: &mut Vec<u32>, data: &mut Vec<Bytes>) {
        let table = self.table.read().unwrap();
        // delete the task_id if the task_id doesn't exist in the table
        ids.retain(|&id| match table.get(&id) {
            Some(task) => {
                data.push(task.data.clone());
                true
            }
            None => false,
        });
    }

    pub(crate) async fn update_multi_tasks(&self, code: TaskCode, ids: &[u32], data: &[Bytes]) {
        let mut abnormal_tasks = Vec::new();
        {
            // make sure the table lock is released since the next func call may need to acquire
            // the notifiers lock, we'd better only hold one lock at a time
            let mut table = self.table.write().unwrap();
            for i in 0..ids.len() {
                let task = table.get_mut(&ids[i]);
                match task {
                    Some(task) => {
                        task.update(code, &data[i]);
                        match code {
                            TaskCode::Normal => {}
                            _ => {
                                abnormal_tasks.push(ids[i]);
                            }
                        }
                    }
                    None => {
                        // if the task is already timeout, it may be removed by another thread
                        info!(id=%ids[i], "cannot find this task, maybe it has expired");
                    }
                }
            }
        }
        // check if it's a SSE task
        {
            for i in 0..abnormal_tasks.len() {
                if let Some(sender) = self.get_stream_sender(&abnormal_tasks[i]) {
                    if let Err(err) = sender.send((data[i].clone(), code)).await {
                        info!(%err, task_id=abnormal_tasks[i], "failed to send stream event");
                    }
                    debug!(%code, task_id=abnormal_tasks[i], "sent abnormal task event to the channel");
                }
            }
        }
        for task_id in abnormal_tasks {
            self.notify_task_done(task_id);
        }
    }
}

async fn wait_sse_finish(id: u32, timeout: Duration, notifier: oneshot::Receiver<()>) {
    let task_manager = TaskManager::global();
    if let Err(err) = time::timeout(timeout, notifier).await {
        warn!(%err, "task was not completed in the expected time");
    }

    let metrics = Metrics::global();
    if let Some(task) = task_manager.delete_task(id, true) {
        metrics
            .duration
            .get_or_create(DURATION_LABEL.get().expect("DURATION_LABEL is not set"))
            .observe(task.create_at.elapsed().as_secs_f64());
    }
    metrics.remaining_task.dec();
    // since the SSE will always return status code 200
    metrics
        .throughput
        .get_or_create(&CodeLabel {
            code: StatusCode::OK.as_u16(),
        })
        .inc();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn create_and_update_task() {
        let now = Instant::now();
        let mut task = Task::new(Bytes::from_static(b"hello"));
        assert!(task.create_at > now);
        assert!(task.create_at < Instant::now());
        assert!(matches!(task.code, TaskCode::InternalError));
        assert_eq!(task.data, Bytes::from_static(b"hello"));

        task.update(TaskCode::Normal, &Bytes::from_static(b"world"));
        assert!(matches!(task.code, TaskCode::Normal));
        assert_eq!(task.data, Bytes::from_static(b"world"));
    }

    #[tokio::test]
    async fn task_manager_add_new_task() {
        let (tx, rx) = async_channel::bounded(1);
        let task_manager = TaskManager::new(Duration::from_secs(1), tx);
        let (id, _rx) = task_manager
            .add_new_task(Bytes::from_static(b"hello"))
            .unwrap();
        assert_eq!(id, 0);
        {
            let table = task_manager.table.read().unwrap();
            let task = table.get(&id).unwrap();
            assert_eq!(task.data, Bytes::from_static(b"hello"));
        }
        let recv_id = rx.recv().await.unwrap();
        assert_eq!(recv_id, id);

        // add a new task
        let (id, _rx) = task_manager
            .add_new_task(Bytes::from_static(b"world"))
            .unwrap();
        assert_eq!(id, 1);
        {
            let table = task_manager.table.read().unwrap();
            let task = table.get(&id).unwrap();
            assert_eq!(task.data, Bytes::from_static(b"world"));
        }
        let recv_id = rx.recv().await.unwrap();
        assert_eq!(recv_id, id);
    }

    #[tokio::test]
    async fn task_manager_timeout() {
        let (tx, _rx) = async_channel::bounded(1);
        let task_manager = TaskManager::new(Duration::from_millis(1), tx);

        // wait until this task timeout
        let res = task_manager.submit_task(Bytes::from_static(b"hello")).await;
        assert!(matches!(res.unwrap_err(), ServiceError::Timeout));
    }

    #[tokio::test]
    async fn task_manager_too_many_request() {
        let (tx, _rx) = async_channel::bounded(1);
        // push one task into the channel to make the channel full
        let _ = tx.send(0u32).await;
        let task_manager = TaskManager::new(Duration::from_millis(1), tx);

        // trigger too many request since the capacity is 0
        let res = task_manager.submit_task(Bytes::from_static(b"hello")).await;
        assert!(matches!(res.unwrap_err(), ServiceError::TooManyRequests));
    }

    #[tokio::test]
    async fn task_manager_graceful_shutdown() {
        let (tx, _rx) = async_channel::bounded(1);
        let task_manager = TaskManager::new(Duration::from_millis(1), tx);
        assert!(!task_manager.is_shutdown());
        task_manager.shutdown().await;
        assert!(task_manager.is_shutdown());

        let (tx, _rx) = async_channel::bounded(1);
        let task_manager = TaskManager::new(Duration::from_millis(10), tx);
        {
            // block with one task in the channel
            let mut table = task_manager.table.write().unwrap();
            table.insert(0u32, Task::new(Bytes::from_static(b"hello")));
        }
        assert!(!task_manager.is_shutdown());
        let now = Instant::now();
        task_manager.shutdown().await;
        assert!(task_manager.is_shutdown());
        // force shutdown after a timeout duration
        assert!(now.elapsed() >= Duration::from_millis(10));
    }

    #[tokio::test]
    async fn task_manager_get_and_update_task() {
        let (tx, _rx) = async_channel::bounded(1);
        let task_manager = TaskManager::new(Duration::from_millis(1), tx);

        // add some tasks to the table
        {
            let mut table = task_manager.table.write().unwrap();
            table.insert(0, Task::new(Bytes::from_static(b"hello")));
            table.insert(1, Task::new(Bytes::from_static(b"world")));
        }

        let mut task_ids = vec![0, 1, 2];
        let mut data = Vec::new();
        task_manager.get_multi_tasks_data(&mut task_ids, &mut data);
        assert_eq!(task_ids, vec![0, 1]);
        assert_eq!(
            data,
            vec![Bytes::from_static(b"hello"), Bytes::from_static(b"world")]
        );

        // update tasks
        data = vec![Bytes::from_static(b"rust"), Bytes::from_static(b"tokio")];
        task_manager
            .update_multi_tasks(TaskCode::Normal, &task_ids, &data)
            .await;
        let mut new_data = Vec::new();
        task_manager.get_multi_tasks_data(&mut task_ids, &mut new_data);
        assert_eq!(task_ids, vec![0, 1]);
        assert_eq!(
            new_data,
            vec![Bytes::from_static(b"rust"), Bytes::from_static(b"tokio")]
        );
    }
}
