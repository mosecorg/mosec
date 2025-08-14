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

//! Conditional sync primitives for std or loom testing

#[cfg(all(test, feature = "loom_tests"))]
pub use loom::sync::{Arc, Mutex};

#[cfg(not(all(test, feature = "loom_tests")))]
pub use std::sync::{Arc, Mutex};

// These are not modeled by loom, so we always use std versions
pub use std::sync::{atomic::AtomicBool, atomic::Ordering, OnceLock};