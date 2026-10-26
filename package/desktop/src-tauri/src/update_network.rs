//! Shared transport policy for signed portable and installer updates.
use futures_util::{stream::FuturesUnordered, StreamExt};
use std::{future::Future, time::Duration};

// Keep aligned with the official download page. Only rewrite this project's
// GitHub release URLs; custom/test endpoints must never be sent to a mirror.
const RELEASE_ROOT: &str = "https://github.com/LC044/TrailSnap/releases/";
const MIRRORS: [&str; 2] = ["https://gh-proxy.com/", "https://gh-proxy.at9.net/"];
pub const ROUNDS: usize = 2;
pub const CATALOG_TIMEOUT: Duration = Duration::from_secs(8);
pub const IDLE_TIMEOUT: Duration = Duration::from_secs(20);

pub fn candidates(url: &str) -> Vec<String> {
    let original = MIRRORS
        .iter()
        .find_map(|prefix| url.strip_prefix(prefix))
        .unwrap_or(url);
    if !original.starts_with(RELEASE_ROOT) {
        return vec![url.to_owned()];
    }
    std::iter::once(original.to_owned())
        .chain(MIRRORS.iter().map(|prefix| format!("{prefix}{original}")))
        .collect()
}

pub fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .user_agent("TrailSnap-Updater")
        .connect_timeout(Duration::from_secs(5))
        .read_timeout(IDLE_TIMEOUT)
        .build()
        .map_err(|e| e.to_string())
}

pub async fn backoff(round: usize) {
    if round > 0 {
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
}

/// Race real catalog requests, including parsing/validation. A fast HTML error
/// page must not win over a slower valid manifest. Dropping pending futures
/// cancels the losing requests rather than waiting for GitHub to time out.
pub async fn first_valid<T, F, Fut>(sources: &[String], attempt: F) -> Result<T, String>
where
    F: Fn(String) -> Fut,
    Fut: Future<Output = Result<T, String>>,
{
    let mut errors = Vec::new();
    for round in 0..ROUNDS {
        backoff(round).await;
        let mut pending: FuturesUnordered<_> =
            sources.iter().map(|url| attempt(url.clone())).collect();
        while let Some(result) = pending.next().await {
            match result {
                Ok(value) => return Ok(value),
                Err(error) => errors.push(error),
            }
        }
    }
    Err(format!(
        "所有更新源均失败（已自动重试），请稍后重试：{}",
        errors.join("；")
    ))
}

/// Probe headers using a one-byte range, never download multiple full archives.
/// Successful sources are ordered by response latency; failed probes stay as
/// fallbacks (some release hosts do not support Range).
pub async fn rank(sources: Vec<String>) -> Vec<String> {
    if sources.len() < 2 {
        return sources;
    }
    let Ok(client) = client() else {
        return sources;
    };
    let mut pending: FuturesUnordered<_> = sources
        .iter()
        .map(|url| {
            let client = client.clone();
            async move {
                let ok = client
                    .get(url)
                    .header(reqwest::header::RANGE, "bytes=0-0")
                    .timeout(Duration::from_secs(4))
                    .send()
                    .await
                    .is_ok_and(|response| response.status().is_success());
                (url.clone(), ok)
            }
        })
        .collect();
    let mut ranked = Vec::new();
    while let Some((url, ok)) = pending.next().await {
        if ok {
            ranked.push(url);
        }
    }
    for url in &sources {
        if !ranked.contains(url) {
            ranked.push(url.clone());
        }
    }
    ranked
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn only_project_release_urls_are_mirrored_without_nested_prefixes() {
        let url = format!("{RELEASE_ROOT}download/v1.0.0/TrailSnap.zip");
        let sources = candidates(&url);
        assert_eq!(sources.len(), 3);
        assert_eq!(candidates(&sources[1]), sources);
        for custom in [
            "http://127.0.0.1:1234/test",
            "https://example.com/latest.json",
            "https://github.com/other/repo/releases/latest",
            "https://github.com/LC044/TrailSnap/releases.evil/a",
        ] {
            assert_eq!(candidates(custom), vec![custom]);
        }
    }

    #[tokio::test]
    async fn slow_source_and_invalid_catalog_do_not_block_valid_source() {
        let sources = vec!["slow".into(), "html".into(), "valid".into()];
        let result = tokio::time::timeout(
            Duration::from_millis(200),
            first_valid(&sources, |url| async move {
                match url.as_str() {
                    "slow" => {
                        std::future::pending::<()>().await;
                        unreachable!()
                    }
                    "html" => Err("invalid JSON".into()),
                    _ => Ok(42),
                }
            }),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(result, 42);
    }

    #[tokio::test]
    async fn retries_are_bounded_and_transient_failure_recovers() {
        let count = AtomicUsize::new(0);
        let sources = vec!["test".into()];
        let value = first_valid(&sources, |_| async {
            if count.fetch_add(1, Ordering::SeqCst) == 0 {
                Err("offline".into())
            } else {
                Ok(7)
            }
        })
        .await
        .unwrap();
        assert_eq!(value, 7);
        count.store(0, Ordering::SeqCst);
        assert!(first_valid::<(), _, _>(&sources, |_| async {
            count.fetch_add(1, Ordering::SeqCst);
            Err("offline".into())
        })
        .await
        .unwrap_err()
        .contains("已自动重试"));
        assert_eq!(count.load(Ordering::SeqCst), ROUNDS);
    }
}
