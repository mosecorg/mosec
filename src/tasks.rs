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
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::http::StatusCode;
use bytes::Bytes;
use tokio::sync::{mpsc, oneshot, Barrier};
use tokio::time;
use tracing::{debug, error, info, warn};

use crate::config::Config;
use crate::errors::ServiceError;
use crate::metrics::{CodeLabel, Metrics, DURATION_LABEL};
use crate::protocol::communicate;

#[derive(Debug, Clone, Copy, PartialEq, Eq, derive_more::Display, derive_more::Error)]
pub(crate) enum TaskCode {
    #[display("200: OK")]
    Normal,
    #[display("400: Bad Request")]
    BadRequestError,
    #[display("422: Unprocessable Content")]
    ValidationError,
    #[display("408: Request Timeout")]
    TimeoutError,
    #[display("500: Internal Server Error")]
    InternalError,
    // special case
    #[display("200: Server Sent Event")]
    StreamEvent,
}

#[derive(Debug, Clone)]
pub(crate) struct Task {
    pub(crate) code: TaskCode,
    pub(crate) data: Bytes,
    pub(crate) stage: usize,
    pub(crate) route: String,
    pub(crate) create_at: Instant,
}

impl Task {
    fn new(data: Bytes, route: String) -> Self {
        Self {
            code: TaskCode::InternalError,
            data,
            stage: 0,
            route,
            create_at: Instant::now(),
        }
    }

    fn update(&mut self, code: TaskCode, data: &Bytes) {
        self.code = code;
        self.data = data.clone();
        self.stage += 1;
    }

    /// Encode the current state of the task into a 16-bit integer.
    /// 0000 0000 0000 00yx
    /// x: is ingress
    /// y: is egress
    fn encode_state(&self, total: usize) -> u16 {
        let mut state = 0;
        state |= (self.stage == 0) as u16;
        state |= ((total - 1 == self.stage) as u16) << 1;
        state
    }
}

#[derive(Debug)]
pub(crate) struct TaskManager {
    table: Mutex<HashMap<u32, Task>>,
    notifiers: Mutex<HashMap<u32, oneshot::Sender<()>>>,
    stream_senders: Mutex<HashMap<u32, mpsc::Sender<(Bytes, TaskCode)>>>,
    timeout: Duration,
    current_id: Mutex<u32>,
    senders: HashMap<String, Vec<async_channel::Sender<u32>>>,
    mime_types: HashMap<String, String>,
    shutdown: AtomicBool,
}

pub(crate) static TASK_MANAGER: OnceLock<TaskManager> = OnceLock::new();

