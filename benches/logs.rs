use chrono::Local;
use env_logger::Builder;
use log::LevelFilter;
use std::io::Write;
use tracing;
use tracing_subscriber;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

fn init_default_logger() {
    Builder::new()
        .format(|buf, record| {
            writeln!(
                buf,
                "{} [{}] - {}",
                Local::now().format("%Y-%m-%d %H:%M:%S"),
                record.level(),
                record.args()
            )
        })
        .filter(None, LevelFilter::Info)
        .init();
}

fn init_tracing_logger() {
    if std::env::var("RUST_LOG").is_err() {
        std::env::set_var("RUST_LOG", "info")
    }

    let res = tracing_subscriber::fmt::try_init();
    if res.is_err() {
        println!("Failed to initialize tracing logger: {}", res.err().unwrap());
    }
}

fn default_logs(n: usize) {
    for i in 0..n {
        log::debug!("debug: {}", i);
        log::info!("info: {}", i);
        log::warn!("warn: {}", i);
        log::error!("error: {}", i);
    }
}

fn tracing_logs(n: usize) {
    for i in 0..n {
        tracing::debug!("debug: {}", i);
        tracing::info!("info: {}", i);
        tracing::warn!("warn: {}", i);
        tracing::error!("error: {}", i);
    }
}

fn criterion_benchmark(c: &mut Criterion) {
    init_default_logger();
    init_tracing_logger();
    let mut group = c.benchmark_group("logger");
    for i in [1, 10].iter() {
        group.bench_with_input(BenchmarkId::new("default", i), i, |b, i| {
            b.iter(|| default_logs(*i));
        });
        group.bench_with_input(BenchmarkId::new("tracing", i), i, |b, i| {
            b.iter(|| tracing_logs(*i));
        });
    }
    group.finish();
}

criterion_group!(benches, criterion_benchmark);
criterion_main!(benches);
