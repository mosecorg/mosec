// Copyright 2023 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use std::collections::BTreeMap;
use std::fmt;

use serde::Deserialize;
use utoipa::openapi::request_body::RequestBody;
use utoipa::openapi::{RefOr, Response, Schema};

#[derive(Deserialize, Debug)]
pub(crate) struct Runtime {
    pub max_batch_size: usize,
    pub max_wait_time: u64,
    pub worker: String,
}

#[derive(Deserialize)]
pub(crate) struct Route {
    pub endpoint: String,
    pub workers: Vec<String>,
    pub mime: String,
    pub is_sse: bool,
    pub request_body: Option<RequestBody>,
    pub responses: Option<BTreeMap<String, RefOr<Response>>>,
    pub schemas: Option<BTreeMap<String, RefOr<Schema>>>,
}

impl fmt::Debug for Route {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "({}: [{}], resp({}))",
            self.endpoint,
            self.workers.join(", "),
            self.mime
        )
    }
}

#[derive(Deserialize, Debug)]
pub(crate) struct Config {
    // socket dir
    pub path: String,
    // channel capacity
    pub capacity: usize,
    // service timeout (ms)
    pub timeout: u64,
    // service address
    pub address: String,
    // service port
    pub port: u16,
    // metrics namespace
    pub namespace: String,
    // log level: (debug, info, warning, error)
    pub log_level: String,
    pub runtimes: Vec<Runtime>,
    pub routes: Vec<Route>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            path: String::from("/tmp/mosec"),
            capacity: 1024,
            timeout: 3000,
            address: String::from("0.0.0.0"),
            port: 8000,
            namespace: String::from("mosec_service"),
            log_level: String::from("info"),
            runtimes: vec![Runtime {
                max_batch_size: 64,
                max_wait_time: 3000,
                worker: String::from("Inference_1"),
            }],
            routes: vec![Route {
                endpoint: String::from("/inference"),
                workers: vec![String::from("Inference_1")],
                mime: String::from("application/json"),
                is_sse: false,
                request_body: None,
                responses: None,
                schemas: None,
            }],
        }
    }
}
