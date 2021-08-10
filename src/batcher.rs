use crossbeam_channel::{select, tick, Receiver, Sender};
use std::ops::Add;
use std::process;
use std::time::{Duration, Instant};

pub struct Batcher {
    pub limit: usize,       // batch size limit
    pub wait: Duration,     // wait time for batching
    pub interval: Duration, // interval time for ticker
    pub inbound: Receiver<usize>,
    pub outbound: Sender<Vec<usize>>,
}

impl Batcher {
    pub fn run(&self) {
        println!("running batcher...");
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
