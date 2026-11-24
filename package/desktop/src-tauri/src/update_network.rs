//! Shared transport policy for signed portable and installer updates.
use futures_util::{future::select_all, stream::FuturesUnordered, StreamExt};
use reqwest::{header, StatusCode};
use std::{
    cmp::Reverse,
    fs,
    future::Future,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
    time::Duration,
};

// Keep aligned with the official download page. Only rewrite this project's
// GitHub release URLs; custom/test endpoints must never be sent to a mirror.
const RELEASE_ROOT: &str = "https://github.com/LC044/TrailSnap/releases/";
const FIRST_PARTY_RELEASE_ROOT: &str = "https://download.trailsnap.cn/LC044/TrailSnap/releases/";
const LLAMA_RELEASE_ROOT: &str = "https://github.com/ggml-org/llama.cpp/releases/download/";
const MIRRORS: [&str; 2] = ["https://gh-proxy.com/", "https://gh-proxy.at9.net/"];
pub const ROUNDS: usize = 2;
pub const CATALOG_TIMEOUT: Duration = Duration::from_secs(8);
pub const IDLE_TIMEOUT: Duration = Duration::from_secs(20);

pub fn candidates(url: &str) -> Vec<String> {
    let normalized = url
        .strip_prefix(FIRST_PARTY_RELEASE_ROOT)
        .map(|path| format!("{RELEASE_ROOT}{path}"));
    let mut sources = release_sources(normalized.as_deref().unwrap_or(url), RELEASE_ROOT);
    let Some(path) = sources
        .first()
        .and_then(|source| source.strip_prefix(RELEASE_ROOT))
    else {
        return sources;
    };
    let fixed_version = path
        .strip_prefix("download/v")
        .and_then(|path| path.split_once('/'));
    if fixed_version.is_some_and(|(version, asset)| {
        let parts: Vec<_> = version.split('.').collect();
        parts.len() == 3
            && parts
                .iter()
                .all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()))
            && !asset.is_empty()
            && asset.as_bytes()[0].is_ascii_alphanumeric()
            && asset
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
    }) {
        sources.push(format!("{FIRST_PARTY_RELEASE_ROOT}{path}"));
    }
    sources
}

pub fn llama_candidates(url: &str) -> Vec<String> {
    release_sources(url, LLAMA_RELEASE_ROOT)
}

