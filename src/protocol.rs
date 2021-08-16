use std::{
    io::{self, Read, Write},
    os::unix::net::UnixStream,
    usize,
};

use bytes::Bytes;

const LENGTH_TASK_FLAG: usize = 2;
const LENGTH_TASK_BATCH: usize = 2;
const LENGTH_TASK_ID: usize = 4;
const LENGTH_TASK_BODY_LEN: usize = 4;

pub const FLAG_OK: u16 = 1; // 200
pub const FLAG_BAD_REQUEST: u16 = 2; // 400
pub const FLAG_VALIDATION_ERROR: u16 = 4; // 422
pub const FLAG_INTERNAL_ERROR: u16 = 8; // 500

#[derive(Debug)]
pub struct Protocol {
    pub stream: UnixStream,
}

impl Protocol {
    // TODO: Bytes facilitates zero-copy, may optimize on this
    pub fn receive(
        &mut self,
        flag: &mut u16,
        ids: &mut Vec<usize>,
        payloads: &mut Vec<Bytes>,
    ) -> io::Result<()> {
        let mut flag_buf = [0; LENGTH_TASK_FLAG];
        let mut bs_buf = [0; LENGTH_TASK_BATCH];
        self.stream.read_exact(&mut flag_buf)?;
        self.stream.read_exact(&mut bs_buf)?;
        *flag = u16::from_be_bytes(flag_buf);
        let mut bs = u16::from_be_bytes(bs_buf);

        while bs > 0 {
            bs -= 1;
            let mut id_buf = [0; LENGTH_TASK_ID];
            let mut len_buf = [0; LENGTH_TASK_BODY_LEN];
            self.stream.read_exact(&mut id_buf)?;
            self.stream.read_exact(&mut len_buf)?;
            let id = u32::from_be_bytes(id_buf) as usize;
            let len = u32::from_be_bytes(len_buf) as usize;
            let mut buffer = vec![0u8; len];
            let mut payload_buf = &mut buffer[..];
            self.stream.read_exact(&mut payload_buf)?;
            ids.push(id);
            payloads.push(Bytes::from(payload_buf.to_vec()));
        }
        Ok(())
    }

    pub fn send(&mut self, flag: u16, ids: &Vec<usize>, payloads: &Vec<Bytes>) -> io::Result<()> {
        let mut buffer: Vec<u8> = Vec::new();
        let flag_buf = u16::to_be_bytes(flag);
        buffer.extend_from_slice(&flag_buf);
        let bs = ids.len() as u16;
        let bs_buf = u16::to_be_bytes(bs);
        buffer.extend_from_slice(&bs_buf);
        if bs > 0 {
            for (id, payload) in ids.iter().zip(payloads.iter()) {
                let id_buf = u32::to_be_bytes(*id as u32);
                let len_buf = u32::to_be_bytes(payload.len() as u32);
                buffer.extend_from_slice(&id_buf);
                buffer.extend_from_slice(&len_buf);
                buffer.extend_from_slice(&payload.to_vec());
            }
        }
        self.stream.write_all(&buffer[..])?;
        Ok(())
    }
}

#[cfg(test)]
mod test_protocol {
    use std::os::unix::net::{SocketAddr, UnixListener, UnixStream};
    use std::{fs, path::Path, thread};

    use bytes::Bytes;

    use super::*;

    const TEST_PATH: &str = "/tmp/mosec_test";
    const TEST_FLAG: u16 = FLAG_OK;
    const TEST_IDS: [usize; 2] = [1, 2];
    const TEST_PAYLOADS: [&str; 2] = ["test1", "imageb64str"];

    #[test]
    fn test_protocol_echo() {
        let path = Path::new(TEST_PATH);
        if path.exists() {
            fs::remove_file(path).unwrap();
        }
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
        let mut pc = Protocol { stream }; // protocol-client
        pc.send(
            TEST_FLAG,
            &TEST_IDS.to_vec(),
            &TEST_PAYLOADS.iter().map(|x| Bytes::from(*x)).collect(),
        )
        .unwrap();
    }

    fn handle_protocol_client(stream: UnixStream) {
        println!("new connection");
        let mut ps = Protocol { stream }; // protocol-server
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
}
