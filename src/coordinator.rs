use std::fs;
use std::path::Path;
use std::time::Duration;

use async_channel::{bounded, Receiver, Sender};
use tracing::{error, info};

use crate::args::Opts;
use crate::protocol::communicate;
use crate::tasks::{TaskManager, TASK_MANAGER};

#[derive(Debug)]
pub(crate) struct Coordinator {
    capacity: usize,
    path: String,
    batches: Vec<u32>,
    wait_time: Duration,
    timeout: Duration,
    receiver: Receiver<u32>,
    sender: Sender<u32>,
}

impl Coordinator {
    pub(crate) fn init_from_opts(opts: &Opts) -> Self {
        // init the global task manager
        let (sender, receiver) = bounded(opts.capacity);
        let timeout = Duration::from_millis(opts.timeout);
        let wait_time = Duration::from_millis(opts.wait);
        let task_manager = TaskManager::new(timeout, sender.clone());
        TASK_MANAGER.set(task_manager).unwrap();

        Self {
            capacity: opts.capacity,
            path: opts.path.to_string(),
            batches: opts.batches.clone(),
            wait_time,
            timeout,
            receiver,
            sender,
        }
    }

    pub(crate) async fn run(&self) {
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
            let path = folder.join(format!("ipc_{:?}.socket", i));

            let batch_size = *batch;
            tokio::spawn(communicate(
                path,
                batch_size as usize,
                wait_time,
                last_receiver.clone(),
                sender.clone(),
                last_sender.clone(),
            ));
            last_receiver = receiver;
            last_sender = sender;
        }
        tokio::spawn(finish_task(last_receiver.clone()));
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