fn release_sources(url: &str, release_root: &str) -> Vec<String> {
    let original = MIRRORS
        .iter()
        .find_map(|prefix| url.strip_prefix(prefix))
        .unwrap_or(url);
    if !original.starts_with(release_root) {
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

pub struct Download<'a> {
    pub destination: &'a Path,
    pub size: Option<u64>,
    pub timeout: Duration,
}

#[derive(Clone, Copy)]
pub enum DownloadMode {
    Single,
    Parallel { sample: Duration },
}

impl DownloadMode {
    pub fn desktop() -> Self {
        match std::env::var("TS_DESKTOP_DOWNLOAD_MODE").as_deref() {
            Ok(value) if value.eq_ignore_ascii_case("single") => Self::Single,
            _ => Self::Parallel {
                sample: Duration::from_secs(30),
            },
        }
    }
}

impl Download<'_> {
    /// Downloads into a caller-owned temporary file and returns only after verification.
    pub async fn verified<T, F, Fut>(
        &self,
        sources: Vec<String>,
        mode: DownloadMode,
        mut progress: impl FnMut(u64, Option<u64>),
        verify: F,
    ) -> Result<T, String>
    where
        F: Fn(PathBuf) -> Fut,
        Fut: Future<Output = Result<T, String>>,
    {
        let client = client()?;
        let sources = rank(sources).await;
        let mut attempts = vec![0; sources.len()];
        let mut last_error = String::new();
        if let DownloadMode::Parallel { sample } = mode {
            if sources.len() > 1 {
                match self
                    .race(
                        &client,
                        &sources,
                        sample,
                        &mut attempts,
                        &mut progress,
                        &verify,
                    )
                    .await
                {
                    Ok(value) => return Ok(value),
                    Err(error) => last_error = error,
                }
            }
        }
        for round in 0..ROUNDS {
            backoff(round).await;
            for (index, source) in sources.iter().enumerate() {
                if attempts[index] > round {
                    continue;
                }
                attempts[index] += 1;
                let mut resume = Resume::default();
                let mut result = self
                    .fetch(&client, source, &mut resume, &mut progress)
                    .await;
                if result.is_err() && resume.can_resume() && attempts[index] < ROUNDS {
                    // Keep one temporary file and only reuse bytes from this source.
                    attempts[index] += 1;
                    backoff(round + 1).await;
                    result = self
                        .fetch(&client, source, &mut resume, &mut progress)
                        .await;
                }
                match result {
                    Ok(()) => match verify(self.destination.to_path_buf()).await {
                        Ok(verified) => return Ok(verified),
                        Err(error) => last_error = error,
                    },
                    Err(error) => last_error = error,
                }
            }
        }
        Err(format!("所有下载源均失败（已自动重试）：{last_error}"))
    }

    async fn race<T, F, Fut>(
        &self,
        client: &reqwest::Client,
        sources: &[String],
        sample: Duration,
        attempts: &mut [usize],
        progress: &mut impl FnMut(u64, Option<u64>),
        verify: &F,
    ) -> Result<T, String>
    where
        F: Fn(PathBuf) -> Fut,
        Fut: Future<Output = Result<T, String>>,
    {
        let parent = self.destination.parent().ok_or("下载目录无效")?;
        // The names also match the portable updater's interrupted-download cleanup.
        let files = RaceFiles(
            (0..sources.len())
                .map(|_| parent.join(format!("download-{}.zip", uuid::Uuid::new_v4())))
                .collect(),
        );
        let samples: Vec<_> = sources.iter().map(|_| Mutex::new((0, self.size))).collect();
        let mut transfers: Vec<_> = sources
            .iter()
            .enumerate()
            .map(|(index, source)| {
                let path = files.path(index);
                let sample = &samples[index];
                Some(Box::pin(async move {
                    let download = self.at(path);
                    let mut resume = Resume::default();
                    let result = download
                        .fetch(client, source, &mut resume, &mut |bytes, total| {
                            *sample.lock().expect("download sample poisoned") = (bytes, total);
                        })
                        .await;
                    (index, resume, result)
                }))
            })
            .collect();
        attempts.fill(1);
        let deadline = tokio::time::Instant::now() + sample;
        let wait = tokio::time::sleep_until(deadline);
        tokio::pin!(wait);
        let mut tick = tokio::time::interval(Duration::from_millis(200));
        tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut visible = 0;
        let mut reported = None;
        let mut selected = false;
        let mut retry: Option<(usize, Resume)> = None;
        let mut last_error = String::new();
        loop {
            let active = transfers.iter().flatten().count();
            if active == 0 {
                break;
            }
            // A pending request may still fail before receiving any bytes. Keep a
            // resumable partial from a failed source until the sample has ended.
            if !selected
                && ((active == 1 && retry.is_none()) || tokio::time::Instant::now() >= deadline)
            {
                // All candidates share the same sampling window. Break ties by header rank.
                visible = (0..sources.len())
                    .filter(|&index| transfers[index].is_some())
                    .max_by_key(|&index| {
                        let (bytes, _) = *samples[index].lock().expect("download sample poisoned");
                        (bytes, Reverse(index))
                    })
                    .expect("active download");
                for (index, transfer) in transfers.iter_mut().enumerate() {
                    if index != visible {
                        *transfer = None;
                    }
                }
                files.discard_except(visible);
                retry = None;
                selected = true;
            } else if transfers[visible].is_none() {
                visible = transfers
                    .iter()
                    .position(Option::is_some)
                    .expect("active download");
            }
            show_race_progress(visible, &samples, &mut reported, progress);
            let (index, resume, result) = tokio::select! {
                ((index, resume, result), _, _) = select_all(transfers.iter_mut().flatten()) => {
                    (index, resume, result)
                },
                _ = tick.tick() => continue,
                _ = &mut wait, if !selected => continue,
            };
            transfers[index] = None;
            match result {
                Ok(()) => {
                    show_race_progress(index, &samples, &mut reported, progress);
                    match verify(files.path(index).to_path_buf()).await {
                        Ok(value) => {
                            drop(transfers);
                            fs::rename(files.path(index), self.destination)
                                .map_err(|e| e.to_string())?;
                            return Ok(value);
                        }
                        Err(error) => last_error = error,
                    }
                }
                Err(error) => {
                    last_error = error;
                    if resume.can_resume()
                        && retry
                            .as_ref()
                            .is_none_or(|(_, prior)| resume.offset > prior.offset)
                    {
                        retry = Some((index, resume));
                    }
                }
            }
        }
        drop(transfers);
        if let Some((index, mut resume)) = retry {
            files.discard_except(index);
            show_race_progress(index, &samples, &mut reported, progress);
            attempts[index] += 1;
            backoff(1).await;
            self.at(files.path(index))
                .fetch(client, &sources[index], &mut resume, progress)
                .await?;
            let value = verify(files.path(index).to_path_buf()).await?;
            fs::rename(files.path(index), self.destination).map_err(|e| e.to_string())?;
            return Ok(value);
        }
        Err(last_error)
    }

    fn at<'a>(&self, destination: &'a Path) -> Download<'a> {
        Download {
            destination,
            size: self.size,
            timeout: self.timeout,
        }
    }

    async fn fetch(
        &self,
        client: &reqwest::Client,
        source: &str,
        resume: &mut Resume,
        progress: &mut impl FnMut(u64, Option<u64>),
    ) -> Result<(), String> {
        tokio::time::timeout(
            self.timeout,
            self.transfer(client, source, resume, progress),
        )
        .await
        .map_err(|_| "下载超时".to_string())?
    }

    async fn transfer(
        &self,
        client: &reqwest::Client,
        source: &str,
        resume: &mut Resume,
        progress: &mut impl FnMut(u64, Option<u64>),
    ) -> Result<(), String> {
        let offset = resume.offset;
        progress(offset, self.size.or(resume.total));
        let full_request = || {
            client
                .get(source)
                .header(header::ACCEPT, "application/octet-stream")
                .header(header::ACCEPT_ENCODING, "identity")
        };
        let mut request = full_request();
        if offset > 0 {
            request = request.header(header::RANGE, format!("bytes={offset}-"));
            if let Some(etag) = &resume.etag {
                request = request.header(header::IF_RANGE, etag.clone());
            }
        }
        let mut response = request.send().await.map_err(|e| e.to_string())?;
        let range_total = if offset > 0 && response.status() == StatusCode::PARTIAL_CONTENT {
            resume.range_total(&response)
        } else {
            None
        };
        if offset > 0
            && range_total.is_none()
            && matches!(
                response.status(),
                StatusCode::PARTIAL_CONTENT | StatusCode::RANGE_NOT_SATISFIABLE
            )
        {
            drop(response);
            response = full_request().send().await.map_err(|e| e.to_string())?;
        }
        response = response.error_for_status().map_err(|e| e.to_string())?;
        let mut file = if let Some(total) = range_total {
            resume.total = Some(total);
            fs::OpenOptions::new().append(true).open(self.destination)
        } else {
            if response.status() != StatusCode::OK {
                return Err(format!("下载返回意外状态：{}", response.status()));
            }
            let etag = response
                .headers()
                .get(header::ETAG)
                .filter(|value| value.as_bytes().starts_with(b"\""))
                .cloned();
            *resume = Resume {
                offset: 0,
                total: self.size.or(response.content_length()),
                etag,
            };
            if offset > 0 || self.size.is_none() {
                progress(0, resume.total);
            }
            fs::File::create(self.destination)
        }
        .map_err(|e| e.to_string())?;

        let mut stream = response.bytes_stream();
        while let Some(bytes) = stream.next().await {
            let bytes = bytes.map_err(|e| e.to_string())?;
            let downloaded = resume.offset + bytes.len() as u64;
            if resume.total.is_some_and(|total| downloaded > total) {
                resume.offset = 0;
                return Err("下载文件大小超过预期".into());
            }
            file.write_all(&bytes).map_err(|e| {
                resume.offset = 0;
                e.to_string()
            })?;
            resume.offset = downloaded;
            progress(resume.offset, resume.total);
        }
        file.sync_all().map_err(|e| e.to_string())?;
        if resume.total.is_some_and(|total| resume.offset != total) {
            return Err("下载文件不完整".into());
        }
        Ok(())
    }
}

