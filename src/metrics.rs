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

use std::sync::OnceLock;

use prometheus_client::encoding::EncodeLabelSet;
use prometheus_client::metrics::counter::Counter;
use prometheus_client::metrics::family::{Family, MetricConstructor};
use prometheus_client::metrics::gauge::Gauge;
use prometheus_client::metrics::histogram::{exponential_buckets, Histogram};
use prometheus_client::registry::Registry;

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
pub struct CodeLabel {
    pub code: u16,
    pub endpoint: String,
}

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
pub struct StageConnectionLabel {
    pub stage: String,
    pub connection: String,
}

#[derive(Debug)]
pub(crate) struct Metrics {
    pub(crate) throughput: Family<CodeLabel, Counter>,
    pub(crate) duration: Family<StageConnectionLabel, Histogram, CustomHistogramBuilder>,
    pub(crate) batch_size: Family<StageConnectionLabel, Histogram>,
    pub(crate) batch_duration: Family<StageConnectionLabel, Histogram>,
    pub(crate) remaining_task: Gauge,
}

#[derive(Clone)]
pub(crate) struct CustomHistogramBuilder {
    length: u16,
}

impl MetricConstructor<Histogram> for CustomHistogramBuilder {
    fn new_metric(&self) -> Histogram {
        // When a new histogram is created, this function will be called.
        Histogram::new(exponential_buckets(1e-3f64, 2f64, self.length))
    }
}

impl Metrics {
    pub(crate) fn global() -> &'static Metrics {
        METRICS.get().expect("Metrics is not initialized")
    }

    pub(crate) fn new(timeout: u64) -> Self {
        let builder = CustomHistogramBuilder {
            length: (timeout as f64).log2().ceil() as u16 + 1,
        };
        Self {
            throughput: Family::<CodeLabel, Counter>::default(),
            duration:
                Family::<StageConnectionLabel, Histogram, CustomHistogramBuilder>::new_with_constructor(
                    builder,
                ), // 1ms ~ 4.096s (default)
            batch_size: Family::<StageConnectionLabel, Histogram>::new_with_constructor(|| {
                Histogram::new(exponential_buckets(1f64, 2f64, 10)) // 1 ~ 512
            }),
            batch_duration: Family::<StageConnectionLabel, Histogram>::new_with_constructor(|| {
                Histogram::new(exponential_buckets(1e-3f64, 2f64, 13)) // 1ms ~ 4.096s
            }),
            remaining_task: Gauge::default(),
        }
    }

    pub(crate) fn init_with_namespace(namespace: &str, timeout: u64) -> Self {
        DURATION_LABEL
            .set(StageConnectionLabel {
                stage: "total".to_string(),
                connection: "total".to_string(),
            })
            .unwrap();
        let mut registry = <Registry>::default();
        let metrics = Metrics::new(timeout);
        registry.register(
            format!("{namespace}_throughput"),
            "service inference endpoint throughput",
            metrics.throughput.clone(),
        );
        registry.register(
            format!("{namespace}_process_duration_second"),
            "process duration for each connection in each stage",
            metrics.duration.clone(),
        );
        registry.register(
            format!("{namespace}_batch_size"),
            "batch size for each connection in each stage",
            metrics.batch_size.clone(),
        );
        registry.register(
            format!("{namespace}_batch_duration_second"),
            "dynamic batching duration for each connection in each stage",
            metrics.batch_duration.clone(),
        );
        registry.register(
            format!("{namespace}_remaining_task"),
            "remaining tasks for the whole service",
            metrics.remaining_task.clone(),
        );
        REGISTRY.set(registry).unwrap();
        metrics
    }
}

pub(crate) static METRICS: OnceLock<Metrics> = OnceLock::new();
pub(crate) static REGISTRY: OnceLock<Registry> = OnceLock::new();
pub(crate) static DURATION_LABEL: OnceLock<StageConnectionLabel> = OnceLock::new();
