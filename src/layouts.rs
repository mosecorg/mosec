use logforth::kv::{Key, Value, Visitor};
use logforth::layout::text::colored::{Color, ColoredString, Colorize};
use logforth::record::{Level, Record};
use logforth::{Diagnostic, Error};
use serde::Serialize;
use serde_json::Map;

#[derive(Debug)]
pub(crate) struct ColoredLayout;

impl logforth::Layout for ColoredLayout {
    fn format(&self, record: &Record, diags: &[Box<dyn Diagnostic>]) -> Result<Vec<u8>, Error> {
        let ts = jiff::Timestamp::try_from(record.time()).unwrap();

        let level = ColoredString::from(record.level().to_string()).color(match record.level() {
            Level::Fatal | Level::Fatal2 | Level::Fatal3 | Level::Fatal4 => Color::BrightRed,
            Level::Error | Level::Error2 | Level::Error3 | Level::Error4 => Color::Red,
            Level::Warn | Level::Warn2 | Level::Warn3 | Level::Warn4 => Color::Yellow,
            Level::Info | Level::Info2 | Level::Info3 | Level::Info4 => Color::Green,
            Level::Debug | Level::Debug2 | Level::Debug3 | Level::Debug4 => Color::Blue,
            Level::Trace | Level::Trace2 | Level::Trace3 | Level::Trace4 => Color::Magenta,
        });

        let target = record.target();
        let line = record.line().unwrap_or_default();
        let message = record.payload();

        struct KvWriter(String);

        impl Visitor for KvWriter {
            fn visit(&mut self, key: Key, value: Value) -> Result<(), Error> {
                use std::fmt::Write;
                // SAFETY: write to a string always succeeds
                write!(&mut self.0, " {key}={value}").unwrap();
                Ok(())
            }
        }

        let mut visitor = KvWriter(format!("{ts:.6} {level:>6} {target}:{line} {message}"));
        record.key_values().visit(&mut visitor)?;
        for d in diags {
            d.visit(&mut visitor)?;
        }

        Ok(visitor.0.into_bytes())
    }
}

#[derive(Debug)]
pub(crate) struct JsonLayout;

impl logforth::Layout for JsonLayout {
    fn format(&self, record: &Record, diags: &[Box<dyn Diagnostic>]) -> Result<Vec<u8>, Error> {
        let diagnostics = diags;

        let ts = jiff::Timestamp::try_from(record.time()).unwrap();

        struct FieldsVisitor(Map<String, serde_json::Value>);

        impl Visitor for FieldsVisitor {
            fn visit(&mut self, key: Key, value: Value) -> Result<(), Error> {
                let key = key.to_string();
                match serde_json::to_value(&value) {
                    Ok(value) => self.0.insert(key, value),
                    Err(_) => self.0.insert(key, value.to_string().into()),
                };
                Ok(())
            }
        }

        let mut visitor = FieldsVisitor(Map::new());
        visitor.visit(Key::new("message"), record.payload().into())?;
        record.key_values().visit(&mut visitor)?;
        for d in diagnostics {
            d.visit(&mut visitor)?;
        }

        #[derive(Debug, Clone, Serialize)]
        struct RecordLine<'a> {
            timestamp: String,
            level: &'a str,
            target: String,
            #[serde(skip_serializing_if = "Map::is_empty")]
            fields: Map<String, serde_json::Value>,
        }

        let record_line = RecordLine {
            timestamp: format!("{ts:.6}"),
            level: record.level().name(),
            target: format!("{}:{}", record.target(), record.line().unwrap_or_default(),),
            fields: visitor.0,
        };

        Ok(serde_json::to_vec(&record_line).unwrap())
    }
}