type Sample = (u64, Option<u64>);

fn show_race_progress(
    index: usize,
    samples: &[Mutex<Sample>],
    reported: &mut Option<(usize, Sample)>,
    progress: &mut impl FnMut(u64, Option<u64>),
) {
    let (bytes, total) = *samples[index].lock().expect("download sample poisoned");
    if *reported == Some((index, (bytes, total))) {
        return;
    }
    // A source change replaces the visible partial file. Reset delta-based consumers.
    if reported.is_none_or(|(prior, (_, prior_total))| prior != index || prior_total != total) {
        progress(0, total);
    }
    if bytes > 0 {
        progress(bytes, total);
    }
    *reported = Some((index, (bytes, total)));
}

struct RaceFiles(Vec<PathBuf>);

impl RaceFiles {
    fn path(&self, index: usize) -> &Path {
        &self.0[index]
    }

    fn discard_except(&self, keep: usize) {
        for (index, path) in self.0.iter().enumerate() {
            if index != keep {
                let _ = fs::remove_file(path);
            }
        }
    }
}

impl Drop for RaceFiles {
    fn drop(&mut self) {
        for path in &self.0 {
            let _ = fs::remove_file(path);
        }
    }
}

#[derive(Default)]
struct Resume {
    offset: u64,
    total: Option<u64>,
    etag: Option<header::HeaderValue>,
}

