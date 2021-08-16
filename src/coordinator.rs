use std::{
    os::unix::net::{UnixListener, UnixStream},
    path::PathBuf,
    sync::{Arc, Mutex},
    thread,
};

use crossbeam_channel::{Receiver, Sender, TryRecvError};
use tracing::{debug, info, warn};

use crate::{
    pool::{self, TaskPool, TaskStatusCode},
    protocol::*,
};

struct Coordinator {
    stage_id: usize,
    task_pool: Arc<Mutex<TaskPool>>,
    protocol_server: Protocol,     // server side of unix stream
    inbound: Receiver<Vec<usize>>, // - symmetrical to batcher.rs,
    outbound: Sender<usize>,       //   (maybe) multiple input, single output
    put_back: Sender<Vec<usize>>,  // recycle tasks when disconnection
    last: bool,                    // indication of last stage
}

impl Coordinator {
    pub fn run(&mut self) {
        loop {
            // get ids from batcher, fetch data, send to workload
            let recv_ids = self.inbound.recv().expect("coordinator inbound recv error");
            let mut req_ids = Vec::new();
            let mut req_payloads = Vec::new();
            let mut completes = Vec::new();
            let mut cancels = Vec::new();
            debug!("stage-{} processing task-{:?}", self.stage_id, recv_ids);
            for id in recv_ids {
                let task = pool::get_task(&self.task_pool, id).unwrap();
                match task.cancel.try_recv() {
                    Ok(_) => {
                        debug!("stage-{} cancelling task-{} ", self.stage_id, id);
                        continue;
                    }
                    Err(TryRecvError::Disconnected) => panic!("cancel channel disconnected"), // TODO: handle error
                    Err(TryRecvError::Empty) => {
                        // not canceled (e.g. due to timeout) yet
                        req_ids.push(id);
                        req_payloads.push(task.data.clone());
                        completes.push(task.complete.clone());
                        cancels.push(task.cancel.clone());
                    }
                }
            }
            match self
                .protocol_server
                .send(FLAG_OK as u16, &req_ids, &req_payloads)
            {
                Ok(_) => {}
                Err(error) => {
                    warn!("stage-{} protocol client error: {:?}\tterminating the thread and recycling the task", self.stage_id, error);
                    // put tasks back
                    pool::update_task_batch(
                        &self.task_pool,
                        &req_ids,
                        req_payloads,
                        TaskStatusCode::UnknownError,
                        &completes,
                        cancels,
                    )
                    .unwrap();
                    self.put_back.send(req_ids).unwrap();
                    return;
                }
            }

            // get from workload, store data, send to next batcher or return result (after status check)
            let mut flag = FLAG_OK;
            let mut resp_ids = Vec::new();
            let mut resp_payloads = Vec::new();
            self.protocol_server
                .receive(&mut flag, &mut resp_ids, &mut resp_payloads)
                .expect("protocol client disconnected");
            let status = if flag == FLAG_OK {
                TaskStatusCode::Normal
            } else if flag == FLAG_BAD_REQUEST {
                TaskStatusCode::ValidationError
            } else if flag == FLAG_VALIDATION_ERROR {
                TaskStatusCode::ValidationError
            } else if flag == FLAG_INTERNAL_ERROR {
                TaskStatusCode::InternalError
            } else {
                TaskStatusCode::UnknownError
            };

            pool::update_task_batch(
                &self.task_pool,
                &resp_ids,
                resp_payloads,
                status,
                &completes,
                cancels,
            )
            .unwrap();

            for i in 0..resp_ids.len() {
                let id = resp_ids[i];
                let complete = completes[i].clone();
                // early stop if any error occurs at current stage
                if flag != FLAG_OK || self.last {
                    complete.send(id).unwrap();
                } else {
                    self.outbound.send(id).unwrap();
                }
            }
        }
    }
}

fn handle_workload(
    stage_id: usize,
    stream: UnixStream,
    task_pool: Arc<Mutex<TaskPool>>,
    inbound: Receiver<Vec<usize>>,
    outbound: Sender<usize>,
    put_back: Sender<Vec<usize>>,
    last: bool,
) {
    let p = Protocol { stream };
    let mut c = Coordinator {
        stage_id,
        task_pool,
        protocol_server: p,
        inbound,
        outbound,
        put_back,
        last,
    };
    c.run();
}

pub fn start_listener(
    stage_id: usize,
    path: PathBuf,
    task_pool: Arc<Mutex<TaskPool>>,
    inbound: Receiver<Vec<usize>>,
    outbound: Sender<usize>,
    put_back: Sender<Vec<usize>>,
    last: bool,
) {
    info!(
        "start workload listener @ stage-{} at: {:?}",
        stage_id, path
    );

    let unix_listener = UnixListener::bind(&path).expect(&path.to_string_lossy());
    for stream in unix_listener.incoming() {
        match stream {
            Ok(stream) => {
                let task_pool = task_pool.clone();
                let inbound = inbound.clone();
                let outbound = outbound.clone();
                let put_back = put_back.clone();
                info!("workload connected @ stage-{}", stage_id);
                thread::spawn(move || {
                    handle_workload(
                        stage_id, stream, task_pool, inbound, outbound, put_back, last,
                    )
                });
            }
            Err(error) => {
                panic!(
                    "workload connection @ stage-{} failed: {:?}",
                    stage_id, error
                );
            }
        }
    }
}
