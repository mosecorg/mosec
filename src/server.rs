use std::{
    fs,
    path::Path,
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

use bytes::Bytes;
use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender};
use tracing::info;

use crate::{
    batcher, coordinator,
    errors::{MosecError, ServiceError},
    pool::{self, TaskStatusCode},
};

#[derive(Debug)]
pub struct MServer {
    pub batcher_limits: Vec<usize>,
    pub batcher_wait: Duration,
    pub batcher_interval: Duration,
    pub protocol_unix_root: String,
    pub queue_capacity: usize,
    pub web_inbound_tx: Sender<usize>,
    pub web_inbound_rx: Receiver<usize>,
    pub service_timeout: Duration,
    pub task_pool: Arc<Mutex<pool::TaskPool>>,
}

impl MServer {
    pub fn new(
        batcher_limits: Vec<usize>,
        batcher_wait: Duration,
        batcher_interval: Duration,
        protocol_unix_root: String,
        queue_capacity: usize,
        service_timeout: Duration,
    ) -> Arc<Self> {
        let (web_inbound_tx, web_inbound_rx) = bounded(queue_capacity);
        let task_pool = pool::TaskPool::new();
        Arc::new(MServer {
            batcher_limits,
            batcher_wait,
            batcher_interval,
            protocol_unix_root,
            queue_capacity,
            web_inbound_tx,
            web_inbound_rx,
            service_timeout,
            task_pool,
        })
    }
    pub fn submit(&self, data: Bytes) -> Result<(Receiver<usize>, Sender<()>), MosecError> {
        // When timeout, the task is cancelled before protocol send
        let (cancel_tx, cancel_rx) = bounded(1);
        let tp = Arc::clone(&self.task_pool);
        match pool::init_task(&tp, data, cancel_rx) {
            Ok((id, result_rx)) => match self.web_inbound_tx.send(id) {
                Ok(_) => Ok((result_rx, cancel_tx)),
                Err(_) => {
                    eprintln!("Error: broken pipe");
                    Err(MosecError::BrokenPipeError)
                }
            },
            Err(error) => Err(error),
        }
    }
    pub fn retrieve(
        &self,
        result: Receiver<usize>,
        cancel: Sender<()>,
    ) -> Result<Bytes, ServiceError> {
        match result.recv_timeout(self.service_timeout) {
            Ok(id) => {
                let tp = Arc::clone(&self.task_pool);
                match pool::get_task(&tp, id) {
                    Ok(task) => match task.status {
                        TaskStatusCode::Normal => Ok(task.data),
                        TaskStatusCode::ValidationError => Err(ServiceError::ValidationError),
                        TaskStatusCode::InternalError => Err(ServiceError::InternalError),
                        TaskStatusCode::UnknownError => Err(ServiceError::UnknownError),
                    },
                    Err(error) => {
                        println!("{:?}", error);
                        Err(ServiceError::InternalError)
                    }
                }
            }
            Err(error) => match error {
                RecvTimeoutError::Timeout => {
                    cancel.send(()).unwrap();
                    Err(ServiceError::Timeout)
                }
                RecvTimeoutError::Disconnected => {
                    cancel.send(()).unwrap();
                    println!("result channel disconnected");
                    Err(ServiceError::UnknownError)
                }
            },
        }
    }
}

pub fn run(server: Arc<MServer>) {
    // prepare channels
    // batcher->coordinator (.len() = stage_num)
    let mut b_outbound = Vec::new(); // batchers' output
    let mut c_inbound = Vec::new(); // coordinators' input

    // coordinator->next batcher (.len() = stage_num - 1)
    let mut b_inbound = Vec::new(); // next batchers' input
    let mut c_outbound = Vec::new(); // coordinators' output
    for i in 0..server.batcher_limits.len() {
        let (tx, rx) = bounded::<Vec<usize>>(server.queue_capacity);
        b_outbound.push(tx);
        c_inbound.push(rx);
        if i > 0 {
            let (tx, rx) = bounded::<usize>(server.queue_capacity);
            b_inbound.push(rx);
            c_outbound.push(tx);
        }
    }

    // prepare protocol
    let folder = Path::new(&server.protocol_unix_root);
    if folder.is_dir() {
        info!(path=?folder, "path already exist, try to remove it");
        fs::remove_dir_all(folder).unwrap();
    }
    fs::create_dir(folder).unwrap();

    let stage_num = server.batcher_limits.len();
    let batcher_wait = server.batcher_wait;
    let batcher_interval = server.batcher_interval;

    // for each workload stage
    for stage_id in 0..stage_num {
        let server = server.clone();
        let task_pool = server.task_pool.clone();
        // start batcher
        let batcher_inbound = if stage_id == 0 {
            server.web_inbound_rx.clone()
        } else {
            b_inbound[stage_id - 1].clone()
        };
        let batcher_outbound = b_outbound[stage_id].clone();
        let batcher_outbound_put_back = b_outbound[stage_id].clone();

        let limit = server.batcher_limits[stage_id];
        thread::spawn(move || {
            batcher::start_batcher(
                stage_id,
                limit,
                batcher_wait,
                batcher_interval,
                batcher_inbound,
                batcher_outbound,
            )
        });

        // start listener for new workload (communicated via coordinator)
        let coordinator_inbound = c_inbound[stage_id].clone();
        let coordinator_outbound = if stage_id < stage_num - 1 {
            c_outbound[stage_id].clone()
        } else {
            // dummy outbound for the last stage
            let (dummy_tx, dummy_rx) = bounded::<usize>(0);
            drop(dummy_rx);
            dummy_tx
        };
        let path = folder.join(format!("ipc_{:?}.socket", stage_id));
        thread::spawn(move || {
            coordinator::start_listener(
                stage_id,
                path,
                task_pool,
                coordinator_inbound,
                coordinator_outbound,
                batcher_outbound_put_back,
                stage_id == stage_num - 1,
            )
        });
    }
}
