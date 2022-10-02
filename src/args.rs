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

use argh::FromArgs;

#[derive(FromArgs, Debug, PartialEq)]
/// MOSEC arguments
pub(crate) struct Opts {
    /// the Unix domain socket directory path
    #[argh(option, default = "String::from(\"\")")]
    pub(crate) path: String,

    /// batch size for each stage
    #[argh(option)]
    pub(crate) batches: Vec<u32>,

    /// capacity for the channel
    /// (when the channel is full, the new requests will be dropped with 429 Too Many Requests)
    #[argh(option, short = 'c', default = "1024")]
    pub(crate) capacity: usize,

    /// timeout for one request (milliseconds)
    #[argh(option, short = 't', default = "3000")]
    pub(crate) timeout: u64,

    /// wait time for each batch (milliseconds)
    #[argh(option, short = 'w', default = "10")]
    pub(crate) wait: u64,

    /// service host
    #[argh(option, short = 'a', default = "String::from(\"0.0.0.0\")")]
    pub(crate) address: String,

    /// service port
    #[argh(option, short = 'p', default = "8000")]
    pub(crate) port: u16,

    /// metrics namespace
    #[argh(option, short = 'n', default = "String::from(\"mosec_service\")")]
    pub(crate) namespace: String,
}