impl TaskManager {
    pub(crate) fn global() -> &'static TaskManager {
        TASK_MANAGER.get().expect("task manager is not initialized")
    }

    pub(crate) fn new(timeout: u64) -> Self {
        Self {
            table: Mutex::new(HashMap::new()),
            notifiers: Mutex::new(HashMap::new()),
            stream_senders: Mutex::new(HashMap::new()),
            timeout: Duration::from_millis(timeout),
            current_id: Mutex::new(0),
            senders: HashMap::new(),
            mime_types: HashMap::new(),
            shutdown: AtomicBool::new(false),
        }
    }

    pub(crate) fn init_from_config(&mut self, conf: &Config) -> Arc<Barrier> {
        let barrier = Arc::new(Barrier::new(conf.runtimes.len() + 1));

        let mut worker_channel =
            HashMap::<String, (async_channel::Receiver<u32>, async_channel::Sender<u32>)>::new();
        let dir = Path::new(&conf.path);

        // run the coordinator in different threads
        for runtime in &conf.runtimes {
            let (tx, rx) = async_channel::bounded::<u32>(conf.capacity);
            worker_channel.insert(runtime.worker.clone(), (rx.clone(), tx));
            let path = dir.join(format!("ipc_{}.socket", runtime.worker));
            tokio::spawn(communicate(
                path,
                runtime.max_batch_size,
                Duration::from_millis(runtime.max_wait_time),
                runtime.worker.clone(),
                rx,
                barrier.clone(),
            ));
        }

        for route in &conf.routes {
            self.mime_types
                .insert(route.endpoint.clone(), route.mime.clone());
            let worker_senders = route
                .workers
                .iter()
                .map(|w| worker_channel[w].1.clone())
                .collect();
            self.senders.insert(route.endpoint.clone(), worker_senders);
        }

        barrier
    }

    pub(crate) fn get_mime_type(&self, endpoint: &str) -> Option<&String> {
        self.mime_types.get(endpoint)
    }

    pub(crate) async fn send_task(&self, id: &u32) {
        let stage: usize;
        let route: &Vec<async_channel::Sender<u32>>;
        {
            let table = self.table.lock().unwrap();
            match table.get(id) {
                Some(task) => {
                    stage = task.stage;
                    route = &self.senders[&task.route];
                }
                None => {
                    warn!(%id, "failed to get the task when trying to send it");
                    return;
                }
            };
        }
        if stage >= route.len() {
            self.notify_task_done(id);
            return;
        }
        if route[stage].send(*id).await.is_err() {
            warn!(%id, "failed to send this task, the sender might be closed");
        }
    }

    pub(crate) async fn shutdown(&self) {
        self.shutdown.store(true, Ordering::Release);
        let fut = time::timeout(self.timeout, async {
            let mut interval = time::interval(Duration::from_millis(100));
            let mut retry = 0;
            loop {
                interval.tick().await;
                let remaining_task_num = self.table.lock().unwrap().len();
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

    pub(crate) async fn submit_task(&self, data: Bytes, key: &str) -> Result<Task, ServiceError> {
        let (id, rx) = self.add_new_task(data, key)?;
        if let Err(err) = time::timeout(self.timeout, rx).await {
            warn!(%id, %err, "task was not completed in the expected time, if this happens a lot, \
                you might want to increase the service timeout");
            self.delete_task(id, false);
            return Err(ServiceError::Timeout);
        }
        let mut table = self.table.lock().unwrap();
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
        key: &str,
    ) -> Result<mpsc::Receiver<(Bytes, TaskCode)>, ServiceError> {
        let (id, rx) = self.add_new_task(data, key)?;
        let (sender, receiver) = mpsc::channel(16);

        {
            let mut stream_senders = self.stream_senders.lock().unwrap();
            stream_senders.insert(id, sender);
        }
        let metrics = Metrics::global();
        metrics.remaining_task.inc();
        tokio::spawn(wait_sse_finish(id, key.to_string(), self.timeout, rx));

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
            let mut table = self.table.lock().unwrap();
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

    fn add_new_task(
        &self,
        data: Bytes,
        key: &str,
    ) -> Result<(u32, oneshot::Receiver<()>), ServiceError> {
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
            let mut table = self.table.lock().unwrap();
            table.insert(id, Task::new(data, key.to_string()));
        }
        debug!(%id, "add a new task");

        if self.senders[key][0].try_send(id).is_err() {
            warn!(%id, "reach the capacity limit, will delete this task");
            self.delete_task(id, false);
            return Err(ServiceError::TooManyRequests);
        }
        Ok((id, rx))
    }

    pub(crate) fn notify_task_done(&self, id: &u32) {
        let res;
        {
            let mut notifiers = self.notifiers.lock().unwrap();
            res = notifiers.remove(id);
        }
        if let Some(sender) = res {
            if !sender.is_closed() {
                sender.send(()).unwrap();
            } else {
                warn!(%id, "the task notifier is already closed, will delete it \
                    (this is usually because the client side has closed the connection)");
                {
                    let mut table = self.table.lock().unwrap();
                    table.remove(id);
                }
                let metrics = Metrics::global();
                metrics.remaining_task.dec();
            }
        } else {
            // if the task is already timeout, the notifier may be removed by another thread
            info!(%id, "cannot find the task notifier, maybe this task has expired");
        }
    }

    pub(crate) fn get_multi_tasks_data(
        &self,
        ids: &mut Vec<u32>,
        data: &mut Vec<Bytes>,
        states: &mut Vec<u16>,
    ) {
        let table = self.table.lock().unwrap();
        // delete the task_id if the task_id doesn't exist in the table
        ids.retain(|&id| match table.get(&id) {
            Some(task) => {
                data.push(task.data.clone());
                states.push(task.encode_state(self.senders[&task.route].len()));
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
            let mut table = self.table.lock().unwrap();
            for i in 0..ids.len() {
                let task = table.get_mut(&ids[i]);
                match task {
                    Some(task) => {
                        task.update(code, &data[i]);
                        if code != TaskCode::Normal {
                            abnormal_tasks.push(ids[i]);
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
        for task_id in &abnormal_tasks {
            self.notify_task_done(task_id);
        }
    }
}

async fn wait_sse_finish(
    id: u32,
    endpoint: String,
    timeout: Duration,
    notifier: oneshot::Receiver<()>,
) {
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
            endpoint,
        })
        .inc();
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEFAULT_ENDPOINT: &str = "/inference";

    #[test]
    fn create_and_update_task() {
        let now = Instant::now();
        let mut task = Task::new(Bytes::from_static(b"hello"), "".to_string());
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
        let mut task_manager = TaskManager::new(1000);
        task_manager.init_from_config(&Config::default());
        let (id, _rx) = task_manager
            .add_new_task(Bytes::from_static(b"hello"), DEFAULT_ENDPOINT)
            .unwrap();
        assert_eq!(id, 0);
        {
            let table = task_manager.table.lock().unwrap();
            let task = table.get(&id).unwrap();
            assert_eq!(task.data, Bytes::from_static(b"hello"));
        }

        // add a new task
        let (id, _rx) = task_manager
            .add_new_task(Bytes::from_static(b"world"), DEFAULT_ENDPOINT)
            .unwrap();
        assert_eq!(id, 1);
        {
            let table = task_manager.table.lock().unwrap();
            let task = table.get(&id).unwrap();
            assert_eq!(task.data, Bytes::from_static(b"world"));
        }
    }

    #[tokio::test]
    async fn task_manager_timeout() {
        let mut task_manager = TaskManager::new(1);
        task_manager.init_from_config(&Config::default());

        // wait until this task timeout
        let res = task_manager
            .submit_task(Bytes::from_static(b"hello"), DEFAULT_ENDPOINT)
            .await;
        assert!(matches!(res.unwrap_err(), ServiceError::Timeout));
    }

    #[tokio::test]
    async fn task_manager_too_many_request() {
        let mut task_manager = TaskManager::new(1);
        let mut config = Config::default();
        // capacity > 0
        config.capacity = 1;
        task_manager.init_from_config(&config);
        // send one task id to block the channel
        task_manager.senders[DEFAULT_ENDPOINT][0]
            .send(0)
            .await
            .unwrap();

        // trigger too many request since the capacity is 1
        let res = task_manager
            .submit_task(Bytes::from_static(b"hello"), DEFAULT_ENDPOINT)
            .await;
        assert!(matches!(res.unwrap_err(), ServiceError::TooManyRequests));
    }

    #[tokio::test]
    async fn task_manager_graceful_shutdown() {
        let mut task_manager = TaskManager::new(1);
        task_manager.init_from_config(&Config::default());
        assert!(!task_manager.is_shutdown());
        task_manager.shutdown().await;
        assert!(task_manager.is_shutdown());
    }

    #[tokio::test]
    async fn task_manager_graceful_shutdown_after_timeout() {
        let mut task_manager = TaskManager::new(10);
        task_manager.init_from_config(&Config::default());
        {
            // block with one task in the channel
            let mut table = task_manager.table.lock().unwrap();
            table.insert(
                0u32,
                Task::new(Bytes::from_static(b"hello"), DEFAULT_ENDPOINT.to_string()),
            );
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
        let mut task_manager = TaskManager::new(1);
        task_manager.init_from_config(&Config::default());

        // add some tasks to the table
        {
            let mut table = task_manager.table.lock().unwrap();
            table.insert(
                0,
                Task::new(Bytes::from_static(b"hello"), DEFAULT_ENDPOINT.to_string()),
            );
            table.insert(
                1,
                Task::new(Bytes::from_static(b"world"), DEFAULT_ENDPOINT.to_string()),
            );
        }

        let mut task_ids = vec![0, 1, 2];
        let mut data = Vec::new();
        let mut states = Vec::new();
        task_manager.get_multi_tasks_data(&mut task_ids, &mut data, &mut states);
        assert_eq!(task_ids, vec![0, 1]);
        assert_eq!(
            data,
            vec![Bytes::from_static(b"hello"), Bytes::from_static(b"world")]
        );
        assert_eq!(states, vec![3 as u16, 3 as u16]);

        // update tasks
        data = vec![Bytes::from_static(b"rust"), Bytes::from_static(b"tokio")];
        task_manager
            .update_multi_tasks(TaskCode::Normal, &task_ids, &data)
            .await;
        let mut new_data = Vec::new();
        task_manager.get_multi_tasks_data(&mut task_ids, &mut new_data, &mut states);
        assert_eq!(task_ids, vec![0, 1]);
        assert_eq!(
            new_data,
            vec![Bytes::from_static(b"rust"), Bytes::from_static(b"tokio")]
        );
    }
}
