use std::ops::Add;
use std::process;
use std::time::{Duration, Instant};

use crossbeam_channel::{select, tick, Receiver, Sender};
use tracing::info;

struct Batcher {
    limit: usize,                 // batch size limit
    wait: Duration,               // wait time for batching
    interval: Duration,           // interval time for ticker
    inbound: Receiver<usize>,     // symmetrical to coordinator.rs
    outbound: Sender<Vec<usize>>, // single input, (maybe) multiple output
}

impl Batcher {
    pub fn run(&self) {
        let mut deadline = Instant::now().add(self.wait);
        let ticker = tick(self.interval);
        loop {
            let mut count = 0;
            let mut batch = Vec::new();
            while (count < 1) || (count < self.limit && Instant::now().lt(&deadline)) {
                select! {
                    recv(self.inbound) -> msg => {
                        match msg {
                            Ok(id) => {
                                batch.push(id);
                                count += 1;
                            },
                            Err(error) => {
                                eprintln!("Batcher error: {:?}", error);
                                process::exit(0); // TODO: graceful shutdown
                            }
                        }
                    },
                    recv(ticker) -> _ => continue
                }
                if count == 1 {
                    deadline = Instant::now().add(self.wait);
                }
            }
            self.outbound
                .send(batch)
                .expect("Batcher error: unable to send");
        }
    }
}

pub fn start_batcher(
    stage_id: usize,
    limit: usize,
    wait: Duration,
    interval: Duration,
    inbound: Receiver<usize>,
    outbound: Sender<Vec<usize>>,
) {
    info!("start batcher @ stage-{} with size {}", stage_id, limit);
    let b = Batcher {
        limit,
        wait,
        interval,
        inbound,
        outbound,
    };
    b.run();
}
