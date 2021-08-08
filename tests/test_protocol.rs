use bytes::Bytes;
use mosec::protocol;
use std::os::unix::net::{SocketAddr, UnixListener, UnixStream};
use std::{fs, thread};

const TEST_PATH: &str = "/tmp/mosec_test";
const TEST_FLAG: u16 = protocol::FLAG_OK;
const TEST_IDS: [usize; 2] = [1, 2];
const TEST_PAYLOADS: [&str; 2] = ["test1", "imageb64str"];

#[test]
fn test_protocol_echo() {
    let _ = fs::remove_file(TEST_PATH);
    let listener = UnixListener::bind(TEST_PATH).unwrap();
    let addr = listener.local_addr().unwrap();
    println!("socket address: {:#?}", addr.clone());

    let handle = thread::spawn(|| protocol_client_send(addr));
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                /* handle the communication between PY side protocol-client */
                thread::spawn(move || handle_protocol_client(stream));
                break;
            }
            Err(err) => {
                /* connection failed */
                println!("connection failed: {:?}", &err);
                break;
            }
        }
    }
    handle.join().unwrap();
}

fn protocol_client_send(addr: SocketAddr) {
    let stream = UnixStream::connect(addr.as_pathname().unwrap()).unwrap();
    let mut pc = protocol::Protocol { stream }; // protocol-client
    pc.send(
        TEST_FLAG,
        &TEST_IDS.to_vec(),
        &TEST_PAYLOADS.iter().map(|x| Bytes::from(*x)).collect(),
    )
    .unwrap();
}

fn handle_protocol_client(stream: UnixStream) {
    println!("new connection");
    let mut ps = protocol::Protocol { stream }; // protocol-server
    let mut flag = 0;
    let mut ids = vec![];
    let mut payloads = vec![];
    ps.receive(&mut flag, &mut ids, &mut payloads).unwrap();
    assert_eq!(flag, TEST_FLAG);
    for (i, (id, payload)) in ids.iter().zip(payloads.iter()).enumerate() {
        assert_eq!(*id, TEST_IDS[i]);
        assert_eq!(*payload, TEST_PAYLOADS[i]);
    }
    println!("{:?}, {:?}, {:?}", flag, ids, payloads);
}
