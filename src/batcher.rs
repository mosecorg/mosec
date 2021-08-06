use crossbeam_channel::{self, select, tick};
use std::ops::Add;
use std::process;
use std::time::{Duration, Instant};

pub struct Batcher {
    pub limit: usize,       // batch size limit
    pub wait: Duration,     // wait time for batching
    pub interval: Duration, // interval time for ticker
    pub inbound: crossbeam_channel::Receiver<usize>,
    pub outbound: Vec<crossbeam_channel::Sender<Vec<usize>>>,
}

impl Batcher {
    pub fn run(&self) {
        println!("running batcher...");
        let mut choice = 0;
        let num_outbound = self.outbound.len();
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
                                println!("{:?}", error);
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
            self.outbound[choice].send(batch.clone()).unwrap();
            println!("batched {:?} for downstream-{}", batch, choice);
            // round robin
            choice += 1;
            if choice >= num_outbound {
                choice = 0;
            }
        }
    }
}
