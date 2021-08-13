use std::sync::{Arc, Mutex};
use std::thread;

use bytes::Bytes;
use crossbeam_channel::bounded;
use mosec::pool;

const CONCURRENCY: usize = 20;

#[test]
fn add_new_task() {
    let tp = pool::TaskPool::new();
    let (cancel_tx, cancel_rx) = bounded(1);
    let (id, result_rx) = pool::init_task(&tp, Bytes::from("my_task"), cancel_rx).unwrap();
    let res = pool::get_task(&tp, id).unwrap();
    assert_eq!(res.data, Bytes::from("my_task"));
}

#[test]
fn add_new_task_multi_thread() {
    let tp = pool::TaskPool::new();
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
            let (id, result_rx) =
                pool::init_task(&tp, Bytes::from(data.clone()), cancel_rx).unwrap();
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
        let task = pool::get_task(&tp, id).unwrap();
        assert_eq!(task.data, Bytes::from(datum[i].clone()));
    }
    println!("{:?}", tp);
}

#[test]
fn update_task_multi_thread() {
    let tp = pool::TaskPool::new();
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
            let (id, result_rx) =
                pool::init_task(&tp, Bytes::from(data.clone()), cancel_rx).unwrap();
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
        let task = pool::get_task(&tp, tid).unwrap();
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
            let id = pool::update_task(
                &tp,
                tid,
                Bytes::from(update_data),
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
        let task = pool::get_task(&tp, tid).unwrap();
        assert_eq!(task.data, Bytes::from(update_datum[i].clone()));
    }
    println!("{:?}", tp);
}
