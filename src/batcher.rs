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

#[cfg(test)]
mod test_batcher {
    use std::thread;
    use std::time::Duration;

    use crossbeam_channel;

    use super::Batcher;

    const TIME_DOWNSCALE: u64 = 10;

    #[test]
    fn batching() {
        let (web_tx, web_rx) = crossbeam_channel::unbounded();
        let (s1_tx, s1_rx) = crossbeam_channel::unbounded();

        let b = Batcher {
            limit: 2,
            wait: Duration::from_millis(3000 / TIME_DOWNSCALE),
            interval: Duration::from_millis(50 / TIME_DOWNSCALE),
            inbound: web_rx,
            outbound: s1_tx,
        };

        thread::spawn(move || b.run());
        web_tx.send(11).unwrap();
        web_tx.send(22).unwrap();
        web_tx.send(33).unwrap();
        assert_eq!(s1_rx.recv(), Ok(vec![11, 22]));
        assert_eq!(s1_rx.recv(), Ok(vec![33]));

        thread::sleep(Duration::from_secs(1));
        for i in 100..106 {
            if i < 102 {
                // first two
                web_tx.send(i).unwrap();
            } else if i < 104 {
                web_tx.send(i).unwrap();
                thread::sleep(Duration::from_millis(3060 / TIME_DOWNSCALE));
            } else {
                web_tx.send(i).unwrap();
                thread::sleep(Duration::from_millis(2900 / TIME_DOWNSCALE));
            }
        }
        assert_eq!(s1_rx.recv(), Ok(vec![100, 101]));
        assert_eq!(s1_rx.recv(), Ok(vec![102]));
        assert_eq!(s1_rx.recv(), Ok(vec![103]));
        assert_eq!(s1_rx.recv(), Ok(vec![104, 105]));
        // no thread join, destroy the txs thus exit batcher
    }
}
