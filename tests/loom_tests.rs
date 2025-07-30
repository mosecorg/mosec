// Tests specifically for loom testing - isolated from main dependencies
// This avoids conflicts with dependencies that don't support loom

#[cfg(loom)]
mod loom_tests {
    use std::collections::HashMap;
    use loom::sync::{Arc, Mutex};
    use loom::thread;

    // Simplified Task structure for testing
    #[derive(Debug, Clone)]
    struct SimpleTask {
        id: u32,
    }

    /// Test the specific locking patterns that can cause deadlocks in TaskManager
    /// This reproduces the notify_task_done vs delete_task deadlock scenario
    #[test]
    fn loom_concurrent_notify_delete_pattern() {
        loom::model(|| {
            // Replicate the two mutexes from TaskManager that are problematic
            let notifiers = Arc::new(Mutex::new(HashMap::<u32, bool>::new()));
            let table = Arc::new(Mutex::new(HashMap::<u32, SimpleTask>::new()));
            
            // Setup initial state
            {
                let mut notifiers_guard = notifiers.lock().unwrap();
                let mut table_guard = table.lock().unwrap();
                notifiers_guard.insert(0, true);
                table_guard.insert(0, SimpleTask { id: 0 });
            }
            
            let notifiers1 = notifiers.clone();
            let table1 = table.clone();
            let notifiers2 = notifiers.clone();
            let table2 = table.clone();

            // Thread 1: Simulate notify_task_done locking pattern
            let handle1 = thread::spawn(move || {
                // First lock notifiers
                let res = {
                    let mut notifiers = notifiers1.lock().unwrap();
                    notifiers.remove(&0)
                };
                // Then conditionally lock table (when sender is closed)
                if res.is_some() {
                    let mut table = table1.lock().unwrap();
                    table.remove(&0);
                }
            });

            // Thread 2: Simulate delete_task locking pattern  
            let handle2 = thread::spawn(move || {
                // First lock notifiers
                {
                    let mut notifiers = notifiers2.lock().unwrap();
                    notifiers.remove(&0);
                }
                // Then lock table
                {
                    let mut table = table2.lock().unwrap();
                    table.remove(&0);
                }
            });

            handle1.join().unwrap();
            handle2.join().unwrap();
        });
    }

    /// Test the table->notifiers vs notifiers->table lock ordering deadlock
    #[test]
    fn loom_concurrent_lock_ordering() {
        loom::model(|| {
            let notifiers = Arc::new(Mutex::new(HashMap::<u32, bool>::new()));
            let table = Arc::new(Mutex::new(HashMap::<u32, SimpleTask>::new()));
            
            let notifiers1 = notifiers.clone();
            let table1 = table.clone();
            let notifiers2 = notifiers.clone();
            let table2 = table.clone();

            // Thread 1: table -> notifiers order
            let handle1 = thread::spawn(move || {
                let _table = table1.lock().unwrap();
                let _notifiers = notifiers1.lock().unwrap();
            });

            // Thread 2: notifiers -> table order (potential deadlock)
            let handle2 = thread::spawn(move || {
                let _notifiers = notifiers2.lock().unwrap();
                let _table = table2.lock().unwrap();
            });

            handle1.join().unwrap();
            handle2.join().unwrap();
        });
    }
}