impl Resume {
    fn can_resume(&self) -> bool {
        self.offset > 0 && self.total.is_none_or(|total| self.offset < total)
    }

    fn range_total(&self, response: &reqwest::Response) -> Option<u64> {
        let range = response
            .headers()
            .get(header::CONTENT_RANGE)?
            .to_str()
            .ok()?;
        let (_, total) = range.split_once('/')?;
        let total = total.parse::<u64>().ok()?;
        if total <= self.offset
            || self.total.is_some_and(|expected| expected != total)
            || range != format!("bytes {}-{}/{total}", self.offset, total - 1)
            || self
                .etag
                .as_ref()
                .zip(response.headers().get(header::ETAG))
                .is_some_and(|(previous, current)| previous != current)
        {
            return None;
        }
        Some(total)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn only_project_release_urls_are_mirrored_without_nested_prefixes() {
        let url = format!("{RELEASE_ROOT}download/v1.0.0/TrailSnap.zip");
        let sources = candidates(&url);
        assert_eq!(sources.len(), 4);
        assert_eq!(candidates(&sources[1]), sources);
        assert_eq!(candidates(&sources[3]), sources);
        assert_eq!(
            sources[3],
            format!("{FIRST_PARTY_RELEASE_ROOT}download/v1.0.0/TrailSnap.zip")
        );
        for path in [
            "latest/download/latest.json",
            "download/v1.0.0-beta/TrailSnap.zip",
        ] {
            assert_eq!(candidates(&format!("{RELEASE_ROOT}{path}")).len(), 3);
        }
        for custom in [
            "http://127.0.0.1:1234/test",
            "https://example.com/latest.json",
            "https://github.com/other/repo/releases/latest",
            "https://github.com/LC044/TrailSnap/releases.evil/a",
        ] {
            assert_eq!(candidates(custom), vec![custom]);
        }
        let llama = format!("{LLAMA_RELEASE_ROOT}b123/runtime.zip");
        assert_eq!(candidates(&llama), vec![llama.clone()]);
        assert_eq!(llama_candidates(&llama).len(), 3);
        assert_eq!(llama_candidates(&url), vec![url]);
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

    #[tokio::test]
    async fn download_rejects_truncation_and_excess_then_can_retry() {
        let root =
            std::env::temp_dir().join(format!("trailsnap-download-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let archive = root.join("download.zip");
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                axum::Router::new().route("/runtime", axum::routing::get(|| async { "abc" })),
            )
            .await
            .unwrap();
        });
        let url = format!("http://{address}/runtime");
        let client = client().unwrap();
        for (size, expected) in [(4, Some("不完整")), (2, Some("超过")), (3, None)] {
            let result = Download {
                destination: &archive,
                size: Some(size),
                timeout: Duration::from_secs(5),
            }
            .fetch(&client, &url, &mut Resume::default(), &mut |_, _| {})
            .await;
            match expected {
                Some(error) => assert!(result.unwrap_err().contains(error)),
                None => result.unwrap(),
            }
        }
        assert_eq!(fs::read(&archive).unwrap(), b"abc");
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn download_resumes_a_partial_archive_and_restarts_if_range_is_unusable() {
        use std::sync::atomic::{AtomicUsize, Ordering};

        for (range_status, range_header) in [
            (StatusCode::PARTIAL_CONTENT, "bytes 3-5/6"),
            (StatusCode::PARTIAL_CONTENT, "bytes 2-5/6"),
            (StatusCode::RANGE_NOT_SATISFIABLE, "bytes */6"),
            (StatusCode::OK, ""),
        ] {
            let root =
                std::env::temp_dir().join(format!("trailsnap-download-{}", uuid::Uuid::new_v4()));
            fs::create_dir(&root).unwrap();
            let archive = root.join("download.zip");
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let address = listener.local_addr().unwrap();
            let count = std::sync::Arc::new(AtomicUsize::new(0));
            let calls = count.clone();
            let route = move |headers: header::HeaderMap| {
                let attempt = calls.fetch_add(1, Ordering::Relaxed);
                async move {
                    let mut response =
                        axum::http::Response::builder().header(header::ETAG, "\"v1\"");
                    let body = if attempt == 1 {
                        assert_eq!(headers.get(header::RANGE).unwrap(), "bytes=3-");
                        assert_eq!(headers.get(header::IF_RANGE).unwrap(), "\"v1\"");
                        response = response.status(range_status);
                        if !range_header.is_empty() {
                            response = response.header(header::CONTENT_RANGE, range_header);
                        }
                        if range_status == StatusCode::OK {
                            "abcdef"
                        } else {
                            "def"
                        }
                    } else {
                        assert!(!headers.contains_key(header::RANGE));
                        if attempt == 0 {
                            "abc"
                        } else {
                            "abcdef"
                        }
                    };
                    response.body(axum::body::Body::from(body)).unwrap()
                }
            };
            let server = tokio::spawn(async move {
                let app = axum::Router::new().route("/", axum::routing::get(route));
                axum::serve(listener, app).await.unwrap();
            });
            let url = format!("http://{address}/");
            let mut progress = Vec::new();
            Download {
                destination: &archive,
                size: Some(6),
                timeout: Duration::from_secs(5),
            }
            .verified(
                vec![url],
                DownloadMode::Single,
                |offset, _| progress.push(offset),
                |_| async { Ok(()) },
            )
            .await
            .unwrap();
            assert_eq!(fs::read(&archive).unwrap(), b"abcdef");
            let resumed = range_header == "bytes 3-5/6";
            assert!(progress.windows(2).any(|pair| pair == [3, 3]));
            assert_eq!(
                progress.iter().filter(|&&offset| offset == 0).count(),
                if resumed { 1 } else { 2 }
            );
            assert_eq!(
                count.load(Ordering::Relaxed),
                if resumed || range_status == StatusCode::OK {
                    2
                } else {
                    3
                }
            );
            server.abort();
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[tokio::test]
    async fn download_resumes_when_the_first_response_has_no_content_length() {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

        let root =
            std::env::temp_dir().join(format!("trailsnap-download-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let archive = root.join("download");
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            for (response, expected_range) in [
                (&b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n3\r\nabc\r\n"[..], false),
                (&b"HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 3-5/6\r\nContent-Length: 3\r\nConnection: close\r\n\r\ndef"[..], true),
            ] {
                let mut socket = BufReader::new(listener.accept().await.unwrap().0);
                let mut request = String::new();
                loop {
                    let mut line = String::new();
                    if socket.read_line(&mut line).await.unwrap() == 0 || line == "\r\n" {
                        break;
                    }
                    request.push_str(&line);
                }
                assert_eq!(request.to_ascii_lowercase().contains("range: bytes=3-"), expected_range);
                socket.write_all(response).await.unwrap();
                socket.shutdown().await.unwrap();
            }
        });
        let mut progress = Vec::new();
        let actual = Download {
            destination: &archive,
            size: None,
            timeout: Duration::from_secs(5),
        }
        .verified(
            vec![format!("http://{address}/")],
            DownloadMode::Single,
            |offset, total| progress.push((offset, total)),
            |archive| async move { fs::read(archive).map_err(|e| e.to_string()) },
        )
        .await
        .unwrap();
        assert_eq!(actual, b"abcdef");
        assert!(progress.contains(&(3, None)));
        assert_eq!(progress.last(), Some(&(6, Some(6))));
        server.await.unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn parallel_uses_the_fastest_transfer_and_removes_losing_files() {
        use axum::{body::Body, http::Response, routing::get, Router};
        use std::{convert::Infallible, sync::Arc};
        use tokio::sync::Notify;

        let root =
            std::env::temp_dir().join(format!("trailsnap-download-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let archive = root.join("download");
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let release_fast = Arc::new(Notify::new());
        let full_requests = Arc::new(AtomicUsize::new(0));
        let app = Router::new().route(
            "/{source}",
            get({
                let release_fast = release_fast.clone();
                let full_requests = full_requests.clone();
                move |axum::extract::Path(source): axum::extract::Path<String>,
                      headers: header::HeaderMap| {
                    let release_fast = release_fast.clone();
                    let full_requests = full_requests.clone();
                    async move {
                        let fast = source == "fast";
                        if let Some(range) = headers.get(header::RANGE) {
                            assert_eq!(range, "bytes=0-0");
                            if fast {
                                tokio::time::sleep(Duration::from_millis(30)).await;
                            }
                            return Response::builder()
                                .status(206)
                                .body(Body::from("a"))
                                .unwrap();
                        }
                        full_requests.fetch_add(1, Ordering::SeqCst);
                        let body = futures_util::stream::unfold(0, move |step| {
                            let release_fast = release_fast.clone();
                            async move {
                                let chunk = match step {
                                    0 if fast => "abc",
                                    0 => "x",
                                    1 if fast => {
                                        release_fast.notified().await;
                                        "def"
                                    }
                                    1 => std::future::pending().await,
                                    _ => return None,
                                };
                                Some((Ok::<_, Infallible>(chunk), step + 1))
                            }
                        });
                        Response::builder()
                            .header(header::CONTENT_LENGTH, 6)
                            .body(Body::from_stream(body))
                            .unwrap()
                    }
                }
            }),
        );
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let mut progress = Vec::new();
        Download {
            destination: &archive,
            size: Some(6),
            timeout: Duration::from_secs(4),
        }
        .verified(
            vec![
                format!("http://{address}/slow"),
                format!("http://{address}/fast"),
            ],
            DownloadMode::Parallel {
                sample: Duration::from_millis(650),
            },
            |bytes, _| {
                progress.push(bytes);
                if bytes == 3 {
                    // The loser is removed while the winning response is still open.
                    assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
                    release_fast.notify_one();
                }
            },
            |path| async move {
                assert_eq!(fs::read(path).unwrap(), b"abcdef");
                Ok(())
            },
        )
        .await
        .unwrap();
        assert!(progress.starts_with(&[0, 1, 0, 3]));
        assert_eq!(full_requests.load(Ordering::SeqCst), 2);
        assert_eq!(fs::read(&archive).unwrap(), b"abcdef");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn single_mode_only_downloads_the_first_working_source() {
        let root =
            std::env::temp_dir().join(format!("trailsnap-download-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let archive = root.join("download");
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = axum::Router::new()
            .route("/fast", axum::routing::get(|| async { "full" }))
            .route(
                "/fallback",
                axum::routing::get(|headers: header::HeaderMap| async move {
                    assert_eq!(headers.get(header::RANGE).unwrap(), "bytes=0-0");
                    tokio::time::sleep(Duration::from_millis(30)).await;
                    "probe"
                }),
            );
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Download {
            destination: &archive,
            size: Some(4),
            timeout: Duration::from_secs(4),
        }
        .verified(
            vec![
                format!("http://{address}/fast"),
                format!("http://{address}/fallback"),
            ],
            DownloadMode::Single,
            |_, _| {},
            |_| async { Ok(()) },
        )
        .await
        .unwrap();
        assert_eq!(fs::read(&archive).unwrap(), b"full");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }
}
