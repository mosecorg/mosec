// Copyright 2022 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use clap::Parser;

#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
pub(crate) struct Opts {
    /// Unix domain socket directory path
    #[clap(long, default_value = "")]
    pub(crate) path: String,

    /// batch size for each stage
    #[clap(short, long, default_values = &["1", "8", "1"])]
    pub(crate) batches: Vec<u32>,

    /// capacity for the channel
    /// (when the channel is full, the new requests will be dropped with 429 Too Many Requests)
    #[clap(short, long, default_value = "1024")]
    pub(crate) capacity: usize,

    /// timeout for one request (milliseconds)
    #[clap(short, long, default_value = "3000")]
    pub(crate) timeout: u64,

    /// wait time for each batch (milliseconds)
    #[clap(short, long, default_value = "10")]
    pub(crate) wait: u64,

    /// service host
    #[clap(short, long, default_value = "0.0.0.0")]
    pub(crate) address: String,

    /// service port
    #[clap(short, long, default_value = "8000")]
    pub(crate) port: u16,

    /// metrics namespace
    #[clap(short, long, default_value = "mosec_service")]
    pub(crate) namespace: String,
}
