use crossbeam_channel;
use mosec::batcher;
use std::thread;
use std::time::Duration;

const TIME_DOWNSCALE: u64 = 10;

#[test]
fn batching() {
    let (web_tx, web_rx) = crossbeam_channel::unbounded();
    let (s1_tx, s1_rx) = crossbeam_channel::unbounded();

    let b = batcher::Batcher {
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
