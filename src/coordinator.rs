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

use std::fs;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use async_channel::{bounded, Receiver, Sender};
use tokio::sync::Barrier;
use tracing::{error, info};

use crate::args::Opts;
use crate::metrics::{Metrics, METRICS};
use crate::protocol::communicate;
use crate::tasks::{TaskManager, TASK_MANAGER};

#[derive(Debug)]
pub(crate) struct Coordinator {
    capacity: usize,
    path: String,
    batches: Vec<u32>,
    wait_time: Duration,
    receiver: Receiver<u32>,
    sender: Sender<u32>,
}

impl Coordinator {
    pub(crate) fn init_from_opts(opts: &Opts) -> Self {
        // init the global task manager
        let (sender, receiver) = bounded(opts.capacity);
        let timeout = Duration::from_millis(opts.timeout);
        let wait_time = Duration::from_millis(opts.wait);
        let path = if !opts.path.is_empty() {
            opts.path.to_string()
        } else {
            // default IPC path
            std::env::temp_dir()
                .join(env!("CARGO_PKG_NAME"))
                .into_os_string()
                .into_string()
                .unwrap()
        };
        let task_manager = TaskManager::new(timeout, sender.clone());
        TASK_MANAGER.set(task_manager).unwrap();
        let metrics = Metrics::init_with_namespace(&opts.namespace, opts.timeout);
        METRICS.set(metrics).unwrap();

        Self {
            capacity: opts.capacity,
            path,
            batches: opts.batches.clone(),
            wait_time,
            receiver,
            sender,
        }
    }

    pub(crate) fn run(&self) -> Arc<Barrier> {
        let barrier = Arc::new(Barrier::new(self.batches.len() + 1));
        let mut last_receiver = self.receiver.clone();
        let mut last_sender = self.sender.clone();
        let wait_time = self.wait_time;
        let folder = Path::new(&self.path);
        if folder.is_dir() {
            info!(path=?folder, "path already exist, try to remove it");
            fs::remove_dir_all(folder).unwrap();
        }
        fs::create_dir(folder).unwrap();

        for (i, batch) in self.batches.iter().enumerate() {
            let (sender, receiver) = bounded::<u32>(self.capacity);
            let path = folder.join(format!("ipc_{:?}.socket", i + 1));

            let batch_size = *batch;
            tokio::spawn(communicate(
                path,
                batch_size as usize,
                wait_time,
                (i + 1).to_string(),
                last_receiver.clone(),
                sender.clone(),
                last_sender.clone(),
                barrier.clone(),
            ));
            last_receiver = receiver;
            last_sender = sender;
        }
        tokio::spawn(finish_task(last_receiver));
        barrier
    }
}

async fn finish_task(receiver: Receiver<u32>) {
    let task_manager = TaskManager::global();
    loop {
        match receiver.recv().await {
            Ok(id) => {
                task_manager.notify_task_done(id);
            }
            Err(err) => {
                error!(%err, "receive from the last channel error");
            }
        }
    }
}
