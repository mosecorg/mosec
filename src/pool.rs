use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

use bytes::Bytes;
use crossbeam_channel::{bounded, Receiver, Sender};

use crate::errors;

#[derive(Debug, Clone, Copy)]
pub enum TaskStatusCode {
    Normal,
    ValidationError,
    InternalError,
    UnknownError,
}

#[derive(Debug, Clone)]
pub struct Task {
    // task info
    pub status: TaskStatusCode,
    pub data: Bytes,

    // notifiers
    pub complete: Sender<usize>,
    pub cancel: Receiver<()>,
}

#[derive(Debug)]
pub struct TaskPool {
    tasks: HashMap<usize, Task>,
    total_count: usize,
}

impl TaskPool {
    pub fn new() -> Arc<Mutex<Self>> {
        let map: HashMap<usize, Task> = HashMap::new();
        Arc::new(Mutex::new(TaskPool {
            tasks: map,
            total_count: 1,
        }))
    }
    fn put(
        &mut self,
        tid: usize,
        data: Bytes,
        status: TaskStatusCode,
        complete: Sender<usize>,
        cancel: Receiver<()>,
    ) -> Result<usize, errors::MosecError> {
        let mut id = tid;
        if tid == 0 {
            // initialize a task, or otherwise reuse the task id
            id = self.total_count;
            self.total_count = self.total_count.wrapping_add(1);
            if self.total_count == 0 {
                self.total_count += 1;
            }
        }
        match self.tasks.insert(
            id,
            Task {
                status,
                data,
                complete,
                cancel,
            },
        ) {
            None => Ok(id),
            Some(_) => Err(errors::MosecError::TaskAlreadyExistsError),
        }
    }
    fn get(&mut self, id: usize) -> Result<Task, errors::MosecError> {
        match self.tasks.remove(&id) {
            Some(task) => Ok(task),
            None => Err(errors::MosecError::TaskNotFoundError),
        }
    }
}

pub fn init_task(
    tp: &Arc<Mutex<TaskPool>>,
    data: Bytes,
    cancel: Receiver<()>,
) -> Result<(usize, Receiver<usize>), errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    let (final_tx, result_rx) = bounded(1);
    match tp.put(0, data, TaskStatusCode::UnknownError, final_tx, cancel) {
        Ok(id) => Ok((id, result_rx)),
        Err(error) => Err(error),
    }
}

pub fn update_task(
    tp: &Arc<Mutex<TaskPool>>,
    tid: usize,
    data: Bytes,
    status: TaskStatusCode,
    complete: Sender<usize>,
    cancel: Receiver<()>,
) -> Result<usize, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.put(tid, data, status, complete, cancel)
}

pub fn update_task_batch(
    tp: &Arc<Mutex<TaskPool>>,
    ids: &Vec<usize>,
    datum: Vec<Bytes>,
    status: TaskStatusCode,
    completes: &Vec<Sender<usize>>,
    cancels: Vec<Receiver<()>>,
) -> Result<(), errors::MosecError> {
    for i in 0..ids.len() {
        let tid = ids[i];
        let data = datum[i].clone();
        let complete = completes[i].clone();
        let cancel = cancels[i].clone();
        match update_task(tp, tid, data, status, complete, cancel) {
            Ok(_) => continue,
            Err(error) => return Err(error),
        };
    }
    Ok(())
}

pub fn get_task(tp: &Arc<Mutex<TaskPool>>, id: usize) -> Result<Task, errors::MosecError> {
    let mut tp = tp.lock().unwrap();
    tp.get(id)
}

#[cfg(test)]
mod test_pool {
    use std::sync::{Arc, Mutex};
    use std::thread;

    use bytes::Bytes;
    use crossbeam_channel::bounded;

    use super::{get_task, init_task, update_task, TaskPool, TaskStatusCode};

    const CONCURRENCY: usize = 20;

