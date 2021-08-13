use std::sync::{Arc, Mutex};

use crossbeam_channel::{Receiver, Sender, TryRecvError};

use crate::{
    pool::{self, TaskPool, TaskStatusCode},
    protocol::*,
};

pub struct Coordinator {
    pub task_pool: Arc<Mutex<TaskPool>>,
    pub protocol_server: Protocol,     // server side of uds stream
    pub inbound: Receiver<Vec<usize>>, // symmetrical to batcher.rs
    pub outbound: Sender<usize>,       // (maybe) multiple input, single output
    pub last: bool,                    // indication of last stage
}

impl Coordinator {
    pub fn run(&self) {
        println!("running coordinator...");
        loop {
            // get ids from batcher, fetch data, send to workload
            let req_ids = self.inbound.recv().expect("coordinator inbound recv error");
            let mut req_payloads = Vec::new();
            let mut completes = Vec::new();
            let mut cancels = Vec::new();
            for id in req_ids {
                let task = pool::get_task(&self.task_pool, id).unwrap();
                match task.cancel.try_recv() {
                    Ok(_) => continue,
                    Err(TryRecvError::Disconnected) => panic!("cancel channel disconnected"), // TODO: handle error
                    Err(TryRecvError::Empty) => {
                        // not canceled (e.g. due to timeout) yet
                        req_payloads.push(task.data.clone());
                        completes.push(task.complete.clone());
                        cancels.push(task.cancel.clone());
                    }
                }
            }
            self.protocol_server
                .send(FLAG_OK as u16, &req_ids, &req_payloads)
                .unwrap();

            // get from workload, store data, send to next batcher or return result (after status check)
            let mut flag = FLAG_OK;
            let mut resp_ids = Vec::new();
            let mut resp_payloads = Vec::new();
            self.protocol_server
                .receive(&mut flag, &mut resp_ids, &mut resp_payloads)
                .unwrap();
            let status = match flag {
                FLAG_OK => TaskStatusCode::Normal,
                FLAG_BAD_REQUEST => TaskStatusCode::ValidationError,
                FLAG_VALIDATION_ERROR => TaskStatusCode::ValidationError,
                FLAG_INTERNAL_ERROR => TaskStatusCode::InternalError,
            };
            for i in 0..resp_ids.len() {
                let id = resp_ids[i];
                let data = resp_payloads[i];
                let complete = completes[i];
                let cancel = cancels[i];
                pool::update_task(&self.task_pool, id, data, status, complete, cancel);
                // early stop if any error occurs at current stage
                if flag != FLAG_OK || self.last {
                    complete.send(id);
                } else {
                    self.outbound.send(id);
                }
            }
        }
    }
}
