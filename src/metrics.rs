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

    pub(crate) fn init_with_namespace(namespace: &str) -> Self {
        Self {
            throughput: register_int_counter_vec!(
                format!("{}_throughput", namespace),
                "service inference endpoint throughput",
                &["code"]
            )
            .unwrap(),
            duration: register_histogram_vec!(
                format!("{}_process_duration_second", namespace),
                "process duration for different stages",
                &["stage", "connection"],
                exponential_buckets(1e-6f64, 4f64, 12).unwrap() // 1us ~ 4.19s
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
                "remaining tasks for each stage"
            )
            .unwrap(),
        }
    }
}

pub(crate) static METRICS: OnceCell<Metrics> = OnceCell::new();