    #[test]
    fn add_new_task() {
        let tp = TaskPool::new();
        let (cancel_tx, cancel_rx) = bounded(1);
        let (id, result_rx) = init_task(&tp, Bytes::from("my_task"), cancel_rx).unwrap();
        let res = get_task(&tp, id).unwrap();
        assert_eq!(res.data, Bytes::from("my_task"));
    }

    #[test]
    fn add_new_task_multi_thread() {
        let tp = TaskPool::new();
        let mut handles = vec![];
        let ids = Arc::new(Mutex::new(vec![]));
        let datum = Arc::new(Mutex::new(vec![]));
        for i in 0..CONCURRENCY {
            let tp = Arc::clone(&tp);
            let ids = Arc::clone(&ids);
            let datum = Arc::clone(&datum);
            let (cancel_tx, cancel_rx) = bounded(1);
            let handle = thread::spawn(move || {
                let mut data = String::new();
                data.push_str("task");
                data.push_str(&i.to_string());
                let (id, result_rx) = init_task(&tp, Bytes::from(data.clone()), cancel_rx).unwrap();
                let mut map = ids.lock().unwrap();
                map.push(id);
                let mut map = datum.lock().unwrap();
                map.push(data);
            });
            handles.push(handle);
        }
        for handle in handles {
            handle.join().unwrap();
        }

        let datum = datum.lock().unwrap();
        for (i, &id) in ids.lock().unwrap().iter().enumerate() {
            let task = get_task(&tp, id).unwrap();
            assert_eq!(task.data, Bytes::from(datum[i].clone()));
        }
        println!("{:?}", tp);
    }

    #[test]
    fn update_task_multi_thread() {
        let tp = TaskPool::new();
        let mut handles = vec![];
        let ids = Arc::new(Mutex::new(vec![]));
        let datum = Arc::new(Mutex::new(vec![]));
        for i in 0..CONCURRENCY {
            let tp = Arc::clone(&tp);
            let ids = Arc::clone(&ids);
            let datum = Arc::clone(&datum);
            let (cancel_tx, cancel_rx) = bounded(1);
            let handle = thread::spawn(move || {
                let mut data = String::new();
                data.push_str("task");
                data.push_str(&i.to_string());
                let (id, result_rx) = init_task(&tp, Bytes::from(data.clone()), cancel_rx).unwrap();
                let mut map = ids.lock().unwrap();
                map.push(id);
                let mut map = datum.lock().unwrap();
                map.push(data);
            });
            handles.push(handle);
        }
        for handle in handles {
            handle.join().unwrap();
        }

        handles = vec![];
        let update_ids = Arc::new(Mutex::new(vec![]));
        let update_datum = Arc::new(Mutex::new(vec![]));
        let datum = datum.lock().unwrap();
        for (i, &tid) in ids.lock().unwrap().iter().enumerate() {
            // correctness check
            let task = get_task(&tp, tid).unwrap();
            assert_eq!(task.data, Bytes::from(datum[i].clone()));

            // update
            let tp = Arc::clone(&tp);
            let update_ids = Arc::clone(&update_ids);
            let update_datum = Arc::clone(&update_datum);
            let handle = thread::spawn(move || {
                let mut update_data = String::new();
                update_data.push_str("updated");
                update_data.push_str(&i.to_string());
                let mut map = update_datum.lock().unwrap();
                map.push(update_data.clone());
                let id = update_task(
                    &tp,
                    tid,
                    Bytes::from(update_data),
                    TaskStatusCode::Normal,
                    task.complete,
                    task.cancel,
                )
                .unwrap();
                assert_eq!(id, tid);
                let mut map = update_ids.lock().unwrap();
                map.push(id);
            });
            handles.push(handle);
        }
        for handle in handles {
            handle.join().unwrap();
        }

        let update_datum = update_datum.lock().unwrap();
        for (i, &tid) in update_ids.lock().unwrap().iter().enumerate() {
            // correctness check
            let task = get_task(&tp, tid).unwrap();
            assert_eq!(task.data, Bytes::from(update_datum[i].clone()));
        }
        println!("{:?}", tp);
    }
}
