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

use once_cell::sync::OnceCell;
use prometheus::{
    exponential_buckets, register_histogram_vec, register_int_counter_vec, register_int_gauge,
    HistogramVec, IntCounterVec, IntGauge,
};

#[derive(Debug)]
pub(crate) struct Metrics {
    pub(crate) throughput: IntCounterVec,
    pub(crate) duration: HistogramVec,
    pub(crate) batch_size: HistogramVec,
    pub(crate) remaining_task: IntGauge,
}

impl Metrics {
    pub(crate) fn global() -> &'static Metrics {
        METRICS.get().expect("Metrics is not initialized")
    }

    pub(crate) fn init_with_namespace(namespace: &str, timeout: u64) -> Self {
        Self {
            throughput: register_int_counter_vec!(
                format!("{}_throughput", namespace),
                "service inference endpoint throughput",
                &["code"]
            )
            .unwrap(),
            duration: register_histogram_vec!(
                format!("{}_process_duration_second", namespace),
                "process duration for each connection in each stage",
                &["stage", "connection"],
                exponential_buckets(1e-3f64, 2f64, (timeout as f64).log2().ceil() as usize + 1)
                    .unwrap() // 1ms ~ 4.096s (default)
            )
            .unwrap(),
            batch_size: register_histogram_vec!(
                format!("{}_batch_size", namespace),
                "batch size for each connection in each stage",
                &["stage", "connection"],
                exponential_buckets(1f64, 2f64, 10).unwrap() // 1 ~ 512
            )
            .unwrap(),
            remaining_task: register_int_gauge!(
                format!("{}_remaining_task", namespace),
                "remaining tasks for the whole service"
            )
            .unwrap(),
        }
    }
}

pub(crate) static METRICS: OnceCell<Metrics> = OnceCell::new();
